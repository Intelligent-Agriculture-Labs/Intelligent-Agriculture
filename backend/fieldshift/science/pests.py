"""Degree-day phenology models for key insect pests.

Accumulation uses the single-sine-free simple average method with lower/upper thresholds, from a
biofix (1 January in the northern hemisphere / 1 July in the southern hemisphere unless stated).
Thresholds and event degree-days are literature values (UC IPM, Purdue, Iowa State, NDSU extension);
they are converted from °F·d to °C·d (× 5/9) where published in °F. See docs/MODELS.md §Pests.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np

PESTS: dict[str, dict[str, Any]] = {
    "alfalfa_weevil": {
        "name": "Alfalfa weevil",
        "crops": ["alfalfa"],
        "t_low": 9.0,  # 48 °F
        "t_high": 30.0,
        "events": [  # (°C·d, label, action)
            (156, "Egg hatch begins", "Start weekly sweep-net sampling"),
            (319, "Peak larval feeding", "Scout tips for feeding; check economic threshold (UC IPM: 20 larvae / sweep)"),
            (450, "Larval feeding declining", "Consider early cutting instead of spraying if near harvest"),
        ],
        "ref": "UC IPM Alfalfa Pest Management Guidelines; Purdue E-series (48 °F base)",
    },
    "western_corn_rootworm": {
        "name": "Western corn rootworm",
        "crops": ["maize", "maize_silage"],
        "t_low": 11.1,  # 52 °F (soil-based in literature; air proxy here)
        "t_high": 30.0,
        "events": [
            (380, "Egg hatch begins", "Larval feeding on roots starts — continuous corn at highest risk"),
            (570, "Peak larval injury", "Dig roots to rate injury"),
            (760, "Adult emergence", "Scout silks for adult beetles"),
        ],
        "ref": "Iowa State University Extension (52 °F base, soil DD approximated with air temperature)",
    },
    "european_corn_borer": {
        "name": "European corn borer",
        "crops": ["maize", "maize_silage", "dry_bean"],
        "t_low": 10.0,
        "t_high": 30.0,
        "events": [(208, "First-generation moth flight", "Scout for egg masses"), (611, "Second-generation moth flight", "Scout ears/stalks")],
        "ref": "Mason et al. (1996) NCR-327",
    },
    "corn_earworm": {
        "name": "Corn earworm",
        "crops": ["maize", "tomato", "sorghum"],
        "t_low": 12.6,
        "t_high": 33.3,
        "events": [(420, "Larvae on silks/fruit", "Scout silks or fruit")],
        "ref": "UC IPM degree-day models (Heliothis zea)",
    },
    "colorado_potato_beetle": {
        "name": "Colorado potato beetle",
        "crops": ["potato", "tomato"],
        "t_low": 10.0,
        "t_high": 30.0,
        "events": [(105, "Overwintered adults emerge", "Scout field edges"), (300, "First-generation larvae", "Scout for small larvae; threshold-based control")],
        "ref": "Ferro et al. (1985); University of Maine IPM",
    },
    "cereal_aphids": {
        "name": "Russian wheat aphid / cereal aphids",
        "crops": ["winter_wheat", "barley", "triticale_forage"],
        "t_low": 5.0,
        "t_high": 30.0,
        "events": [(250, "Spring population build-up", "Check 100 tillers for rolled leaves")],
        "ref": "Colorado State University Extension (indicative)",
    },
    "fall_armyworm": {
        "name": "Fall armyworm",
        "crops": ["maize", "sorghum", "pearl_millet", "teff"],
        "t_low": 10.9,
        "t_high": 35.0,
        "events": [(350, "One generation completed (egg→adult)", "Scout whorls for windowpane damage")],
        "ref": "Hogg et al. 1982; FAO FAW guidance",
    },
}


def degree_days(tmax: np.ndarray, tmin: np.ndarray, t_low: float, t_high: float) -> np.ndarray:
    tx = np.minimum(np.where(np.isfinite(tmax), tmax, t_low), t_high)
    tn = np.where(np.isfinite(tmin), tmin, t_low)
    return np.maximum((tx + tn) / 2 - t_low, 0.0)


def biofix(today: dt.date, lat: float) -> dt.date:
    if lat >= 0:
        return dt.date(today.year, 1, 1)
    return dt.date(today.year if today.month >= 7 else today.year - 1, 7, 1)


def status(pest_id: str, dates: list[dt.date], tmax: np.ndarray, tmin: np.ndarray, today: dt.date, lat: float, forecast_days: int = 7) -> dict[str, Any]:
    """Accumulated DD to today, projected DD in `forecast_days`, next event and days until it."""
    p = PESTS[pest_id]
    bf = biofix(today, lat)
    i0 = max(0, (bf - dates[0]).days)
    it = min(len(dates) - 1, (today - dates[0]).days)
    dd = degree_days(tmax, tmin, p["t_low"], p["t_high"])
    acc_today = float(np.nansum(dd[i0 : it + 1]))
    fut = dd[it + 1 : it + 1 + forecast_days]
    acc_week = acc_today + float(np.nansum(fut))
    nxt = None
    days_until = None
    passed = None
    for ev in p["events"]:
        if acc_today < ev[0]:
            nxt = ev
            run = acc_today
            for k, v in enumerate(dd[it + 1 :]):
                run += v
                if run >= ev[0]:
                    days_until = k + 1
                    break
            break
        passed = ev
    return {
        "id": pest_id,
        "name": p["name"],
        "biofix": bf.isoformat(),
        "dd_today": round(acc_today),
        "dd_in_week": round(acc_week),
        "next_event": {"dd": nxt[0], "label": nxt[1], "action": nxt[2]} if nxt else None,
        "days_until_next": days_until,
        "last_event": {"dd": passed[0], "label": passed[1], "action": passed[2]} if passed else None,
        "t_low": p["t_low"],
        "ref": p["ref"],
    }
