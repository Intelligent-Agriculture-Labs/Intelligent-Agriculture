"""Terrain analysis on a DEM grid (pure numpy): slope, aspect, hillshade, flow accumulation, wetness, cold-air
pooling, and RUSLE soil-loss estimates.

References (docs/MODELS.md §Terrain):
  * Slope/aspect: Horn (1981) finite differences.  Hillshade: Burrough & McDonnell (1998).
  * D8 flow routing: O'Callaghan & Mark (1984).  TWI = ln(a / tan β): Beven & Kirkby (1979).
  * TPI (topographic position index): Weiss (2001); valley bottoms with negative TPI collect cold air at night.
  * RUSLE A = R·K·LS·C·P (Renard et al. 1997). LS from flow accumulation: Moore & Burch (1986).
    R from annual precipitation: Renard & Freimund (1994). K by texture class: Stone & Hilborn (2012, OMAFRA) mid-values.
"""

from __future__ import annotations

import math

import numpy as np

# soil erodibility K (t·ha·h / (ha·MJ·mm)) by USDA texture, OMAFRA table (average organic matter), converted from US units
K_BY_TEXTURE = {
    "sand": 0.004,
    "loamy sand": 0.007,
    "sandy loam": 0.017,
    "loam": 0.039,
    "silt loam": 0.050,
    "silt": 0.054,
    "sandy clay loam": 0.026,
    "clay loam": 0.039,
    "silty clay loam": 0.042,
    "sandy clay": 0.018,
    "silty clay": 0.034,
    "clay": 0.029,
}
# annual cover-management factor C (indicative; Wischmeier & Smith 1978 / Panagos et al. 2015 ranges)
C_BY_CROP_TYPE = {"perennial": 0.02, "cover": 0.05, "small_grain": 0.20, "row": 0.38, "bare": 1.0}
SMALL_GRAINS = {"winter_wheat", "barley", "triticale_forage", "teff", "pearl_millet"}


def crop_c_factor(crop_id: str, crop_type: str) -> float:
    if crop_type == "perennial":
        return C_BY_CROP_TYPE["perennial"]
    if crop_type == "cover":
        return C_BY_CROP_TYPE["cover"]
    return C_BY_CROP_TYPE["small_grain"] if crop_id in SMALL_GRAINS else C_BY_CROP_TYPE["row"]


def rusle_r_factor(annual_precip_mm: float) -> float:
    """Rainfall erosivity R (MJ·mm·ha⁻¹·h⁻¹·yr⁻¹) from mean annual precipitation (Renard & Freimund 1994)."""
    p = max(0.0, annual_precip_mm)
    if p <= 850:
        return 0.0483 * p**1.61
    return 587.8 - 1.219 * p + 0.004105 * p**2


def box_mean(a: np.ndarray, r: int) -> np.ndarray:
    """Mean over a (2r+1)² window using an integral image (edges use the available cells)."""
    pad = np.pad(a, r + 1, mode="edge")
    c = pad.cumsum(0).cumsum(1)
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s[: a.shape[0], : a.shape[1]] / (k * k)


def slope_aspect(dem: np.ndarray, cell: float) -> tuple[np.ndarray, np.ndarray]:
    """Horn (1981) slope (radians) and aspect (degrees from north, clockwise)."""
    z = np.pad(dem, 1, mode="edge")
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    d, f = z[1:-1, :-2], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cell)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cell)  # rows increase southwards
    slope = np.arctan(np.hypot(dzdx, dzdy))
    # downslope direction as a compass bearing: east component -dz/dx, north component -dz/dnorth = +dzdy(rows)
    aspect = (np.degrees(np.arctan2(-dzdx, dzdy)) + 360) % 360
    return slope, aspect


def hillshade(
    slope: np.ndarray, aspect: np.ndarray, azimuth: float = 315.0, altitude: float = 45.0
) -> np.ndarray:
    zen = math.radians(90 - altitude)
    az = math.radians(azimuth)
    asp = np.radians(aspect)
    hs = math.cos(zen) * np.cos(slope) + math.sin(zen) * np.sin(slope) * np.cos(az - asp)
    return np.clip(hs, 0, 1)


_NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def d8_accumulation(dem: np.ndarray, cell: float) -> np.ndarray:
    """Upslope contributing cells (including itself) by D8 steepest descent (O'Callaghan & Mark 1984).
    Pits/flats keep their water (no depression filling) — adequate for field-scale relative wetness."""
    h, w = dem.shape
    z = np.pad(dem, 1, mode="constant", constant_values=np.inf)
    best = np.zeros((h, w))
    rec_r = np.full((h, w), -1, dtype=np.int64)
    rec_c = np.full((h, w), -1, dtype=np.int64)
    rr, cc = np.mgrid[0:h, 0:w]
    for dr, dc in _NB:
        dist = cell * (math.sqrt(2) if dr and dc else 1.0)
        drop = (dem - z[1 + dr : 1 + dr + h, 1 + dc : 1 + dc + w]) / dist
        better = drop > best
        best = np.where(better, drop, best)
        rec_r = np.where(better, rr + dr, rec_r)
        rec_c = np.where(better, cc + dc, rec_c)
    acc = np.ones(h * w)
    order = np.argsort(-dem, axis=None)
    rec = np.where(rec_r >= 0, rec_r * w + rec_c, -1).ravel()
    for idx in order:  # highest first: pass water to receiver
        r = rec[idx]
        if r >= 0:
            acc[r] += acc[idx]
    return acc.reshape(h, w)


def terrain_layers(
    dem: np.ndarray, cell: float, annual_precip_mm: float, texture: str, c_factor: float
) -> dict[str, np.ndarray]:
    """All analysis layers on the DEM grid. `cell` = pixel size in metres."""
    # smooth to the true source scale (~30 m SRTM): tiles are oversampled and carry "orange-peel" noise
    r_s = max(1, int(round(15 / cell)))
    dem_s = box_mean(box_mean(dem, r_s), r_s)
    slope, aspect = slope_aspect(dem_s, cell)
    hs = hillshade(slope, aspect)
    acc = d8_accumulation(dem_s, cell)
    sca = acc * cell  # specific catchment area (m²/m)
    tan_b = np.tan(np.maximum(slope, 0.001))
    twi = np.log(sca / tan_b)
    r_px = max(1, int(round(300 / cell)))
    tpi = dem_s - box_mean(dem_s, r_px)
    # cold-air pooling index 0..1: concave positions (negative TPI) on gentle slopes collect cold, dense air on clear nights
    frost = np.clip(-tpi / 8.0, 0, 1) * np.clip(1 - np.degrees(slope) / 8.0, 0, 1)
    # RUSLE: LS (Moore & Burch 1986) with flow length capped at ~120 m (field boundaries, tillage breaks)
    as_cap = np.minimum(sca, 120.0)
    ls = (as_cap / 22.13) ** 0.4 * (np.sin(slope) / 0.0896) ** 1.3
    r = rusle_r_factor(annual_precip_mm)
    k = K_BY_TEXTURE.get(texture, 0.03)
    soil_loss = r * k * ls * c_factor  # t/ha/yr (P = 1)
    # zone-scale versions (smoothed ~60 m) used for classification, so zones are contiguous areas, not speckle
    r_z = max(1, int(round(45 / cell)))
    return {
        "soil_loss_zone": box_mean(soil_loss, r_z),
        "twi_zone": box_mean(twi, r_z),
        "frost_zone": box_mean(frost, r_z),
        "elevation": dem,
        "hillshade": hs,
        "slope_pct": 100 * np.tan(slope),
        "aspect": aspect,
        "flow_acc": acc,
        "twi": twi,
        "tpi": tpi,
        "frost_index": frost,
        "ls": ls,
        "soil_loss": soil_loss,
        "_meta_r": np.array([r]),
        "_meta_k": np.array([k]),
    }


def polygon_mask(shape: tuple[int, int], poly_px: list[tuple[float, float]]) -> np.ndarray:
    """Vectorised even–odd point-in-polygon test for pixel centres. poly_px = [(col, row), ...]."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    x = xx + 0.5
    y = yy + 0.5
    inside = np.zeros(shape, dtype=bool)
    n = len(poly_px)
    for i in range(n):
        x1, y1 = poly_px[i]
        x2, y2 = poly_px[(i + 1) % n]
        cond = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1)
        inside ^= cond
    return inside
