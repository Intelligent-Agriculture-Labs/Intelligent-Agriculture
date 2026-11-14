"""Weather-driven disease risk models (hourly temperature & relative humidity).

1. Potato/tomato late blight (Phytophthora infestans) — Hutton criteria (UK AHDB, 2017 revision of the
   Smith period): two consecutive days with Tmin ≥ 10 °C and ≥ 6 h each with RH ≥ 90 %.
   Partial: one qualifying day, or both days with 4–5 h RH ≥ 90 % (near-miss) -> moderate.
2. Leaf-wetness proxy: hours with RH ≥ 90 % (Sentelhas et al. 2008 found RH ≥ 90 % a robust LWD proxy).
3. Wheat stripe rust (Puccinia striiformis) — infection favourable when ≥ 6 consecutive wet hours
   (RH ≥ 90 %) with T 7–15 °C (Rapilly 1979; de Vallavieille-Pope et al. 1995).
4. Powdery mildew of grapes/cucurbits/others — Gubler–Thomas index: count of days with ≥ 6
   consecutive hours at 21–30 °C (Gubler et al. 1999; simplified).
5. Alfalfa/legume foliar (spring black stem / leaf spot) proxy — cool (10–25 °C) and ≥ 10 wet hours/day.
6. Sclerotinia white mould (beans, soybean, sunflower) — ≥ 12 wet hours with 15–25 °C during flowering.

Outputs are *risk of conditions favourable to infection*, not detection of disease. Confidence is
limited by the forecast grid (~10–25 km) and by RH as a leaf-wetness proxy; always scout before spraying.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

import numpy as np

DISEASES: dict[str, dict[str, Any]] = {
    "late_blight": {"name": "Late blight", "crops": ["potato", "tomato"], "ref": "Hutton criteria (AHDB 2017)"},
    "stripe_rust": {"name": "Stripe rust", "crops": ["winter_wheat", "barley", "triticale_forage"], "ref": "de Vallavieille-Pope et al. 1995"},
    "powdery_mildew": {"name": "Powdery mildew", "crops": ["tomato", "sunflower", "dry_bean", "barley"], "ref": "Gubler et al. 1999 (simplified)"},
    "legume_leaf_disease": {"name": "Leaf spot / spring black stem", "crops": ["alfalfa"], "ref": "Leaf-wetness proxy (Sentelhas et al. 2008)"},
    "white_mould": {"name": "White mould (Sclerotinia)", "crops": ["dry_bean", "soybean", "sunflower", "safflower"], "ref": "Wet-hours × temperature window"},
    "downy_mildew_millet": {"name": "Downy mildew", "crops": ["pearl_millet"], "ref": "Wet-hours × temperature window"},
}


def hourly_by_day(hourly: dict[str, list[Any]]) -> dict[dt.date, dict[str, np.ndarray]]:
    by: dict[dt.date, dict[str, list[float]]] = defaultdict(lambda: {"t": [], "rh": []})
    for ts, t, rh in zip(hourly.get("time", []), hourly.get("temperature_2m", []), hourly.get("relative_humidity_2m", []), strict=False):
        if t is None or rh is None:
            continue
        d = dt.date.fromisoformat(ts[:10])
        by[d]["t"].append(float(t))
        by[d]["rh"].append(float(rh))
    return {d: {"t": np.array(v["t"]), "rh": np.array(v["rh"])} for d, v in sorted(by.items())}


def _max_run(mask: np.ndarray) -> int:
    best = cur = 0
    for m in mask:
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


def daily_scores(days: dict[dt.date, dict[str, np.ndarray]]) -> dict[str, dict[dt.date, float]]:
    """Return per-disease daily risk scores 0..1."""
    out: dict[str, dict[dt.date, float]] = {k: {} for k in DISEASES}
    dates = sorted(days)
    hutton_day: dict[dt.date, tuple[bool, bool]] = {}
    for d in dates:
        t, rh = days[d]["t"], days[d]["rh"]
        if len(t) < 18:
            continue
        wet = rh >= 90
        wet_h = int(wet.sum())
        tmin = float(t.min())
        full = tmin >= 10 and wet_h >= 6
        near = tmin >= 10 and wet_h >= 4
        hutton_day[d] = (full, near)
        # stripe rust
        sr_mask = wet & (t >= 7) & (t <= 15)
        out["stripe_rust"][d] = min(1.0, _max_run(sr_mask) / 8)
        # powdery mildew: ≥6 consecutive h at 21–30 °C
        pm_run = _max_run((t >= 21) & (t <= 30))
        out["powdery_mildew"][d] = 1.0 if pm_run >= 6 else pm_run / 6 * 0.6
        # legume foliar
        lg = wet & (t >= 10) & (t <= 25)
        out["legume_leaf_disease"][d] = min(1.0, lg.sum() / 10)
        wm = wet & (t >= 15) & (t <= 25)
        out["white_mould"][d] = min(1.0, wm.sum() / 12)
        dm = wet & (t >= 15) & (t <= 30)
        out["downy_mildew_millet"][d] = min(1.0, dm.sum() / 10)
    for i, d in enumerate(dates):
        if d not in hutton_day:
            continue
        prev = hutton_day.get(dates[i - 1]) if i > 0 else None
        full, near = hutton_day[d]
        if prev and full and prev[0]:
            out["late_blight"][d] = 1.0
        elif prev and ((full and prev[1]) or (near and prev[0])):
            out["late_blight"][d] = 0.6
        elif full or near:
            out["late_blight"][d] = 0.3 if full else 0.15
        else:
            out["late_blight"][d] = 0.0
    return out


def risk_label(score: float) -> str:
    if score >= 0.85:
        return "severe"
    if score >= 0.55:
        return "high"
    if score >= 0.25:
        return "moderate"
    return "low"
