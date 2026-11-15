"""Check the committed offline demo: every endpoint the app calls, for all presets, in every language, with
FIELDSHIFT_OFFLINE=1, an EMPTY disk cache (only backend/demo_cache is used) and outbound network blocked.

    backend/.venv/bin/python scripts/verify_offline_demo.py                    # all presets, all languages
    backend/.venv/bin/python scripts/verify_offline_demo.py ames_ia es         # subset
    backend/.venv/bin/python scripts/verify_offline_demo.py --today 2026-12-01 # pretend it is a later day

`--online` instead runs the same requests live against $FIELDSHIFT_CACHE_DIR (no offline mode, network allowed):
scripts/build_demo_cache.py uses that to warm the cache with exactly what the app requests.

Exit code 1 if any request fails or returns empty content. Live Earthdata layers, satellite and terrain maps that
come back without data count as failures too, since the demo must show them offline.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONLINE = "--online" in sys.argv
if not ONLINE:
    os.environ["FIELDSHIFT_OFFLINE"] = "1"
    os.environ["FIELDSHIFT_CACHE_DIR"] = tempfile.mkdtemp(prefix="fs-offline-cache-")
os.environ.setdefault("FIELDSHIFT_DB", str(Path(tempfile.mkdtemp(prefix="fs-verify-db-")) / "farms.db"))
sys.path.insert(0, str(ROOT / "backend"))

if "--today" in sys.argv:  # pretend "today" is a later day (the demo must keep working after the cache build)
    _fake = _dt.date.fromisoformat(sys.argv[sys.argv.index("--today") + 1])

    class _Date(_dt.date):
        @classmethod
        def today(cls) -> _dt.date:  # type: ignore[override]
            return _fake

    _dt.date = _Date  # type: ignore[misc]


def _no_net(*_a: object, **_k: object) -> None:
    raise OSError("network blocked by verify_offline_demo")


if not ONLINE:
    _real_connect = socket.socket.connect

    def _connect(self: socket.socket, addr: object) -> None:
        if self.family == socket.AF_UNIX:
            return _real_connect(self, addr)
        _no_net()

    socket.socket.connect = _connect  # type: ignore[method-assign]
    socket.create_connection = _no_net  # type: ignore[assignment]
    socket.getaddrinfo = _no_net  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from fieldshift.engine import service  # noqa: E402
from fieldshift.main import app  # noqa: E402

LANGS = ("en", "es", "fr", "sw", "hi", "de")
# real data gaps at build time (checked live on the data box), not cache misses:
# Córdoba had no clear ECOSTRESS overpass in the 60 days before 2026-11-15
KNOWN_GAPS = {("cordoba_es", "today", "ecostress")}
LIVE_LAYERS = ("smap_l4", "ecostress", "grace_da", "gpm_imerg_nrt")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--") and not re.fullmatch(r"\d{4}-\d\d-\d\d", a)]
    ids = {q["id"] for q in service.presets()}
    presets = [p for p in service.presets() if p["id"] in args or not ids & set(args)]
    langs = [lng for lng in LANGS if lng in args] or list(LANGS)
    c = TestClient(app)
    fails: list[str] = []
    notes: list[str] = []
    n_ok = 0

    def check(name: str, r: object, ok: bool, why: str = "") -> None:
        nonlocal n_ok
        code = getattr(r, "status_code", None)
        if code == 200 and ok:
            n_ok += 1
        else:
            body = getattr(r, "text", "")[:200]
            fails.append(f"{name}: HTTP {code} {why} {body if code != 200 else ''}".strip())

    for path in ("/api/health", "/api/crops", "/api/presets"):
        r = c.get(path)
        check(path, r, bool(r.json()))
    for p in presets:
        lat, lon, poly = p["lat"], p["lon"], p.get("polygon")
        for lang in langs:
            tag = f"{p['id']}/{lang}"
            r = c.get("/api/glossary", params={"lang": lang})
            check(f"{tag} glossary", r, len(r.json()) > 10)
            for as_of in (None, p.get("replay_date")):
                fi = {
                    "lat": lat,
                    "lon": lon,
                    "crop": p["crop"],
                    "planting_date": p["planting_date"],
                    "irrigation": p["irrigation"],
                    "polygon": poly,
                    "water_allocation_mm": None,
                    "lang": lang,
                    "as_of": as_of,
                    "last_irrigation_date": None,
                    "last_irrigation_mm": None,
                }
                mode = as_of or "today"
                t0 = time.time()
                r = c.post("/api/advice", json=fi)
                dt_s = time.time() - t0
                if r.status_code == 200:
                    a = r.json()
                    st = {s["id"]: s["status"] for s in a["sources"]}
                    missing = [
                        s
                        for s in ("nasa_power", "openmeteo_forecast", "srtm", "soilgrids")
                        if st.get(s) == "unavailable"
                    ]
                    want = (
                        LIVE_LAYERS if as_of is None else LIVE_LAYERS[:-1]
                    )  # IMERG NRT only for recent days
                    live_missing = [
                        s
                        for s in want
                        if st.get(s) in (None, "unavailable") and (p["id"], mode, s) not in KNOWN_GAPS
                    ]
                    ok = bool(a["cards"]) and bool(a["series"]) and not missing and not live_missing
                    check(
                        f"{tag} advice {mode}",
                        r,
                        ok,
                        f"cards={len(a['cards'])} missing={missing} live_missing={live_missing}",
                    )
                    if lang == "en":
                        notes.append(
                            f"{p['id']:12} advice {mode:10} {dt_s:4.1f}s cards={len(a['cards'])} "
                            + " ".join(f"{k}={v}" for k, v in st.items())
                        )
                else:
                    check(f"{tag} advice {mode}", r, False)
                r = c.post("/api/advice/text", json=fi, params={"name": p["name"], "max_chars": 320})
                check(f"{tag} advice/text {mode}", r, r.status_code == 200 and len(r.json()["text"]) > 40)
                q = {
                    "lat": lat,
                    "lon": lon,
                    "crop": p["crop"],
                    "planting_date": p["planting_date"],
                    "irrigation": p["irrigation"],
                }
                if lang == "en":
                    r = c.get("/api/export/advice.csv", params={**q, **({"as_of": as_of} if as_of else {})})
                    check(f"{tag} export csv {mode}", r, r.status_code == 200 and r.text.count("\n") > 100)
                    r = c.get(
                        "/api/export/field.geojson", params={**q, **({"as_of": as_of} if as_of else {})}
                    )
                    check(
                        f"{tag} export geojson {mode}", r, r.status_code == 200 and bool(r.json()["features"])
                    )
            r = c.get("/api/climate", params={"lat": lat, "lon": lon, "lang": lang})
            check(f"{tag} climate", r, r.status_code == 200 and bool(r.json().get("series") or r.json()))
            r = c.post(
                "/api/rotations",
                json={
                    "lat": lat,
                    "lon": lon,
                    "current_rotation": p["current_rotation"],
                    "irrigation": p["irrigation"],
                    "priorities": {"water": 0.8, "soil": 0.6, "income": 0.6, "pests": 0.4, "risk": 0.5},
                    "lang": lang,
                },
            )
            check(f"{tag} rotations", r, r.status_code == 200 and bool(r.json()["strategies"]))
            r = c.post(
                "/api/simulate",
                json={
                    "lat": lat,
                    "lon": lon,
                    "crop": p["crop"],
                    "planting_date": p["planting_date"],
                    "irrigation_strategy": "full" if p["irrigation"] != "none" else "rainfed",
                    "water_allocation_mm": None,
                    "delta_t_c": 0,
                    "rain_factor": 1,
                    "years": 20,
                    "lang": lang,
                },
            )
            check(f"{tag} simulate", r, r.status_code == 200 and bool(r.json().get("summary")))
            r = c.post(
                "/api/planner",
                json={
                    "lat": lat,
                    "lon": lon,
                    "crop": p["crop"],
                    "planting_date": p["planting_date"],
                    "irrigation": p["irrigation"],
                    "water_allocation_mm": None,
                    "lang": lang,
                },
            )
            check(f"{tag} planner", r, r.status_code == 200 and bool(r.json().get("operations")))
            r = c.post(
                "/api/terrain",
                json={"lat": lat, "lon": lon, "crop": p["crop"], "polygon": poly, "lang": lang},
            )
            ok = r.status_code == 200 and bool(r.json().get("layers"))
            check(f"{tag} terrain", r, ok)
            if ok:
                lay = r.json()["layers"][0]
                url = lay.get("png") or lay.get("url") or ""
                if url:
                    rp = c.get(url)
                    check(f"{tag} terrain png", rp, rp.status_code == 200 and len(rp.content) > 500)
            y0 = 2027
            r = c.post(
                "/api/rotations/plan",
                json={
                    "lat": lat,
                    "lon": lon,
                    "polygon": poly,
                    "irrigation": p["irrigation"],
                    "water_allocation_mm": None,
                    "history": [
                        {"year": y0 - 3 + i, "crop": p["current_rotation"][i % len(p["current_rotation"])]}
                        for i in range(3)
                    ],
                    "plan": [
                        {"year": y0 + i, "crop": p["current_rotation"][i % len(p["current_rotation"])]}
                        for i in range(4)
                    ],
                    "lang": lang,
                    "optimize": True,
                },
            )
            check(f"{tag} rotations/plan", r, r.status_code == 200 and bool(r.json().get("years")))
            r = c.get("/api/rain-season", params={"lat": lat, "lon": lon, "crop": p["crop"], "lang": lang})
            check(f"{tag} rain-season", r, r.status_code == 200)
            r = c.post(
                "/api/solar-pump",
                json={
                    "lat": lat,
                    "lon": lon,
                    "crop": p["crop"],
                    "planting_date": p["planting_date"],
                    "irrigation": p["irrigation"] if p["irrigation"] != "none" else "drip",
                    "polygon": poly,
                    "lang": lang,
                },
            )
            check(f"{tag} solar-pump", r, r.status_code == 200)
            sreq = {"lat": lat, "lon": lon, "polygon": poly, "crop": p["crop"], "lang": lang}
            sr: dict = {}
            r = None
            for _ in range(900 if ONLINE else 60):
                r = c.post("/api/satellite", json=sreq)
                sr = r.json() if r.status_code == 200 else {}
                if sr.get("status") != "processing":
                    break
                time.sleep(1)
            ok = sr.get("status") == "done"
            check(f"{tag} satellite", r, ok, f"status={sr.get('status')} {sr.get('message')}")
            if ok:
                pngs = re.findall(r"/api/satellite/png/[A-Za-z0-9]+/[a-z]+\.png", r.text)
                check(f"{tag} satellite pngs", r, bool(pngs), "no PNG overlays")
                for u in sorted(set(pngs)):
                    rp = c.get(u)
                    check(f"{tag} satellite png", rp, rp.status_code == 200 and rp.content[:4] == b"\x89PNG")
            print(f"{tag}: done ({len(fails)} failures so far)", flush=True)

    print("\n".join(notes))
    print(f"\nOK {n_ok}, FAILED {len(fails)}")
    for f in fails:
        print("  FAIL", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
