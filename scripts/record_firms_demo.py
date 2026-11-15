"""Record NASA FIRMS detections for a box as offline demo data (backend/fieldshift/data/firms_demo/).

Usage (CSV files from the keyless 7-day FIRMS text feeds, e.g.
https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_Asia_7d.csv):

    python scripts/record_firms_demo.py NAME W S E N file1.csv [file2.csv ...]
"""

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fieldshift.data.firms import parse_csv  # noqa: E402

name, w, s, e, n, *files = sys.argv[1:]
w, s, e, n = map(float, (w, s, e, n))
rows = []
for fn in files:
    for f in parse_csv(Path(fn).read_text()):
        if s <= f.lat <= n and w <= f.lon <= e:
            rows.append([round(f.lat, 4), round(f.lon, 4), f.date.isoformat(), f.time_utc, f.satellite, f.confidence, round(f.frp_mw, 1), f.daynight])
dates = sorted({r[2] for r in rows})
out = {
    "name": name,
    "note": "Recorded from the public NASA FIRMS 7-day text feeds (VIIRS NOAA-20, VIIRS NOAA-21, MODIS C6.1 NRT).",
    "bbox": [w, s, e, n],
    "start": dates[0],
    "end": dates[-1],
    "columns": ["lat", "lon", "date", "time", "sat", "conf", "frp", "dn"],
    "fires": rows,
}
dst = Path(__file__).resolve().parents[1] / "backend/fieldshift/data/firms_demo" / f"{name}.json.gz"
dst.parent.mkdir(parents=True, exist_ok=True)
with gzip.open(dst, "wt", encoding="utf-8") as fh:
    json.dump(out, fh, separators=(",", ":"))
print(dst, len(rows), dates[0], dates[-1])
