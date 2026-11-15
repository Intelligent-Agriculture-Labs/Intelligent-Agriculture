"""Add the GPM IMERG extracts (NASA POWER IMERG_PRECTOT) for the demo presets to backend/demo_cache.

    cd backend && .venv/bin/python ../scripts/cache_imerg_demo.py

scripts/build_demo_cache.py picks IMERG up automatically from now on (context.build fetches it); this script only
adds the new entries without re-running the whole precompute. It requests exactly what the app requests (live
date and the demo replay date), copies those cache files into demo_cache and merges demo_cache/index.json.
GRACE needs no demo cache: its global asset (fieldshift/data/grace/) is committed and read offline.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldshift.data import http, sources  # noqa: E402
from fieldshift.engine import context, service  # noqa: E402

REPLAY = {
    "fallon_nv": "2025-07-15",
    "machakos_ke": "2025-11-20",
    "cordoba_es": "2025-04-10",
    "ames_ia": "2025-07-20",
}


def main() -> None:
    keys: list[str] = []
    today = dt.date.today()
    for p in service.presets():
        for as_of in (None, REPLAY.get(p["id"])):
            t = dt.date.fromisoformat(as_of) if as_of else today
            end = (
                min(t + dt.timedelta(days=200), today) if (today - t).days > 30 else today
            )  # as context._build
            got = sources.imerg_daily(p["lat"], p["lon"], context.HIST_START, end)
            assert got is not None, f"IMERG unavailable for {p['id']}"
            s0 = max(context.HIST_START, sources.IMERG_START)
            params = {
                "parameters": "IMERG_PRECTOT",
                "community": "AG",
                "latitude": round(p["lat"], 3),
                "longitude": round(p["lon"], 3),
                "start": s0.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "format": "JSON",
                "time-standard": "UTC",
            }
            keys.append(http.cache_key(sources.POWER_URL, params))
            arr = got[0]
            print(p["id"], as_of or "live", f"{int((arr == arr).sum())} IMERG days, status {got[1]}")
    idx_src = json.loads((http.CACHE_DIR / "index.json").read_text())
    idx_f = http.DEMO_DIR / "index.json"
    idx = json.loads(idx_f.read_text()) if idx_f.exists() else {}
    for k in keys:
        shutil.copy2(http.CACHE_DIR / f"{k}.json.gz", http.DEMO_DIR / f"{k}.json.gz")
        idx[k] = idx_src[k]
    idx_f.write_text(json.dumps(idx, default=str))
    print(f"copied {len(set(keys))} files into {http.DEMO_DIR}")


if __name__ == "__main__":
    main()
