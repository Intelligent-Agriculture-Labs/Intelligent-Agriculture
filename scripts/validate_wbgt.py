"""WBGT validation (docs/VALIDATION.md V9). Writes docs/validation/wbgt.json.

1. Cross-check against an independent Liljegren implementation (ECMWF thermofeel ≥ 2.3,
   `pip install thermofeel`; skipped if not installed) on a 1,800-case grid.
2. Psychrometric wet bulb vs. the Assmann psychrometer equation and Stull (2011).
3. Error of the offline fallback (hourly T/RH + NASA POWER climatological wind and radiation)
   against full NASA POWER hourly inputs (T2M, RH2M, WS2M, ALLSKY_SFC_SW_DWN), daily-max WBGT,
   for three climates. Needs network (NASA POWER hourly API).

    cd backend && .venv/bin/python ../scripts/validate_wbgt.py
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fieldshift.data import heatwx, sources  # noqa: E402
from fieldshift.science import heatstress as hs  # noqa: E402

out: dict = {"run": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}

# 1 ---------------------------------------------------------------- independent implementation
try:
    import thermofeel
    from thermofeel import liljegren as tf_lil

    diffs = []
    for t, rh, u, ghi, cza in itertools.product(
        [15, 25, 30, 35, 40, 45], [10, 30, 50, 70, 90], [0.5, 1.5, 3.0, 6.0], [0, 200, 500, 800, 1000], [0.3, 0.6, 0.95]
    ):
        solar, fdir, c = hs._radiation_terms(ghi, cza, None)
        ours = hs.wbgt_liljegren(t, rh, u, ghi, cza, 1000.0).wbgt
        ref = float(
            tf_lil.wbgt(*(np.array([v]) for v in (t + 273.15, rh, 1000.0, u, solar, fdir, c)))[0]
        ) - 273.15
        diffs.append(ours - ref)
    d = np.array(diffs)
    out["thermofeel"] = {
        "version": thermofeel.__version__ if hasattr(thermofeel, "__version__") else "2.3",
        "n": len(d),
        "bias": round(float(d.mean()), 4),
        "mae": round(float(np.abs(d).mean()), 4),
        "max_abs": round(float(np.abs(d).max()), 4),
    }
except ImportError:
    out["thermofeel"] = "not installed"


# 2 ---------------------------------------------------------------- psychrometric wet bulb
def es(x: float) -> float:
    return 6.112 * math.exp(17.62 * x / (243.12 + x))


def tw_assmann(t: float, rh: float, p: float = 1013.25) -> float:
    lo, hi = -40.0, t
    e = rh / 100 * es(t)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if es(mid) - 6.62e-4 * p * (t - mid) - e > 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


rows = []
for t in (10, 20, 30, 40):
    for rh in (20, 50, 80):
        ours = hs.wet_bulb_temperature(t, rh, 1013.25, 1.0, 0, 0, 0, natural=False)
        rows.append((t, rh, ours - tw_assmann(t, rh), ours - hs.wet_bulb_stull(t, rh)))
out["psychrometric"] = {
    "vs_assmann_min": round(min(r[2] for r in rows), 3),
    "vs_assmann_max": round(max(r[2] for r in rows), 3),
    "vs_stull_mae": round(float(np.mean([abs(r[3]) for r in rows])), 3),
    "stull_20C_50pct": round(hs.wet_bulb_stull(20, 50), 2),
}

# 3 ---------------------------------------------------------------- fallback vs full hourly
SITES = [
    ("Ludhiana, India (hot, dry pre-monsoon)", 30.90, 75.85, dt.date(2024, 5, 20), 28, 247),
    ("Fallon, Nevada (desert summer)", 39.44, -118.83, dt.date(2024, 7, 1), 31, 1200),
    ("Machakos, Kenya (tropical highland)", -1.57, 37.22, dt.date(2025, 2, 1), 28, 1600),
]
fb = []
for name, lat, lon, d0, ndays, elev in SITES:
    d1 = d0 + dt.timedelta(days=ndays - 1)
    full = heatwx.power_hourly(lat, lon, d0, d1)
    power = sources.power_daily(lat, lon, d0 - dt.timedelta(days=11 * 365), d1)
    hourly = {
        "time": [tm.isoformat(timespec="minutes") for tm in full.times],
        "temperature_2m": full.t,
        "relative_humidity_2m": full.rh,
    }

    class Ctx:
        pass

    ctx = Ctx()
    ctx.lat, ctx.lon, ctx.hourly, ctx.power, ctx.statuses = lat, lon, hourly, power, {}
    clim = heatwx.from_context(ctx, d0, d1)
    p = hs.pressure_hpa(elev)

    def daily_max(w, lat=lat, lon=lon, p=p):
        rr = hs.assess_hours(lat, lon, w.times, w.t, w.rh, w.wind2, w.ghi, w.utc_offset_h, p, w.direct)
        m: dict = {}
        for r in rr:
            m[r.time.date()] = max(m.get(r.time.date(), -99), r.wbgt)
        return m

    a, b = daily_max(full), daily_max(clim)
    common = sorted(set(a) & set(b))
    e = np.array([b[k] - a[k] for k in common])
    lev_a = [hs.worker_level(a[k]) for k in common]
    lev_b = [hs.worker_level(b[k]) for k in common]
    fb.append(
        {
            "site": name,
            "days": len(common),
            "full_mean_daily_max": round(float(np.mean([a[k] for k in common])), 2),
            "bias": round(float(e.mean()), 2),
            "mae": round(float(np.abs(e).mean()), 2),
            "level_agreement": round(float(np.mean([x == y for x, y in zip(lev_a, lev_b, strict=True)])), 2),
        }
    )
out["fallback_vs_power_hourly"] = fb
dst = ROOT / "docs/validation/wbgt.json"
dst.write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
