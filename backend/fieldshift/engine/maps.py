"""Computed terrain maps for the field area: rendered PNG overlays (web-mercator aligned), legends, field statistics,
management zones and a "Why" block per layer."""

from __future__ import annotations

import hashlib
import io
import json
import threading
from collections import OrderedDict
from typing import Any

import numpy as np
from PIL import Image

from ..data import dem as demmod
from ..data import sources
from ..data.http import DataUnavailable, get_json
from ..science import terrain
from ..science.cropmodel import crop

_PNG: OrderedDict[str, bytes] = OrderedDict()
_LOCK = threading.Lock()

# class breaks & colours (colour-blind-safe sequential palettes)
SLOPE_CLASSES = [
    (2, "#1a9850", "0–2 % flat"),
    (5, "#a6d96a", "2–5 % gentle"),
    (8, "#fee08b", "5–8 % moderate"),
    (15, "#f46d43", "8–15 % strong"),
    (1e9, "#a50026", "> 15 % steep"),
]
LOSS_CLASSES = [
    (1, "#1a9850", "< 1 t/ha/yr (tolerable)"),
    (3, "#a6d96a", "1–3"),
    (5, "#fee08b", "3–5"),
    (10, "#f46d43", "5–10 (high)"),
    (1e9, "#a50026", "> 10 (severe)"),
]
ZONES = {
    "erosion": (
        "#b2182b",
        "Erosion hotspot",
        "The worst-eroding part of the field: start here. Grass strips or contour bunds across the slope, terraces (e.g. fanya juu) on steep parts, permanent cover on the steepest spots.",
    ),
    "erosion_risk": (
        "#f4a259",
        "Erosion risk",
        "Soil loss above the tolerable ~5 t/ha a year: keep the soil covered (residue, cover crops), plough and plant along the contour.",
    ),
    "wet": (
        "#2c7fb8",
        "Wet / waterlogging-prone",
        "Water collects here: check drainage, avoid early-spring traffic, consider water-tolerant crops.",
    ),
    "frost": (
        "#6a51a3",
        "Frost-prone hollow",
        "Cold air pools here on clear nights: avoid frost-sensitive crops and very early sowing.",
    ),
    "core": ("#bfe0a4", "Productive core", "No major terrain constraint; manage as the main field."),
}


