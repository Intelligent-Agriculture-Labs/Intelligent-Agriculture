"""Global yield calibration (ADR-022, docs/VALIDATION.md V10).

The season model's attainable yield (`typical_yield_t_ha` × completion² × water/heat/frost factors,
docs/MODELS.md §2) is scaled by a small, documented set of multiplicative factors fitted against FAOSTAT
national yields at 40+ countries (`scripts/yield_benchmark.py`):

    Y = Y_model × f_crop × f_region ** s_crop  (× f_zone × f_irrigated, both unused in v1)

* f_crop: per-crop potential-yield factor, fitted where the crop table's typical yields come from
  (Northern America, Western and Southern Europe: f_region = 1 there).
* f_region: management / yield-gap factor per UN M49 macro region.
* s_crop: the crop's yield-gap sensitivity (maize and sorghum gaps are larger than cassava's, so the
  same regional factor is raised to a crop-specific power).
* f_zone: optional Köppen–Geiger main climate group factor (only when the benchmark justified it).
* f_irrigated: optional factor for irrigated seasons (smaller yield gap under irrigation), if selected.
* f_country: the field's country (ADR-027, config/yield_country_factors.yaml): the benchmark residual of the
  41 benchmarked countries, else the country's FAOSTAT national yields relative to its macro region (half weight).

Factors live in `config/yield_calibration.yaml` with their sources and fit statistics. Annual crops
without a benchmark entry (vegetables, pulses other than dry bean, teff, …) get only the regional factor
(f_crop = 1, s = 1), so crop comparisons in one place stay consistent; perennials, forages and cover crops
are not calibrated. A `Weather` record without a region (unit tests, the benchmark itself) is never
calibrated.

The region comes from a 0.5° country grid derived from MIRCA2000's unit grid (Portmann et al., 2010),
mapped to UN M49 sub-regions; the climate group is computed from the location's own NASA POWER record.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"
GRID = CONFIG / "region_grid_30mn.npz"
ZONES = ("tropical", "arid", "temperate", "continental")


def climate_zone(dates: Sequence[dt.date], tmax: np.ndarray, tmin: np.ndarray, rain: np.ndarray) -> str:
    """Köppen–Geiger main group (Kottek et al., 2006) from a daily record.

    arid (B) is tested first: annual P < 10·P_th with P_th = 2·MAT (≥70 % of rain in winter),
    2·MAT + 28 (≥70 % in summer) or 2·MAT + 14. Then tropical (A, coldest month ≥ 18 °C), continental
    (D/E, coldest month ≤ −3 °C) and temperate (C). The summer half-year is the warmer one, so the
    hemisphere does not have to be known.
    """
    months = np.fromiter((d.month for d in dates), dtype=np.int8, count=len(dates))
    t = (np.asarray(tmax, float) + np.asarray(tmin, float)) / 2
    p = np.asarray(rain, float)
    tm = np.full(12, np.nan)
    pm = np.full(12, np.nan)
    for m in range(1, 13):
        sel = months == m
        tv = t[sel]
        pv = p[sel]
        if np.isfinite(tv).sum() < 20:
            continue
        tm[m - 1] = float(np.nanmean(tv))
        ok = np.isfinite(pv)
        # mean monthly total = mean daily rain × days in month
        pm[m - 1] = float(np.mean(pv[ok]) * 30.44) if ok.any() else 0.0
    if not np.isfinite(tm).all():
        return "temperate"
    pm = np.nan_to_num(pm)
    mat = float(np.mean(tm))
    pann = float(np.sum(pm))
    amj_as = list(range(3, 9))  # Apr–Sep (0-based 3..8)
    other = [i for i in range(12) if i not in amj_as]
    summer = amj_as if np.mean(tm[amj_as]) >= np.mean(tm[other]) else other
    ps = float(np.sum(pm[summer]))
    if pann > 0 and ps >= 0.7 * pann:
        pth = 2 * mat + 28
    elif pann > 0 and ps <= 0.3 * pann:
        pth = 2 * mat
    else:
        pth = 2 * mat + 14
    if pann < 10 * pth:
        return "arid"
    if np.min(tm) >= 18:
        return "tropical"
    if np.min(tm) <= -3:
        return "continental"
    return "temperate"


@lru_cache
def _grid() -> tuple[np.ndarray, list[str]] | None:
    if not GRID.exists():
        return None
    z = np.load(GRID, allow_pickle=False)
    return z["region"], [str(s) for s in z["names"]]


def region_of(lat: float, lon: float) -> str | None:
    """Macro region (UN M49 based) of a land location, or None (ocean / outside the grid)."""
    g = _grid()
    if g is None or not (np.isfinite(lat) and np.isfinite(lon)):
        return None
    grid, names = g
    row = int(np.clip((90.0 - lat) // 0.5, 0, grid.shape[0] - 1))
    col = int(np.clip((lon + 180.0) // 0.5, 0, grid.shape[1] - 1))
    # coastal cells can be water at 0.5°: look one cell around
    for dr, dc in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        r, c = row + dr, (col + dc) % grid.shape[1]
        if 0 <= r < grid.shape[0] and grid[r, c] > 0:
            return names[int(grid[r, c]) - 1]
    return None


@lru_cache
def calibration() -> dict[str, Any]:
    path = CONFIG / "yield_calibration.yaml"
    if not path.exists():
        return {"crops": {}, "regions": {}, "zones": {}}
    with open(path) as f:
        out: dict[str, Any] = yaml.safe_load(f) or {}
    for k in ("crops", "regions", "zones"):
        out[k] = out.get(k) or {}
    return out


@lru_cache
def country_factors() -> dict[str, Any]:
    """Per-country yield factors (ADR-027, config/yield_country_factors.yaml): benchmark residual for the 41
    benchmarked countries, else the country's FAOSTAT national yields relative to its macro region (half weight)."""
    path = CONFIG / "yield_country_factors.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        out: dict[str, Any] = (yaml.safe_load(f) or {}).get("countries") or {}
    return out


def country_factor(country: str | None) -> float:
    e = country_factors().get(country or "") if country else None
    return float(e["factor"]) if e else 1.0


def factor(
    crop_id: str, region: str | None, zone: str | None, irrigated: bool = False, country: str | None = None
) -> float:
    """Multiplicative yield calibration for one crop at one location (1.0 = uncalibrated)."""
    if region is None:
        return 1.0
    cal = calibration()
    entry = cal["crops"].get(crop_id)
    if entry is None:
        # not benchmarked (no FAOSTAT series): annual field crops get the regional management gap with
        # sensitivity 1 so that crop comparisons (rotations) stay fair; perennials/forages/covers: none
        from .cropmodel import crops

        if crops().get(crop_id, {}).get("type") != "annual" or not cal["regions"]:
            return 1.0
        entry = {"factor": 1.0, "gap_sensitivity": 1.0}
    f = float(entry.get("factor", 1.0))
    f *= float(cal["regions"].get(region, {}).get("factor", 1.0)) ** float(entry.get("gap_sensitivity", 1.0))
    if zone is not None:
        f *= float(cal["zones"].get(zone, {}).get("factor", 1.0))
    if irrigated:
        f *= float(cal.get("irrigated_factor", 1.0))
    f *= country_factor(country)
    lo, hi = cal.get("bounds", [0.1, 2.0])
    return float(np.clip(f, lo, hi))
