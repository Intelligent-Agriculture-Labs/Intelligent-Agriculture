"""Sentinel-2 L2A field windows from the open Earth Search STAC (Element 84, AWS Open Data; ESA Copernicus data).

Each band is read through a GDAL WarpedVRT directly onto a common web-mercator grid around the field, so
scenes from different UTM tiles stack pixel-for-pixel and overlays align with the map. Only the needed COG
blocks are fetched (HTTP range requests); no authentication.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

import numpy as np

from .http import get_json, offline_mode

STAC = "https://earth-search.aws.element84.com/v1/search"
GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    AWS_NO_SIGN_REQUEST="YES",
    GDAL_HTTP_MULTIRANGE="YES",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    GDAL_HTTP_TIMEOUT="60",
    GDAL_HTTP_MAX_RETRY="3",
    GDAL_HTTP_RETRY_DELAY="2",
    VSI_CACHE="TRUE",
)
R = 6378137.0


def merc(lon: float, lat: float) -> tuple[float, float]:
    return math.radians(lon) * R, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * R


def inv_merc(x: float, y: float) -> tuple[float, float]:
    return math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)


def field_grid(
    lat: float, lon: float, polygon: list[list[float]] | None, margin_m: float = 120.0
) -> dict[str, Any]:
    """Web-mercator grid (~10 m ground pixels) covering the field polygon (+margin) or a 300 m box around the pin."""
    if polygon and len(polygon) >= 3:
        xs, ys = zip(*(merc(p[0], p[1]) for p in polygon), strict=True)
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    else:
        cx, cy = merc(lon, lat)
        half = 300 / math.cos(math.radians(lat))
        x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half
    scale = 1 / math.cos(math.radians(lat))  # mercator metres per ground metre
    m = margin_m * scale
    x0, x1, y0, y1 = x0 - m, x1 + m, y0 - m, y1 + m
    px = 10.0 * scale
    w = max(16, min(600, int(math.ceil((x1 - x0) / px))))
    h = max(16, min(600, int(math.ceil((y1 - y0) / px))))
    west, south = inv_merc(x0, y1 - h * px)
    east, north = inv_merc(x0 + w * px, y1)
    return {
        "x0": x0,
        "y1": y1,
        "px": px,
        "w": w,
        "h": h,
        "bounds": {"south": south, "west": west, "north": north, "east": east},
    }


def search(
    grid: dict[str, Any], start: dt.date, end: dt.date, max_cloud: float = 60.0
) -> list[dict[str, Any]]:
    b = grid["bounds"]
    bbox = [b["west"], b["south"], b["east"], b["north"]]
    body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": [b["west"], b["south"], b["east"], b["north"]],
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": 200,
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
    }
    # POST search is not cached by get_json (GET-only) -> use the GET form of the STAC API
    params = {
        "collections": "sentinel-2-l2a",
        "bbox": ",".join(f"{v:.5f}" for v in bbox),
        "datetime": body["datetime"],
        "limit": 200,
    }
    f = get_json(STAC, params, ttl_s=6 * 3600, timeout_s=90)
    feats = f.data.get("features", [])
    out: dict[str, dict[str, Any]] = {}
    for it in feats:
        cc = float(it["properties"].get("eo:cloud_cover", 100))
        if cc >= max_cloud:
            continue
        d = it["properties"]["datetime"][:10]
        if d not in out or cc < out[d]["cloud_pct"]:  # same day from overlapping tiles: keep the clearest
            assets = it["assets"]

            def band(name: str, assets: dict[str, Any] = assets) -> dict[str, Any]:
                a = assets[name]
                rb = (a.get("raster:bands") or [{}])[0]
                return {"href": a["href"], "scale": rb.get("scale", 0.0001), "offset": rb.get("offset", 0.0)}

            try:
                out[d] = {
                    "id": it["id"],
                    "date": d,
                    "cloud_pct": round(cc, 1),
                    "red": band("red"),
                    "nir": band("nir"),
                    "green": band("green"),
                    "blue": band("blue"),
                    "scl": band("scl"),
                }
            except KeyError:
                continue
    return [out[k] for k in sorted(out)]


def read_scene(
    scene: dict[str, Any], grid: dict[str, Any], bands: tuple[str, ...] = ("red", "nir", "scl")
) -> dict[str, np.ndarray]:
    """Read bands onto the field grid (reflectance for optical bands, class codes for SCL)."""
    if offline_mode():
        raise RuntimeError("offline")
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT

    tr = from_origin(grid["x0"], grid["y1"], grid["px"], grid["px"])
    out: dict[str, np.ndarray] = {}
    with rasterio.Env(**GDAL_ENV):
        for b in bands:
            meta = scene[b]
            with (
                rasterio.open(meta["href"]) as src,
                WarpedVRT(
                    src,
                    crs="EPSG:3857",
                    transform=tr,
                    width=grid["w"],
                    height=grid["h"],
                    resampling=Resampling.nearest if b == "scl" else Resampling.bilinear,
                ) as vrt,
            ):
                arr = vrt.read(1).astype(np.float64)
            if b == "scl":
                out[b] = arr
            else:
                refl = arr * meta["scale"] + meta["offset"]
                refl[arr == 0] = np.nan  # nodata
                out[b] = refl
    return out
