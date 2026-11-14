"""Fetch the imagery for the cinematic demo film (not committed; re-run to rebuild):
* NASA GIBS Blue Marble (shaded relief + bathymetry), equirectangular, for the 3D globe;
* Esri World Imagery mosaics (9 x 7 tiles) centred on the Fallon demo field at zoom 3..18, for the orbit-to-field dive.
"""

from __future__ import annotations

import io
import json
import math
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent / "assets"
LAT, LON = 39.44087, -118.83012  # Fallon, Nevada demo field (centre)
UA = {"User-Agent": "FieldShift-film/1.0"}
try:
    import certifi

    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()
NX, NY = 9, 7


def get(url: str) -> bytes:
    err: Exception | None = None
    for _ in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX).read()
        except Exception as e:  # noqa: BLE001
            err = e
            continue
    raise RuntimeError(f"{url}: {err}")


def tile_xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2**z
    x = (lon + 180) / 360 * n
    r = math.radians(lat)
    y = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n
    return x, y


def mosaic(z: int) -> dict:
    fx, fy = tile_xy(LAT, LON, z)
    cx, cy = int(fx), int(fy)
    x0, y0 = cx - NX // 2, cy - NY // 2
    img = Image.new("RGB", (NX * 256, NY * 256))
    n = 2**z

    def one(ij: tuple[int, int]) -> None:
        i, j = ij
        tx, ty = (x0 + i) % n, y0 + j
        if not 0 <= ty < n:
            return
        b = get(f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{ty}/{tx}")
        img.paste(Image.open(io.BytesIO(b)).convert("RGB"), (i * 256, j * 256))

    with ThreadPoolExecutor(12) as ex:
        list(ex.map(one, [(i, j) for i in range(NX) for j in range(NY)]))
    img.save(OUT / f"z{z:02d}.jpg", quality=90)
    return {"z": z, "px": (fx - x0) * 256, "py": (fy - y0) * 256, "w": NX * 256, "h": NY * 256}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    gibs = (
        "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0"
        "&LAYERS=BlueMarble_ShadedRelief_Bathymetry&STYLES=&CRS=EPSG:4326&BBOX=-90,-180,90,180&WIDTH=4096&HEIGHT=2048&FORMAT=image/jpeg"
    )
    (OUT / "bluemarble.jpg").write_bytes(get(gibs))
    levels = [mosaic(z) for z in range(3, 19)]
    # field outline in z18 mosaic pixels (for drawing it on the imagery)
    presets = json.loads((OUT.parent / "fallon_polygon.json").read_text())
    z = 18
    fx, fy = tile_xy(LAT, LON, z)
    x0, y0 = int(fx) - NX // 2, int(fy) - NY // 2
    poly = []
    for lon, lat in presets:
        x, y = tile_xy(lat, lon, z)
        poly.append([(x - x0) * 256, (y - y0) * 256])
    (OUT / "levels.json").write_text(json.dumps({"levels": levels, "poly_z18": poly}))
    print("ok", len(levels), "levels")


if __name__ == "__main__":
    main()
