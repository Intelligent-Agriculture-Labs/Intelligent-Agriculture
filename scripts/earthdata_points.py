"""Point time series of SMAP L4 soil moisture and ECOSTRESS / MODIS ET for the demo sites, straight from NASA archives.

Replaces the AppEEARS batch route (scripts/appeears_smap.py), whose point requests sat queued for more than a day.
Run on the data box (needs Earthdata Login, see backend/fieldshift/data/earthdata.py):

    FIELDSHIFT_CACHE_DIR=~/fs-live-cache backend/.venv/bin/python scripts/earthdata_points.py smap
    FIELDSHIFT_CACHE_DIR=~/fs-live-cache backend/.venv/bin/python scripts/earthdata_points.py et

smap → backend/fieldshift/data/smap_points/<site>.json.gz
       SPL4SMGP.008 via NSIDC cloud OPeNDAP, one 3-hourly analysis per day (10:30 UTC), every 2nd day 2015-04 → today
       keys: dates, l4_rootzone, l4_surface, l4_rootzone_pctl (+ l3e_sm = null: the L3E product is not extracted)
et   → backend/fieldshift/data/et_points/<preset>.json.gz
       ECO_L3T_JET.002 ETdaily (70 m, every clear overpass 2018-07 → today, LP DAAC COGs) and
       MOD16A2GF.061 ET_500m (500 m, 8-day, 2015 →, LP DAAC cloud OPeNDAP)
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldshift.data import earthdata  # noqa: E402
from fieldshift.data.http import DataUnavailable  # noqa: E402

DATA = ROOT / "backend" / "fieldshift" / "data"
SMAP_SITES = {  # same points as the former AppEEARS request and scripts/validate.py
    "fallon_nv": (39.472, -118.777),
    "machakos_ke": (-1.517, 37.263),
    "cordoba_es": (37.885, -4.779),
    "ames_ia": (42.03, -93.62),
}
SMAP_START = dt.date(2015, 4, 1)
ECO_START = dt.date(2018, 7, 1)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        json.dump(payload, fh, separators=(",", ":"))


def smap(sites: dict[str, tuple[float, float]]) -> None:
    end = dt.date.today() - dt.timedelta(days=2)
    for site, (lat, lon) in sites.items():
        t0 = time.time()
        rows: list[dict] = []
        y0 = SMAP_START
        while y0 <= end:  # one CMR query per year (≤ 366 granules at one analysis time)
            y1 = min(end, dt.date(y0.year, 12, 31))
            try:
                got, _ = earthdata.smap_l4_series(lat, lon, y0, y1, every_days=2, max_workers=16)
                rows.extend(got)
            except DataUnavailable as e:
                print(site, y0.year, "unavailable:", e, flush=True)
            print(site, y0.year, len(rows), f"{time.time() - t0:.0f}s", flush=True)
            y0 = y1 + dt.timedelta(days=1)
        rows.sort(key=lambda r: r["date"])
        out = {
            "site": site,
            "lat": lat,
            "lon": lon,
            "source": "NASA SMAP L4 SPL4SMGP.008 (NSIDC cloud OPeNDAP, 10:30 UTC analysis, every 2nd day)",
            "row_col": list(earthdata.ease2_m09(lat, lon)),
            "dates": [r["date"] for r in rows],
            "l3e_sm": [None] * len(rows),
            "l4_surface": [r.get("surface") for r in rows],
            "l4_rootzone": [r.get("rootzone") for r in rows],
            "l4_rootzone_pctl": [r.get("rootzone_pctl") for r in rows],
        }
        _write(DATA / "smap_points" / f"{site}.json.gz", out)
        print(site, "written", len(rows), "days", flush=True)


def et() -> None:
    from fieldshift.engine import service

    end = dt.date.today()
    for p in service.presets():
        site, lat, lon = p["id"], p["lat"], p["lon"]
        t0 = time.time()
        eco: dict[str, float] = {}
        y0 = ECO_START
        while y0 <= end:
            y1 = min(end, dt.date(y0.year, 12, 31))
            try:
                got, _ = earthdata.ecostress_et(lat, lon, y0, y1, max_workers=12)
                eco.update({d.isoformat(): round(v, 3) for d, v in got})
            except DataUnavailable as e:
                print(site, y0.year, "ECOSTRESS unavailable:", e, flush=True)
            print(
                site, y0.year, "ECOSTRESS clear days so far", len(eco), f"{time.time() - t0:.0f}s", flush=True
            )
            y0 = y1 + dt.timedelta(days=1)
        mod: dict[str, float] = {}
        try:  # LP DAAC cloud OPeNDAP (ORNL's subset service returned HTTP 503 on 2026-11-15)
            for d, v in earthdata.mod16_8day(lat, lon, dt.date(2015, 1, 1), end, max_workers=12):
                mod[d.isoformat()] = round(v, 2)
        except DataUnavailable as e:
            print(site, "MOD16 unavailable:", e, flush=True)
        print(site, "MOD16 8-day values", len(mod), flush=True)
        dates = sorted(set(eco) | set(mod))
        out = {
            "site": site,
            "lat": lat,
            "lon": lon,
            "source": "NASA ECOSTRESS ECO_L3T_JET.002 ETdaily (LP DAAC) + MODIS MOD16A2GF.061 (LP DAAC OPeNDAP)",
            "dates": dates,
            "eco_et_daily": [eco.get(d) for d in dates],
            "mod16_et_8day": [mod.get(d) for d in dates],
        }
        _write(DATA / "et_points" / f"{site}.json.gz", out)
        print(site, "written", len(eco), "ECOSTRESS days,", len(mod), "MOD16 composites", flush=True)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "smap"
    if what == "smap":
        only = set(sys.argv[2:])
        smap({k: v for k, v in SMAP_SITES.items() if not only or k in only})
    elif what == "et":
        et()
    else:
        sys.exit("usage: earthdata_points.py smap|et [site ...]")
