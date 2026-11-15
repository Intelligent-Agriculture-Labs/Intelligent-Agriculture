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
from .messages import crop_name, t, word

_PNG: OrderedDict[str, bytes] = OrderedDict()
_LOCK = threading.Lock()

# class breaks & colours (colour-blind-safe sequential palettes)
SLOPE_CLASSES = [
    (2, "#1a9850", "slope_flat"),  # third item: message key (or a language-neutral label)
    (5, "#a6d96a", "slope_gentle"),
    (8, "#fee08b", "slope_moderate"),
    (15, "#f46d43", "slope_strong"),
    (1e9, "#a50026", "slope_steep"),
]
LOSS_CLASSES = [
    (1, "#1a9850", "loss_tolerable"),
    (3, "#a6d96a", "1–3"),
    (5, "#fee08b", "3–5"),
    (10, "#f46d43", "loss_high"),
    (1e9, "#a50026", "loss_severe"),
]
# zone id -> (colour, label key, advice key) in config/messages/maps.yaml
ZONES = {
    "erosion": ("#b2182b", "zone_erosion", "zone_erosion_advice"),
    "erosion_risk": ("#f4a259", "zone_erosion_risk", "zone_erosion_risk_advice"),
    "wet": ("#2c7fb8", "zone_wet", "zone_wet_advice"),
    "frost": ("#6a51a3", "zone_frost", "zone_frost_advice"),
    "core": ("#bfe0a4", "zone_core", "zone_core_advice"),
}


def _lbl(key: str, lang: str) -> str:
    """Class label: a message key, or a language-neutral range such as "1–3"."""
    return key if key[0].isdigit() else t(key, lang)


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
    lang = req.get("lang") or "en"
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
                    "label": _lbl(lab, lang),
                    "share_pct": round(100 * float(np.mean((f >= lo) & (f < hi))), 1),
                }
            )
            lo = hi
        return out

    zone_shares: list[dict[str, Any]] = []
    zf = zone[mask]
    for zid, (col, lab, adv) in ZONES.items():
        share = round(100 * float(np.mean(zf == zid)), 1)
        zone_shares.append(
            {"id": zid, "color": col, "label": t(lab, lang), "share_pct": share, "advice": t(adv, lang)}
        )

    srtm_note = t("map_srtm_note", lang, m=meta["cell_m"])
    base_src = [
        {
            "id": "srtm",
            "name": t("src_srtm_name", lang),
            "provider": "Mapzen/AWS Open Data; NASA; USGS",  # i18n: ok (organisation names)
            "url": "https://registry.opendata.aws/terrain-tiles/",
            "resolution": t("src_srtm_res", lang),
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
            "label": t("layer_elevation", lang),
            "unit": "m",
            "legend": [
                {"color": "#2b6c4a", "label": f"{e_lo:.0f} m"},
                {"color": "#a36f3c", "label": f"{e_hi:.0f} m"},
            ],
            "stats": st(elev),
            "why": t("layer_elevation_why", lang, lo=e_lo, hi=e_hi, note=srtm_note),
        },
        {
            "id": "slope",
            "label": t("layer_slope", lang),
            "unit": "%",
            "legend": class_shares(L["slope_pct"], SLOPE_CLASSES),
            "stats": sl,
            "why": t("layer_slope_why", lang, mean=sl["mean"], p90=sl["p90"]),
        },
        {
            "id": "erosion",
            "label": t("layer_erosion", lang),
            "unit": "t/ha/yr",
            "legend": class_shares(L["soil_loss"], LOSS_CLASSES),
            "stats": loss,
            "why": t(
                "layer_erosion_why",
                lang,
                r=r_fac,
                p=p_ann,
                k=k_fac,
                soil=word("soil", texture, lang),
                cf=cf,
                crop=crop_name(cid, lang, c["name"]),
                mean=loss["mean"],
                p90=loss["p90"],
            ),
        },
        {
            "id": "wetness",
            "label": t("layer_wetness", lang),
            "unit": "TWI",
            "legend": [
                {"color": "#f7fbff", "label": t("legend_dry", lang)},
                {"color": "#08306b", "label": t("legend_wet", lang)},
            ],
            "stats": st(L["twi"]),
            "why": t("layer_wetness_why", lang),
        },
        {
            "id": "frost",
            "label": t("layer_frost", lang),
            "unit": "index",
            "legend": [
                {"color": "#f2f0f7", "label": t("legend_low", lang)},
                {"color": "#3f007d", "label": t("legend_cold_pool", lang)},
            ],
            "stats": st(L["frost_index"]),
            "why": t("layer_frost_why", lang),
        },
        {
            "id": "zones",
            "label": t("layer_zones", lang),
            "unit": "",
            "legend": [
                {"color": z["color"], "label": f"{z['label']} ({z['share_pct']} %)"} for z in zone_shares
            ],
            "stats": {},
            "why": t("layer_zones_why", lang),
        },
        {
            "id": "hillshade",
            "label": t("layer_hillshade", lang),
            "unit": "",
            "legend": [],
            "stats": {},
            "why": t("layer_hillshade_why", lang),
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
                "label": t(ZONES["core"][1], lang),
                "share_pct": 100.0,
                "advice": t("zone_core_none", lang),
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
            t("map_caveat_radius", lang),
            t("map_caveat_features", lang),
        ],
    }
