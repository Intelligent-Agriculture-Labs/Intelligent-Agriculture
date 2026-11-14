"""DEM tiles: AWS Terrain Tiles (terrarium PNG, public, no auth; built from NASA SRTM plus national DEMs such as
USGS 3DEP/NED, ETOPO for bathymetry). We fetch a 3×3 block of zoom-14 web-mercator tiles around the field.
Pixel size ≈ 9.5 m × cos(lat); the true source resolution is ~30 m (SRTM) outside the US, 10 m (3DEP) in the US.
"""

from __future__ import annotations

import io
import math
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
from PIL import Image

from .http import CACHE_DIR, DEMO_DIR, offline_mode

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM = 14


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2**z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def tile_to_lonlat(x: float, y: float, z: int) -> tuple[float, float]:
    n = 2**z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def _tile(z: int, x: int, y: int) -> np.ndarray:
    name = f"dem_{z}_{x}_{y}.png"
    for d in (CACHE_DIR / "dem", DEMO_DIR / "dem"):
        p = d / name
        if p.exists():
            raw = p.read_bytes()
            break
    else:
        if offline_mode():
            raise FileNotFoundError(name)
        r = httpx.get(TILE_URL.format(z=z, x=x, y=y), timeout=30, headers={"User-Agent": "FieldShift/1.0"})
        r.raise_for_status()
        raw = r.content
        (CACHE_DIR / "dem").mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / "dem" / name).write_bytes(raw)
    rgb = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=np.float64)
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def dem_around(lat: float, lon: float, half: int = 1) -> tuple[np.ndarray, dict[str, float]]:
    """(2·half+1)² tiles centred on the field. Returns DEM (m) and bounds/pixel size."""
    fx, fy = lonlat_to_tile(lon, lat, ZOOM)
    cx, cy = int(fx), int(fy)
    xs = range(cx - half, cx + half + 1)
    ys = range(cy - half, cy + half + 1)
    with ThreadPoolExecutor(max_workers=9) as ex:
        tiles = {(x, y): ex.submit(_tile, ZOOM, x, y) for y in ys for x in xs}
        rows = [np.hstack([tiles[(x, y)].result() for x in xs]) for y in ys]
    dem = np.vstack(rows)
    west, north = tile_to_lonlat(cx - half, cy - half, ZOOM)
    east, south = tile_to_lonlat(cx + half + 1, cy + half + 1, ZOOM)
    cell = 40075016.686 * math.cos(math.radians(lat)) / (2**ZOOM) / 256
    return dem, {
        "west": west,
        "east": east,
        "north": north,
        "south": south,
        "cell_m": cell,
        "x0": float(cx - half),
        "y0": float(cy - half),
        "zoom": float(ZOOM),
    }


def lonlat_to_px(lon: float, lat: float, meta: dict[str, float]) -> tuple[float, float]:
    x, y = lonlat_to_tile(lon, lat, int(meta["zoom"]))
    return (x - meta["x0"]) * 256, (y - meta["y0"]) * 256