def _hex(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def _classed(v: np.ndarray, classes: list[tuple[float, str, str]], alpha: int = 190) -> np.ndarray:
    out = np.zeros(v.shape + (4,), dtype=np.uint8)
    lo = -np.inf
    for hi, col, _ in classes:
        m = (v >= lo) & (v < hi)
        out[m, :3] = _hex(col)
        out[m, 3] = alpha
        lo = hi
    return out


def _ramp(v: np.ndarray, stops: list[tuple[float, str]], alpha: np.ndarray | int = 190) -> np.ndarray:
    xs = [s[0] for s in stops]
    out = np.zeros(v.shape + (4,), dtype=np.uint8)
    for ch in range(3):
        out[..., ch] = np.interp(v, xs, [_hex(s[1])[ch] for s in stops]).astype(np.uint8)
    out[..., 3] = alpha
    return out


def _png(rgba: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def get_png(key: str, layer: str) -> bytes | None:
    with _LOCK:
        return _PNG.get(f"{key}/{layer}")


def _put(key: str, layer: str, data: bytes) -> None:
    with _LOCK:
        _PNG[f"{key}/{layer}"] = data
        while len(_PNG) > 120:
            _PNG.popitem(last=False)


def _annual_precip(lat: float, lon: float) -> float:
    """Mean annual precipitation (mm) from the NASA POWER climatology endpoint (fast, 1 request)."""
    try:
        f = get_json(
            "https://power.larc.nasa.gov/api/temporal/climatology/point",
            {
                "parameters": "PRECTOTCORR",
                "community": "AG",
                "latitude": round(lat, 3),
                "longitude": round(lon, 3),
                "format": "JSON",
            },
            ttl_s=365 * 86400,
            timeout_s=60,
        )
        ann = f.data["properties"]["parameter"]["PRECTOTCORR"]["ANN"]  # mm/day
        return float(ann) * 365.25
    except (DataUnavailable, KeyError, TypeError):
        return 500.0


def terrain_api(req: dict[str, Any]) -> dict[str, Any]:
    lat, lon = float(req["lat"]), float(req["lon"])
    cid = req.get("crop") or "maize"
    c = crop(cid)
    poly = req.get("polygon")
    key = hashlib.sha256(
        json.dumps([round(lat, 4), round(lon, 4), cid, poly], default=str).encode()
    ).hexdigest()[:20]
    try:
        dem, meta = demmod.dem_around(lat, lon)
    except Exception as e:  # tiles unavailable (offline without cache)
        raise DataUnavailable(f"elevation tiles unavailable: {e}") from e
    p_ann = _annual_precip(lat, lon)
    soil = sources.soil(lat, lon)
    texture = soil["texture"] if soil else "loam"
    cf = terrain.crop_c_factor(cid, c["type"])
    L = terrain.terrain_layers(dem, meta["cell_m"], p_ann, texture, cf)
    r_fac, k_fac = float(L["_meta_r"][0]), float(L["_meta_k"][0])

    # field mask: drawn polygon, else a 150 m radius around the pin
    if poly and len(poly) >= 3:
        mask = terrain.polygon_mask(dem.shape, [demmod.lonlat_to_px(p[0], p[1], meta) for p in poly])
    else:
        px, py = demmod.lonlat_to_px(lon, lat, meta)
        yy, xx = np.mgrid[0 : dem.shape[0], 0 : dem.shape[1]]
        mask = np.hypot(xx + 0.5 - px, yy + 0.5 - py) * meta["cell_m"] <= 150
    if not mask.any():
        mask[dem.shape[0] // 2, dem.shape[1] // 2] = True
    area_ha = float(mask.sum() * meta["cell_m"] ** 2 / 10000)

    # management zones (priority: erosion > wet > frost > core)
    twi_hi = float(np.percentile(L["twi_zone"], 90))
    zone = np.full(dem.shape, "core", dtype=object)
    zone[L["frost_zone"] >= 0.5] = "frost"
    zone[(L["twi_zone"] >= twi_hi) & (L["slope_pct"] < 3)] = "wet"
    # erosion: above the ~5 t/ha/yr tolerance = risk; hotspot = severe (>= 10) or the worst quarter of the at-risk
    # part of this field, so a uniformly erosive field still shows where to act first
    loss_z = L["soil_loss_zone"]
    zone[loss_z >= 5] = "erosion_risk"
    at_risk = loss_z[mask & (loss_z >= 5)]
    hot_thr = max(5.0, min(10.0, float(np.percentile(at_risk, 75)))) if at_risk.size else 10.0
    zone[loss_z >= hot_thr] = "erosion"

    # ---- render layers
    hs = L["hillshade"]
    elev = L["elevation"]
    e_lo, e_hi = np.percentile(elev, [2, 98])
    en = np.clip((elev - e_lo) / max(1.0, e_hi - e_lo), 0, 1)
    elev_rgba = _ramp(en, [(0, "#2b6c4a"), (0.35, "#a8c686"), (0.65, "#e6d595"), (1, "#a36f3c")], 235)
    shade = (0.55 + 0.45 * hs)[..., None]
    elev_rgba[..., :3] = np.clip(elev_rgba[..., :3] * shade, 0, 255).astype(np.uint8)
    twi_n = np.clip(
        (L["twi"] - np.percentile(L["twi"], 5))
        / max(1e-6, np.percentile(L["twi"], 99) - np.percentile(L["twi"], 5)),
        0,
        1,
    )
    zone_rgba = np.zeros(dem.shape + (4,), dtype=np.uint8)
    for zid, (col, _, _) in ZONES.items():
        m = zone == zid
        zone_rgba[m, :3] = _hex(col)
        zone_rgba[m, 3] = 170 if zid != "core" else 90
    hill_rgba = np.zeros(dem.shape + (4,), dtype=np.uint8)
    g = (hs * 255).astype(np.uint8)
    hill_rgba[..., 0] = g
    hill_rgba[..., 1] = g
    hill_rgba[..., 2] = g
    hill_rgba[..., 3] = 200
    frost_rgba = _ramp(
        L["frost_index"],
        [(0, "#f2f0f7"), (0.5, "#9e9ac8"), (1, "#3f007d")],
        (np.clip(L["frost_index"] * 2, 0, 1) * 210).astype(np.uint8),
    )
    rendered = {
        "elevation": elev_rgba,
        "hillshade": hill_rgba,
        "slope": _classed(L["slope_pct"], SLOPE_CLASSES),
        "erosion": _classed(L["soil_loss_zone"], LOSS_CLASSES),
        "wetness": _ramp(
            twi_n, [(0, "#f7fbff"), (0.5, "#6baed6"), (1, "#08306b")], (40 + twi_n * 190).astype(np.uint8)
        ),
        "frost": frost_rgba,
        "zones": zone_rgba,
    }
    for lid, rgba in rendered.items():
        _put(key, lid, _png(rgba))

    def st(v: np.ndarray) -> dict[str, float]:
        f = v[mask]
        return {
            "mean": round(float(f.mean()), 2),
            "p10": round(float(np.percentile(f, 10)), 2),
            "p90": round(float(np.percentile(f, 90)), 2),
            "max": round(float(f.max()), 2),
        }

    def class_shares(v: np.ndarray, classes: list[tuple[float, str, str]]) -> list[dict[str, Any]]:
        f = v[mask]
        out, lo = [], -np.inf
        for hi, col, lab in classes:
            out.append(
                {
                    "color": col,
                    "label": lab,
                    "share_pct": round(100 * float(np.mean((f >= lo) & (f < hi))), 1),
                }
            )
            lo = hi
        return out

    zone_shares: list[dict[str, Any]] = []
    zf = zone[mask]
    for zid, (col, lab, adv) in ZONES.items():
        share = round(100 * float(np.mean(zf == zid)), 1)
        zone_shares.append({"id": zid, "color": col, "label": lab, "share_pct": share, "advice": adv})

    srtm_note = "Elevation from AWS Terrain Tiles (NASA SRTM 30 m outside the U.S., USGS 3DEP in the U.S.), resampled to ~{:.0f} m pixels.".format(
        meta["cell_m"]
    )
    base_src = [
        {
            "id": "srtm",
            "name": "Elevation: AWS Terrain Tiles (NASA SRTM, USGS 3DEP)",
            "provider": "Mapzen/AWS Open Data; NASA; USGS",
            "url": "https://registry.opendata.aws/terrain-tiles/",
            "resolution": "~30 m source (10 m in U.S.)",
            "latency": "static",
            "last_date": None,
            "is_nasa": True,
            "status": "live",
        }
    ]
    sl = st(L["slope_pct"])
    loss = st(L["soil_loss"])
    layers: list[dict[str, Any]] = [
        {
            "id": "elevation",
            "label": "Elevation & relief",
            "unit": "m",
            "legend": [
                {"color": "#2b6c4a", "label": f"{e_lo:.0f} m"},
                {"color": "#a36f3c", "label": f"{e_hi:.0f} m"},
            ],
            "stats": st(elev),
            "why": f"Shaded relief from the DEM. Elevation range in view: {e_lo:.0f}–{e_hi:.0f} m. {srtm_note}",
        },
        {
            "id": "slope",
            "label": "Slope",
            "unit": "%",
            "legend": class_shares(L["slope_pct"], SLOPE_CLASSES),
            "stats": sl,
            "why": f"Steepness from Horn's method. Your field: mean {sl['mean']:.1f} %, steepest 10 % above {sl['p90']:.1f} %. Slopes above ~8 % need contour work and permanent cover.",
        },
        {
            "id": "erosion",
            "label": "Erosion risk (RUSLE)",
            "unit": "t/ha/yr",
            "legend": class_shares(L["soil_loss"], LOSS_CLASSES),
            "stats": loss,
            "why": (
                f"Estimated long-term soil loss A = R·K·LS·C (RUSLE) with R = {r_fac:.0f} MJ·mm/ha/h/yr from NASA POWER mean annual rain "
                f"({p_ann:.0f} mm), K = {k_fac:.3f} for {texture} soil, LS from slope and upslope flow area, and C = {cf:.2f} for {c['name']}. "
                f"Field mean {loss['mean']:.1f}, hotspots (p90) {loss['p90']:.1f} t/ha/yr. Values are indicative (no support practices, P = 1)."
            ),
        },
        {
            "id": "wetness",
            "label": "Wetness (water collects)",
            "unit": "TWI",
            "legend": [
                {"color": "#f7fbff", "label": "dry / shedding"},
                {"color": "#08306b", "label": "wet / collecting"},
            ],
            "stats": st(L["twi"]),
            "why": "Topographic wetness index ln(a / tan β): high where a large upslope area drains into flat ground. Shows where water ponds and soils stay wet longer.",
        },
        {
            "id": "frost",
            "label": "Frost-prone hollows",
            "unit": "index",
            "legend": [
                {"color": "#f2f0f7", "label": "low"},
                {"color": "#3f007d", "label": "cold-air pooling"},
            ],
            "stats": st(L["frost_index"]),
            "why": "Valleys and hollows lower than their surroundings (negative topographic position within ~300 m) on gentle slopes collect cold, dense air on clear, calm nights — late spring and early autumn frosts hit here first.",
        },
        {
            "id": "zones",
            "label": "Management zones",
            "unit": "",
            "legend": [
                {"color": z["color"], "label": f"{z['label']} ({z['share_pct']} %)"} for z in zone_shares
            ],
            "stats": {},
            "why": "Zones combine the maps: erosion risk (RUSLE ≥ 5 t/ha/yr, about the tolerable soil loss) and erosion hotspots (≥ 10 t/ha/yr, or the worst quarter of the at-risk part of this field), wet spots (top 10 % wetness on < 3 % slope), frost hollows (index ≥ 0.5); the rest is the productive core.",
        },
        {
            "id": "hillshade",
            "label": "Hillshade",
            "unit": "",
            "legend": [],
            "stats": {},
            "why": "Relief illuminated from the north-west to make landforms visible.",
        },
    ]
    for lyr in layers:
        lyr["png"] = f"/api/terrain/png/{key}/{lyr['id']}.png"
    advice = [z for z in zone_shares if z["id"] != "core" and z["share_pct"] >= 5]
    return {
        "key": key,
        "bounds": {
            "south": meta["south"],
            "west": meta["west"],
            "north": meta["north"],
            "east": meta["east"],
        },
        "cell_m": round(meta["cell_m"], 1),
        "field": {
            "area_ha": round(area_ha, 2),
            "polygon": bool(poly and len(poly) >= 3),
            "texture": texture,
            "annual_precip_mm": round(p_ann),
        },
        "layers": layers,
        "zones": zone_shares,
        "zone_advice": advice
        or [
            {
                "id": "core",
                "label": ZONES["core"][1],
                "share_pct": 100.0,
                "advice": "No major terrain constraint in your field.",
                "color": ZONES["core"][0],
            }
        ],
        "sources": base_src
        + [
            sources.source_ref("nasa_power", "live"),
            sources.source_ref("soilgrids", "live" if soil else "unavailable"),
        ],
        "caveats": [
            srtm_note,
            "Without a drawn field outline, statistics use a 150 m radius around your pin.",
            "Terrain maps show where water, soil and cold air move; they do not include drainage tiles, terraces or field roads.",
        ],
    }
