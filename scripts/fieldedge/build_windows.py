"""Training windows for the field-edge model (EXP-12).

Each window is a 3 x 3 block of 256-px web-mercator tiles at zoom 17 (or 16 with Z=16), the same geometry as the
app's Esri mosaics, centred on a Fields of The World (FTW) chip. Saved per window: RGB, field extent, field
boundaries (3 px) and the chip footprint (labels are only valid inside it).

Imagery is OPEN national orthophotography of the four benchmark DEV countries only, never Esri imagery:
  France: IGN BD ORTHO via Géoplateforme WMTS (Licence Ouverte / Etalab 2.0)
  Spain: PNOA máxima actualidad, IGN/CNIG (CC-BY 4.0, scne.es)
  Netherlands: PDOK Luchtfoto RGB, Beeldmateriaal Nederland (CC-BY 4.0)
  Austria: basemap.at orthophoto (CC-BY 4.0, basemap.at)
Labels: FTW boundaries_<country>.parquet (France: IGN RPG, Licence Ouverte; Spain: CC-BY-4.0;
Netherlands: CC0-1.0; Austria: CC-BY-4.0). Windows within ~3 km of a benchmark field are skipped.

    python build_windows.py france 700          # zoom 17
    Z=16 python build_windows.py france 350     # zoom 16 (large fields, the app's retry zoom)
Expects the FTW parquet files in ~/fd_bench/ftw (see scripts/field_benchmark.py).
"""

import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import box

B = os.path.expanduser("~/fd_bench")
OUT = f"{B}/train"
TILES = f"{B}/train_tiles"
os.makedirs(OUT, exist_ok=True)
os.makedirs(TILES, exist_ok=True)
SRC = {
    "france": (
        "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg",
        "boundaries_france_2020.parquet",
    ),
    "spain": (
        "https://www.ign.es/wmts/pnoa-ma?request=GetTile&service=WMTS&VERSION=1.0.0&Layer=OI.OrthoimageCoverage&Style=default&Format=image/jpeg&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}",
        "boundaries_spain_2020.parquet",
    ),
    "netherlands": (
        "https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0/Actueel_orthoHR/EPSG:3857/{z}/{x}/{y}.jpeg",
        "boundaries_netherlands_2022.parquet",
    ),
    "austria": (
        "https://maps.wien.gv.at/basemap/bmaporthofoto30cm/normal/google3857/{z}/{y}/{x}.jpeg",
        "boundaries_austria_2021.parquet",
    ),
}
Z = int(os.environ.get("Z", 17))
cli = httpx.Client(timeout=30, headers={"User-Agent": "FieldShift-research/1.0 (field boundary benchmark)"})


def lonlat_to_tile(lon, lat, z):
    n = 2**z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def tile_to_lonlat(x, y, z):
    n = 2**z
    return x / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def tile(c, x, y):
    p = f"{TILES}/{c}_{Z}_{x}_{y}.jpg"
    if not os.path.exists(p):
        for a in range(4):
            try:
                r = cli.get(SRC[c][0].format(z=Z, x=x, y=y))
                if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                    Path(p).write_bytes(r.content)
                    break
            except Exception:
                pass
            time.sleep(2 * (a + 1))
        else:
            return None
    try:
        return np.asarray(Image.open(p).convert("RGB"))
    except Exception:
        return None


def rasterise(polys, x0, y0, shape):
    ext = Image.new("L", (shape[1], shape[0]), 0)
    bnd = Image.new("L", (shape[1], shape[0]), 0)
    de, db = ImageDraw.Draw(ext), ImageDraw.Draw(bnd)

    def px(ring):
        return [
            ((lonlat_to_tile(lo, la, Z)[0] - x0) * 256, (lonlat_to_tile(lo, la, Z)[1] - y0) * 256)
            for lo, la in ring.coords
        ]

    for g in polys:
        for p in [g] if g.geom_type == "Polygon" else g.geoms:
            de.polygon(px(p.exterior), fill=1)
            for i in p.interiors:
                de.polygon(px(i), fill=0)
    for g in polys:
        for p in [g] if g.geom_type == "Polygon" else g.geoms:
            for ring in [p.exterior, *p.interiors]:
                db.line(px(ring), fill=1, width=3)
    return np.asarray(ext), np.asarray(bnd)


def main(country, n):
    chips = gpd.read_parquet(f"{B}/ftw/chips_{country}.parquet").to_crs(4326)
    fields = gpd.read_parquet(f"{B}/ftw/{SRC[country][1]}")[["geometry"]].to_crs(4326)
    sample = gpd.read_parquet(f"{B}/bench/sample.parquet")
    sample = sample[sample.country == country]
    taps = gpd.GeoSeries(gpd.points_from_xy(sample.tap_lon, sample.tap_lat), crs=4326)
    sidx = fields.sindex
    rng = np.random.default_rng(7 + Z)
    order = rng.permutation(len(chips))
    made = 0
    for ci in order:
        if made >= n:
            break
        ch = chips.geometry.iloc[ci]
        c = ch.centroid
        if len(taps) and taps.distance(c).min() < 0.03:
            continue  # ~3 km from any benchmark field
        fx, fy = lonlat_to_tile(c.x, c.y, Z)
        cx, cy = int(fx), int(fy)
        x0, y0 = cx - 1, cy - 1
        with ThreadPoolExecutor(9) as ex:
            fut = {
                (x, y): ex.submit(tile, country, x, y) for y in range(y0, y0 + 3) for x in range(x0, x0 + 3)
            }
            imgs = [[fut[(x, y)].result() for x in range(x0, x0 + 3)] for y in range(y0, y0 + 3)]
        if any(t is None or t.shape[:2] != (256, 256) for row in imgs for t in row):
            continue
        img = np.vstack([np.hstack(row) for row in imgs])
        if (img.std(axis=2) < 1).mean() > 0.2:
            continue  # nodata / blank
        lo0, la0 = tile_to_lonlat(x0, y0, Z)
        lo1, la1 = tile_to_lonlat(x0 + 3, y0 + 3, Z)
        win = box(lo0, la1, lo1, la0)
        polys = [fields.geometry.iloc[i] for i in sidx.query(win, predicate="intersects")]
        ext, bnd = rasterise(polys, x0, y0, img.shape)
        valid, _ = rasterise([ch], x0, y0, img.shape)
        if ext[valid > 0].mean() < 0.15:
            continue
        pxm = 40075016.686 * math.cos(math.radians(c.y)) / 2**Z / 256
        np.savez_compressed(
            f"{OUT}/{country}_" + ("z16_" if Z == 16 else "") + f"{ci}.npz",
            img=img,
            ext=ext,
            bnd=bnd,
            valid=valid,
            pxm=pxm,
            lat=c.y,
        )
        made += 1
        if made % 50 == 0:
            print(country, made, flush=True)
    print(country, "done", made, flush=True)


if __name__ == "__main__":
    c = sys.argv[1]
    n = int(sys.argv[2])
    import urllib.request

    p = f"{B}/ftw/chips_{c}.parquet"
    if not os.path.exists(p):
        urllib.request.urlretrieve(
            f"https://data.source.coop/kerner-lab/fields-of-the-world/{c}/chips_{c}.parquet", p
        )
    main(c, n)
