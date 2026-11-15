"""V13b: is near-real-time GPM IMERG (Late run) good enough to fill the ~2–3 months IMERG Final has not reached yet?

    FIELDSHIFT_CACHE_DIR=~/fs-live-cache backend/.venv/bin/python scripts/validate_imerg_late.py
    (data box: IMERG Late comes from NASA GES DISC via Giovanni and needs Earthdata Login)
    → docs/validation/imerg_late.json

Same 18 GHCN gauges, lag rule and metrics as V13 (scripts/validate_imerg.py), 2019–2024. The decision-relevant
comparison is for the bridge period, where the app previously served CR50 (POWER × climatological IMERG/POWER ratio)
and now serves B50L (0.5 · POWER + 0.5 · IMERG Late):
  P_lst  NASA POWER PRECTOTCORR (local solar time)
  I      IMERG Final (POWER, UTC days)          L      IMERG Late (GES DISC GPM_3IMERGDL.07, UTC days)
  B50    0.5 · (P_lst + I)   (served where Final exists)
  B50L   0.5 · (P_lst + L)   (served now on recent days)
  CR50   P_lst × (0.5 + 0.5 · climatological I/P ratio)  (served on recent days before this change)
Adoption rule, fixed before the run: B50L must beat CR50 on daily r and monthly KGE at a majority of gauges.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import validate_imerg as vi  # noqa: E402
from fieldshift.data import earthdata  # noqa: E402
from fieldshift.science import rainblend  # noqa: E402

vi.START, vi.END = dt.date(2019, 1, 1), dt.date(2024, 12, 31)
PRODUCTS = ["P_lst", "I", "L", "B50", "B50L", "CR50"]


def late(lat: float, lon: float, dates: list[dt.date]) -> np.ndarray:
    rows, _, _ = earthdata.giovanni_series(earthdata.IMERG_LATE, lat, lon, vi.START, vi.END, ttl_s=60 * 86400)
    a = np.full(len(dates), np.nan)
    for d, v in rows:
        a[(d - vi.START).days] = v
    return a


def evaluate(site: tuple[str, str, str, str, float, float]) -> dict[str, object]:
    sid, station, name, continent, lat, lon = site
    g = vi.ghcn(station)
    n = (vi.END - vi.START).days + 1
    dates = [vi.START + dt.timedelta(days=i) for i in range(n)]
    obs = np.array([g.get(d, np.nan) for d in dates])
    utc = vi.power(lat, lon, "PRECTOTCORR,IMERG_PRECTOT", "UTC")
    p = vi.power(lat, lon, "PRECTOTCORR", "LST")["PRECTOTCORR"]
    i = utc["IMERG_PRECTOT"]
    lt = late(lat, lon, dates)
    mon = np.array([d.month - 1 for d in dates])
    prods = {
        "P_lst": p,
        "I": i,
        "L": lt,
        "B50": rainblend.blend_daily(p, i, 0.5),
        "B50L": rainblend.blend_daily(p, lt, 0.5),
        "CR50": p * rainblend.bridge_factor(rainblend.climatological_ratio(p, i, dates))[mon],
    }

    def shifted(a: np.ndarray, lag: int) -> np.ndarray:
        return np.roll(a, lag) if lag else a

    lag = max(
        (-1, 0, 1), key=lambda k: np.nanmean([vi.pearson(shifted(p, k), obs), vi.pearson(shifted(i, k), obs)])
    )
    months = np.array([d.year * 12 + d.month - 1 for d in dates])
    valid = np.isfinite(obs)
    mobs: list[float] = []
    mprod: dict[str, list[float]] = {k: [] for k in prods}
    for m in np.unique(months):
        sel = (months == m) & valid
        if sel.sum() < 20:
            continue
        sh = {k: shifted(v, lag)[sel] for k, v in prods.items()}
        if any(not np.isfinite(x).all() for x in sh.values()):
            continue
        mobs.append(float(obs[sel].sum()))
        for k in prods:
            mprod[k].append(float(sh[k].sum()))
    mo = np.array(mobs)
    metrics = {}
    for k, a in prods.items():
        s, mp = shifted(a, lag), np.array(mprod[k])
        metrics[k] = {
            "daily_r": round(vi.pearson(s, obs), 3),
            "wet_day_csi": round(vi.csi(s, obs), 3),
            "monthly_r": round(vi.pearson(mp, mo), 3),
            "monthly_bias_pct": round(100 * (mp.sum() / mo.sum() - 1), 1) if len(mo) else float("nan"),
            "monthly_kge": round(vi.kge(mp, mo), 3),
        }
    both = np.isfinite(i) & np.isfinite(lt)
    return {
        "site": sid,
        "name": name,
        "continent": continent,
        "zone": rainblend.zone(lat),
        "lag_days": lag,
        "months": len(mo),
        "late_vs_final_daily_r": round(vi.pearson(lt, i), 3),
        "late_vs_final_bias_pct": round(100 * (np.nansum(lt[both]) / np.nansum(i[both]) - 1), 1),
        "metrics": metrics,
    }


def main() -> None:
    rows = []
    for s in vi.SITES:
        try:
            r = evaluate(s)
        except Exception as e:  # report and continue
            print(f"{s[0]}: FAILED {type(e).__name__}: {e}", flush=True)
            continue
        rows.append(r)
        m = r["metrics"]
        print(
            f"{r['site']:<13} {r['zone']:<11} months={r['months']:<3} L~I r={r['late_vs_final_daily_r']:.2f} "
            f"bias={r['late_vs_final_bias_pct']:+.0f}%  "
            + "  ".join(
                f"{k}: d{m[k]['daily_r']:.2f} kge{m[k]['monthly_kge']:.2f}" for k in ("CR50", "B50L", "B50")
            ),
            flush=True,
        )
    ok = [r for r in rows if r["months"] >= 12]

    def wins(a: str, b: str, key: str) -> int:
        return sum(r["metrics"][a][key] > r["metrics"][b][key] for r in ok)

    summary = {
        "sites": len(ok),
        "B50L_beats_CR50_daily_r": wins("B50L", "CR50", "daily_r"),
        "B50L_beats_CR50_monthly_kge": wins("B50L", "CR50", "monthly_kge"),
        "B50L_beats_P_daily_r": wins("B50L", "P_lst", "daily_r"),
        "B50L_beats_P_monthly_kge": wins("B50L", "P_lst", "monthly_kge"),
        "B50_beats_B50L_daily_r": wins("B50", "B50L", "daily_r"),
        "median_late_vs_final_daily_r": round(float(np.median([r["late_vs_final_daily_r"] for r in ok])), 3),
        "median_late_vs_final_bias_pct": round(
            float(np.median([r["late_vs_final_bias_pct"] for r in ok])), 1
        ),
        "mean": {
            k: {
                m: round(float(np.nanmean([r["metrics"][k][m] for r in ok])), 3)
                for m in ("daily_r", "wet_day_csi", "monthly_r", "monthly_kge", "monthly_bias_pct")
            }
            for k in PRODUCTS
        },
    }
    summary["adopted"] = (
        summary["B50L_beats_CR50_daily_r"] > len(ok) / 2
        and summary["B50L_beats_CR50_monthly_kge"] > len(ok) / 2
    )
    out = {
        "generated": dt.date.today().isoformat(),
        "period": [vi.START.isoformat(), vi.END.isoformat()],
        "reference": "GHCN-Daily (NOAA NCEI), QC-flagged values dropped",
        "sites": rows,
        "summary": summary,
    }
    path = ROOT / "docs" / "validation" / "imerg_late.json"
    path.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
