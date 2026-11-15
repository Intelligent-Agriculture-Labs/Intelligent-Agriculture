"""Tap-to-detect field boundaries on high-resolution imagery (see science/fielddetect.py)."""

from __future__ import annotations

import io
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import numpy as np
from PIL import Image

from ..data.dem import lonlat_to_tile, tile_to_lonlat
from ..data.http import CACHE_DIR, DEMO_DIR, DataUnavailable, offline_mode
from ..science import fielddetect
from .messages import t

IMAGERY = {
    "esri": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "Imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community",  # i18n: ok (attribution)
        19,
    ),
    "naip": (
        "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
        "USDA NAIP / USGS The National Map (public domain)",  # i18n: ok (attribution)
        16,
    ),
}


# technical method descriptions (API metadata, not shown to farmers)
METHODS = {
    "learned": "Learned field-edge map (tiny U-Net trained on Fields of The World) + scale-adaptive candidate regions "  # i18n: ok
    "ranked by a learned IoU predictor + Douglas–Peucker (tap-to-delineate)",
    "classical": "Field-scale graph segmentation (Felzenszwalb) + edge-aware region growing + Douglas–Peucker "  # i18n: ok
    "(tap-to-delineate)",
}


def _tile(src: str, z: int, x: int, y: int) -> np.ndarray:
    name = f"{src}_{z}_{x}_{y}.jpg"
    for d in (CACHE_DIR / "imagery", DEMO_DIR / "imagery"):
        p = d / name
        if p.exists():
            return np.asarray(Image.open(p).convert("RGB"))
    if offline_mode():
        raise DataUnavailable("imagery not cached (offline)")
    r = httpx.get(
        IMAGERY[src][0].format(z=z, x=x, y=y),
        timeout=30,
        headers={"User-Agent": "FieldShift/1.0 (NASA Space Apps 2026)"},
    )
    if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
        raise DataUnavailable(f"imagery tile {src} {z}/{x}/{y}: HTTP {r.status_code}")
    (CACHE_DIR / "imagery").mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "imagery" / name).write_bytes(r.content)
    return np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))


def _mosaic(
    src: str, lat: float, lon: float, z: int, half: int = 1
) -> tuple[np.ndarray, int, int, tuple[int, int]]:
    fx, fy = lonlat_to_tile(lon, lat, z)
    cx, cy = int(fx), int(fy)
    xs, ys = range(cx - half, cx + half + 1), range(cy - half, cy + half + 1)
    with ThreadPoolExecutor(max_workers=9) as ex:
        t = {(x, y): ex.submit(_tile, src, z, x, y) for y in ys for x in xs}
        img = np.vstack([np.hstack([t[(x, y)].result() for x in xs]) for y in ys])
    seed = (int((fy - (cy - half)) * 256), int((fx - (cx - half)) * 256))
    return img, cx - half, cy - half, seed


def _merge_close(ring: list[list[float]], lat: float, min_m: float) -> list[list[float]]:
    """Drop vertices closer than min_m to the previously kept vertex (cleaner outlines to edit by hand)."""
    if ring and ring[0] == ring[-1]:
        ring = ring[:-1]
    kx = 111320.0 * math.cos(math.radians(lat))
    out: list[list[float]] = []
    for p in ring:
        if not out or math.hypot((p[0] - out[-1][0]) * kx, (p[1] - out[-1][1]) * 110540.0) >= min_m:
            out.append(p)
    if (
        len(out) > 3
        and math.hypot((out[0][0] - out[-1][0]) * kx, (out[0][1] - out[-1][1]) * 110540.0) < min_m
    ):
        out.pop()
    return out if len(out) >= 3 else ring


def detect_field(lat: float, lon: float, source: str | None = None, lang: str = "en") -> dict[str, Any]:
    src = source or "esri"
    attempts = [(src, 17), (src, 16)] if src == "esri" else [(src, 16), (src, 15)]
    last: dict[str, Any] | None = None
    for s, z in attempts:
        img, x0, y0, seed = _mosaic(s, lat, lon, z)
        px_m = 40075016.686 * math.cos(math.radians(lat)) / (2**z) / 256
        res = fielddetect.detect(img, seed, pixel_m=px_m)
        if res is None:
            continue
        last = {**res, "_z": z, "_x0": x0, "_y0": y0, "_src": s}
        if not res["touches_border"]:
            break
    if last is None:
        raise DataUnavailable("no field region found at this point — draw the boundary by hand")
    z, x0, y0 = last["_z"], last["_x0"], last["_y0"]
    ring = []
    for r, c in last["polygon_rc"]:
        lo, la = tile_to_lonlat(x0 + c / 256.0, y0 + r / 256.0, z)
        ring.append([round(lo, 6), round(la, 6)])
    ring = _merge_close(ring, lat, min_m=8.0)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    m_per_px = 40075016.686 * math.cos(math.radians(lat)) / (2**z) / 256
    area_ha = last["area_px"] * m_per_px**2 / 10000
    return {
        "polygon": ring,
        "area_ha": round(area_ha, 2),
        "confidence": last["confidence"],
        "touches_border": last["touches_border"],
        "method": METHODS[last["params"].get("method", "classical")],
        "imagery": IMAGERY[last["_src"]][1],
        "pixel_m": round(m_per_px, 2),
        "params": last["params"],
        "note": t("detect_note", lang),
    }
