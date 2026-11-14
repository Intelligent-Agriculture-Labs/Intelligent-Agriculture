"""Fetch SMAP point time series for the demo sites from NASA AppEEARS (needs Earthdata Login).

    EARTHDATA_USER=... EARTHDATA_PASS=... python scripts/appeears_smap.py
    (or credentials in ~/.config/fieldshift/earthdata as "user:password", chmod 600)

Products (2015-03-31 → today):
  SPL3SMP_E.006  Enhanced L3 radiometer surface soil moisture (9 km, AM overpass)
  SPL4SMGP.008   L4 surface + root-zone soil moisture and root-zone percentile (9 km, 3-hourly → daily mean)

Output: backend/fieldshift/data/smap_points/<site>.json.gz  {"lat","lon","dates":[...],"l3e_sm":[...],
"l4_surface":[...],"l4_rootzone":[...],"l4_rootzone_pctl":[...]}  — committed (small), used for drought
status and validation. AppEEARS is asynchronous (minutes–hours), so this runs as a batch job on the data box.
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "fieldshift" / "data" / "smap_points"
API = "https://appeears.earthdatacloud.nasa.gov/api"
SITES = {
    "fallon_nv": (39.472, -118.777),
    "machakos_ke": (-1.517, 37.263),
    "cordoba_es": (37.885, -4.779),
    "ames_ia": (42.03, -93.62),
}
LAYERS = [
    {"product": "SPL3SMP_E.006", "layer": "Soil_Moisture_Retrieval_Data_AM_soil_moisture"},
    {"product": "SPL4SMGP.008", "layer": "Geophysical_Data_sm_surface"},
    {"product": "SPL4SMGP.008", "layer": "Geophysical_Data_sm_rootzone"},
    {"product": "SPL4SMGP.008", "layer": "Geophysical_Data_sm_rootzone_pctl"},
]
KEYS = {
    "Soil_Moisture_Retrieval_Data_AM_soil_moisture": "l3e_sm",
    "Geophysical_Data_sm_surface": "l4_surface",
    "Geophysical_Data_sm_rootzone": "l4_rootzone",
    "Geophysical_Data_sm_rootzone_pctl": "l4_rootzone_pctl",
}


def creds() -> tuple[str, str]:
    u, p = os.environ.get("EARTHDATA_USER"), os.environ.get("EARTHDATA_PASS")
    if u and p:
        return u, p
    f = Path.home() / ".config" / "fieldshift" / "earthdata"
    user, _, pw = f.read_text().strip().partition(":")
    return user, pw


def main() -> None:
    user, pw = creds()
    c = httpx.Client(timeout=120)
    tok = c.post(f"{API}/login", auth=(user, pw)).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    end = (dt.date.today() - dt.timedelta(days=3)).strftime("%m-%d-%Y")
    task = {
        "task_type": "point",
        "task_name": f"fieldshift-smap-{dt.date.today().isoformat()}",
        "params": {
            "dates": [{"startDate": "03-31-2015", "endDate": end}],
            "layers": LAYERS,
            "coordinates": [
                {"id": k, "latitude": v[0], "longitude": v[1], "category": "demo"} for k, v in SITES.items()
            ],
        },
    }
    tid = os.environ.get("APPEEARS_TASK_ID") or c.post(f"{API}/task", json=task, headers=h).json()["task_id"]
    print("task", tid, flush=True)
    while True:
        # /task/{id} returns the task document including its status (pending/queued/processing/done/error)
        try:
            st = c.get(f"{API}/task/{tid}", headers=h).json()
            status = st.get("status")
        except (httpx.HTTPError, ValueError) as e:
            print("poll error", e, flush=True)
            status = None
        print(dt.datetime.now().strftime("%H:%M"), status, flush=True)
        if status == "done":
            break
        if status in ("error", "expired"):
            sys.exit(f"AppEEARS task failed: {status}")
        time.sleep(60)
    files = c.get(f"{API}/bundle/{tid}", headers=h).json()["files"]
    rows: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for f in files:
        if not f["file_name"].endswith(".csv") or "results" not in f["file_name"].lower():
            continue
        r = c.get(f"{API}/bundle/{tid}/{f['file_id']}", headers=h, follow_redirects=True)
        rdr = csv.DictReader(io.StringIO(r.text))
        for row in rdr:
            site = row.get("ID")
            date = row.get("Date", "")[:10]
            for col, val in row.items():
                for layer, key in KEYS.items():
                    if col.endswith(layer) and val not in ("", None):
                        try:
                            v = float(val)
                        except ValueError:
                            continue
                        if -9000 < v < 9000 and v >= 0:
                            rows[site][date][key].append(v)
        print("parsed", f["file_name"], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for site, by_date in rows.items():
        dates = sorted(by_date)
        out = {
            "site": site,
            "lat": SITES[site][0],
            "lon": SITES[site][1],
            "source": "NASA SMAP via AppEEARS",
            "task_id": tid,
            "dates": dates,
        }
        for key in KEYS.values():
            out[key] = [
                round(sum(by_date[d][key]) / len(by_date[d][key]), 4) if by_date[d][key] else None
                for d in dates
            ]
        with gzip.open(OUT / f"{site}.json.gz", "wt") as fh:
            json.dump(out, fh, separators=(",", ":"))
        n = {k: sum(v is not None for v in out[k]) for k in KEYS.values()}
        print(site, len(dates), "days", n, flush=True)


if __name__ == "__main__":
    main()
