"""Add the live Earthdata layers of the demo presets (IMERG Late/Early, SMAP L4, ECOSTRESS, GRACE-DA) to
backend/demo_cache, so the offline demo (FIELDSHIFT_OFFLINE=1) shows them too.

    FIELDSHIFT_CACHE_DIR=$(mktemp -d) backend/.venv/bin/python scripts/cache_earthdata_demo.py

Run on the data box (Earthdata Login) with an EMPTY cache directory: everything requested lands in it, and all of it is
copied into demo_cache with merged index entries. Cache keys are URL + parameters only (no credentials or tokens).
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
from fieldshift.engine import context, live_layers, service  # noqa: E402

REPLAY = {  # as scripts/build_demo_cache.py
    "fallon_nv": "2025-07-15",
    "machakos_ke": "2025-11-20",
    "cordoba_es": "2025-04-10",
    "ames_ia": "2025-07-20",
}


def main() -> None:
    assert not any(http.CACHE_DIR.glob("*.json.gz")), "use an empty FIELDSHIFT_CACHE_DIR"
    today = dt.date.today()
    for p in service.presets():
        for as_of in (None, REPLAY.get(p["id"])):
            t = dt.date.fromisoformat(as_of) if as_of else today
            end = (
                min(t + dt.timedelta(days=200), today) if (today - t).days > 30 else today
            )  # as context._build
            if (today - end).days < context.NRT_DAYS:
                nrt = sources.imerg_nrt(p["lat"], p["lon"], end - dt.timedelta(days=context.NRT_DAYS), end)
                print(
                    p["id"],
                    as_of or "live",
                    "IMERG NRT days",
                    0 if nrt is None else int((nrt[0] == nrt[0]).sum()),
                )
            live = live_layers.fetch(p["lat"], p["lon"], t, timeout_s=600)
            print(
                p["id"],
                as_of or "live",
                {k: len(v) for k, v in live.items() if k != "_status"},
                live["_status"],
            )
    idx_src = json.loads((http.CACHE_DIR / "index.json").read_text())
    idx_f = http.DEMO_DIR / "index.json"
    idx = json.loads(idx_f.read_text()) if idx_f.exists() else {}
    n = 0
    for k, meta in idx_src.items():
        src = http.CACHE_DIR / f"{k}.json.gz"
        if src.exists():
            shutil.copy2(src, http.DEMO_DIR / f"{k}.json.gz")
            idx[k] = meta
            n += 1
    idx_f.write_text(json.dumps(idx, default=str))
    print(f"copied {n} files into {http.DEMO_DIR}")


if __name__ == "__main__":
    main()
