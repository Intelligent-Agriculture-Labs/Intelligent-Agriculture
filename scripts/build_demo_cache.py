"""Warm the data cache for every demo preset and copy it into backend/demo_cache (committed).

Run on the data box (VPS, Earthdata Login in ~/.config/fieldshift/earthdata), in a fresh clone, with an empty cache:

    export FIELDSHIFT_CACHE_DIR=$(mktemp -d)
    backend/.venv/bin/python scripts/verify_offline_demo.py --online   # every request the app makes, all languages
    FIELDSHIFT_ORNL_RETRIES=6 backend/.venv/bin/python scripts/build_demo_cache.py
    FIELDSHIFT_CACHE_DIR=$(mktemp -d) backend/.venv/bin/python scripts/cache_earthdata_demo.py

then copy backend/demo_cache back and check it offline with scripts/verify_offline_demo.py.
It fetches NASA POWER (1984→today), forecast, SRTM, SoilGrids and the ORNL DAAC satellite layers
(MODIS NDVI 2001→, MOD16 ET, SMAP, LST) patiently, runs every endpoint once, then copies the cache files.
New entries are merged into demo_cache/index.json (same key = replaced; older entries stay, so the offline fuzzy
match keeps them as a fallback and prefers the newest date range).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("FIELDSHIFT_ORNL_RETRIES", "6")

from fieldshift.data import http, sources  # noqa: E402
from fieldshift.engine import context, service  # noqa: E402

if "--enrich-only" in sys.argv:  # satellite layers only, one site per process (run in parallel)
    for p in service.presets():
        if p["id"] in sys.argv:
            for d in (
                None,
                {
                    "fallon_nv": "2025-07-15",
                    "machakos_ke": "2025-11-20",
                    "cordoba_es": "2025-04-10",
                    "ames_ia": "2025-07-20",
                }[p["id"]],
            ):
                t = dt.date.fromisoformat(d) if d else dt.date.today()
                e = context.enrichment(p["lat"], p["lon"], t)
                print(p["id"], d, {k: len(v) for k, v in e.items()}, flush=True)
    sys.exit(0)

# summer replay dates used by the demo (irrigation season; documented in docs/USER_GUIDE.md)
REPLAY = {
    "fallon_nv": "2025-07-15",
    "machakos_ke": "2025-11-20",
    "cordoba_es": "2025-04-10",
    "ames_ia": "2025-07-20",
}


def main() -> None:
    only = {a for a in sys.argv[1:] if not a.startswith("--")}
    for p in service.presets():
        if only and p["id"] not in only:
            continue
        t0 = time.time()
        print(f"== {p['id']}", flush=True)
        for as_of in (None, REPLAY.get(p["id"])):
            today = dt.date.fromisoformat(as_of) if as_of else dt.date.today()
            if "--no-enrich" not in sys.argv:
                enr = context.enrichment(p["lat"], p["lon"], today)
                print("   enrichment", as_of, {k: len(v) for k, v in enr.items()}, flush=True)
            inp = {
                "lat": p["lat"],
                "lon": p["lon"],
                "crop": p["crop"],
                "planting_date": p["planting_date"],
                "irrigation": p["irrigation"],
                "as_of": as_of,
                "enrich_timeout_s": 5 if "--no-enrich" in sys.argv else 900,
            }
            a = service.advice(inp)
            print("   advice", as_of, [c["title"] for c in a["cards"]], flush=True)
            for lang in ("es", "fr", "sw", "hi", "de"):
                service.advice({**inp, "lang": lang})
        service.climate_api(p["lat"], p["lon"])
        r = service.rotations_api(
            {
                "lat": p["lat"],
                "lon": p["lon"],
                "current_rotation": p["current_rotation"],
                "irrigation": p["irrigation"],
            }
        )
        print("   rotations", [(s["name"], s["total_score"]) for s in r["strategies"]], flush=True)
        s = service.simulate_api(
            {
                "lat": p["lat"],
                "lon": p["lon"],
                "crop": p["crop"],
                "planting_date": p["planting_date"],
                "irrigation_strategy": "full" if p["irrigation"] != "none" else "rainfed",
                "irrigation_method": p["irrigation"] if p["irrigation"] != "none" else "sprinkler",
            }
        )
        print("   simulate", s["summary"], flush=True)
        sources.soil(p["lat"], p["lon"])
        from fieldshift.engine import maps, planner

        t = maps.terrain_api(
            {"lat": p["lat"], "lon": p["lon"], "crop": p["crop"], "polygon": p.get("polygon")}
        )
        print("   terrain", [(z["label"], z["share_pct"]) for z in t["zones"]], flush=True)
        pl = planner.planner_api(
            {
                "lat": p["lat"],
                "lon": p["lon"],
                "crop": p["crop"],
                "planting_date": p["planting_date"],
                "irrigation": p["irrigation"],
            }
        )
        print("   planner", pl["window"], len(pl["operations"]), "ops", flush=True)
        from fieldshift.engine import satellite_service

        sreq = {"lat": p["lat"], "lon": p["lon"], "polygon": p.get("polygon"), "crop": p["crop"]}
        for _ in range(240):
            sr = satellite_service.satellite_api(sreq)
            if sr["status"] != "processing":
                break
            time.sleep(5)
        print(
            "   satellite",
            sr["status"],
            sr.get("phenology"),
            (sr.get("zones") or {}).get("legend"),
            sr.get("message"),
            flush=True,
        )
        print(f"   done in {time.time() - t0:.0f}s", flush=True)

    # copy cache -> demo_cache (only gz payloads + index); keep demo_cache small: skip files > 8 MB
    http.DEMO_DIR.mkdir(parents=True, exist_ok=True)
    idx = json.loads((http.CACHE_DIR / "index.json").read_text())
    idx_f = http.DEMO_DIR / "index.json"
    old = json.loads(idx_f.read_text()) if idx_f.exists() else {}
    kept = {k: m for k, m in old.items() if (http.DEMO_DIR / f"{k}.json.gz").exists()}
    n_new = 0
    for key, meta in idx.items():
        src = http.CACHE_DIR / f"{key}.json.gz"
        if src.exists() and src.stat().st_size < 8_000_000:
            shutil.copy2(src, http.DEMO_DIR / src.name)
            kept[key] = meta
            n_new += 1
    idx_f.write_text(json.dumps(kept, default=str))
    for sub in ("dem", "satellite"):  # elevation tiles (terrain maps) and satellite analyses (offline)
        if (http.CACHE_DIR / sub).exists():
            shutil.copytree(http.CACHE_DIR / sub, http.DEMO_DIR / sub, dirs_exist_ok=True)
    total = sum(f.stat().st_size for f in http.DEMO_DIR.glob("*.gz"))
    print(f"demo_cache: {n_new} files copied, {len(kept)} indexed, {total / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
