"""Satellite checks of the water balance: SMAP soil moisture vs. the model's root zone, ECOSTRESS ET vs. modelled ET,
and GRACE-DA groundwater percentiles.

The model (FAO-56 water balance on NASA POWER weather) drives the advice; these satellite layers are independent
evidence. They are shown next to the model and produce a card only where they disagree in a way a farmer can act on.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np

from .context import FieldContext
from .messages import t

# USDM-style categories for GRACE-DA and SMAP percentiles (Houborg et al. 2012 use the same breakpoints)
PCT_CLASSES = [
    (2, "exceptionally_dry"),
    (5, "extremely_dry"),
    (10, "severely_dry"),
    (20, "moderately_dry"),
    (30, "abnormally_dry"),
    (70, "near_normal"),
    (101, "wet"),
]
SMAP_DRY_PCT, SMAP_WET_PCT = 20.0, 80.0
MODEL_DRY_PCT, MODEL_WET_PCT = 40.0, 70.0
SMAP_MAX_AGE_DAYS = 10
ET_RECENT_DAYS = 30
GW_LOW_PCT = 10.0

SMAP_CAVEATS = [
    "SMAP L4 is a 9 km cell: it mixes your field with its surroundings and does not see irrigation on a single field.",
    "SMAP L4 merges the satellite's surface measurement with a land model (NASA GMAO); the root zone is modelled, not measured directly.",
]
ET_CAVEATS = [
    "ECOSTRESS flies on the Space Station: overpasses are irregular and clouds block many of them.",
    "One overpass is an instantaneous snapshot scaled to a daily total; single days are noisy (±1–2 mm/day).",
]
GRACE_DA_CAVEATS = [
    "GRACE-DA is a land model (Catchment) that assimilates GRACE/GRACE-FO; it covers ~25 km cells, not your well.",
    "Percentiles compare with the model's own 1948–2012 climatology; the data arrive ~2–3 months late.",
]


def pct_class(p: float) -> str:
    return next(name for lim, name in PCT_CLASSES if p < lim)


def _pct(v: float) -> float:
    return round(v * 100 if v <= 1.0 else v, 1)


def _latest(rows: list[tuple[dt.date, float]], today: dt.date, max_age: int) -> tuple[dt.date, float] | None:
    ok = [(d, v) for d, v in rows if d <= today and (today - d).days <= max_age]
    return ok[-1] if ok else None


# --------------------------------------------------------------------------- SMAP root zone vs model
def smap_check(
    ctx: FieldContext,
    model_pct_left: float | None,
    irrigated: bool,
    lang: str,
    today: dt.date,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(block, card). The card appears for rain-fed fields when SMAP and the model clearly disagree."""
    from .service import _why  # local import: service imports this module

    rz = _latest(ctx.enrich.get("smap_l4") or [], today, SMAP_MAX_AGE_DAYS)
    pc = _latest(ctx.enrich.get("smap_l4_pctl") or [], today, SMAP_MAX_AGE_DAYS)
    sf = _latest(ctx.enrich.get("smap_l4_surface") or [], today, SMAP_MAX_AGE_DAYS)
    if rz is None and pc is None:
        return None, None
    pctl = _pct(pc[1]) if pc else None
    agreement = "unknown"
    if pctl is not None and model_pct_left is not None:
        if pctl <= SMAP_DRY_PCT and model_pct_left >= MODEL_WET_PCT:
            agreement = "satellite_drier"
        elif pctl >= SMAP_WET_PCT and model_pct_left <= MODEL_DRY_PCT:
            agreement = "satellite_wetter"
        else:
            agreement = "agree"
    d = (rz or pc or sf)[0]  # type: ignore[index]
    steps = [
        f"NASA SMAP L4 ({d.isoformat()}, 9 km): root-zone soil moisture "
        + (f"{rz[1]:.3f} m³/m³" if rz else "n/a")
        + (f", surface {sf[1]:.3f} m³/m³" if sf else "")
        + (
            f"; wetter than {pctl:.0f} % of days in SMAP's record for this place and season ({pct_class(pctl).replace('_', ' ')})."
            if pctl is not None
            else "."
        ),
    ]
    if model_pct_left is not None:
        steps.append(
            f"FieldShift's water balance for your crop: {model_pct_left:.0f} % of available root-zone water left."
        )
    steps.append(
        "Check against SMAP L4 over 9 growing seasons (VALIDATION V3): the model's rain-fed root-zone water moved with "
        "SMAP's root zone with a median per-season correlation of 0.92 in Iowa, 0.66 in Córdoba and 0.64 in Machakos. "
        "SMAP is independent of the NASA POWER rain that drives the model."
    )
    if agreement == "satellite_drier":
        steps.append(
            "The satellite sees drier soil than the model: rain may have missed your area (the model's rain is a ~50 km grid "
            "average) or the soil holds less water than assumed. Check the soil by hand before relying on the model."
        )
    elif agreement == "satellite_wetter":
        steps.append(
            "The satellite sees wetter soil than the model: local rain the weather grid missed, or a shallow water table. "
            "Check the soil before irrigating or replanting."
        )
    elif agreement == "agree":
        steps.append("Satellite and model tell the same story; this raises confidence in the water advice.")
    if irrigated:
        steps.append(
            "On an irrigated field the 9 km SMAP cell mostly reflects the surrounding land, so it is shown for context only."
        )
    why = _why(
        "NASA SMAP soil moisture compared with the model's root zone"
        + {
            "satellite_drier": ": the satellite sees drier soil.",
            "satellite_wetter": ": the satellite sees wetter soil.",
            "agree": ": they agree.",
            "unknown": ".",
        }[agreement],
        steps,
        ["smap_rootzone", "smap_sm", "soil_depletion"],
        "SMAP L4 percentile vs. FAO-56 root-zone water balance",
        "soil-moisture",
        0.55 if agreement == "agree" else 0.45,
        "Two independent estimates; SMAP's 9 km cell is coarse for one field.",
        SMAP_CAVEATS,
        ["smap_l4", "nasa_power", "soilgrids"],
    )
    block = {
        "date": d.isoformat(),
        "rootzone_m3m3": round(rz[1], 3) if rz else None,
        "surface_m3m3": round(sf[1], 3) if sf else None,
        "rootzone_pctl": pctl,
        "rootzone_class": pct_class(pctl) if pctl is not None else None,
        "model_pct_left": model_pct_left,
        "agreement": agreement,
        "why": why,
    }
    card = None
    if not irrigated and agreement in ("satellite_drier", "satellite_wetter"):
        key = "smap_drier" if agreement == "satellite_drier" else "smap_wetter"
        card = {
            "id": "smap_check",
            "category": "water",
            "risk": "low",
            "icon": "planet",
            "title": t(f"{key}_title", lang, pct=round(pctl or 0)),
            "detail": t(f"{key}_detail", lang, model=round(model_pct_left or 0)),
            "due": None,
            "amount": None,
            "why": why,
        }
    return block, card


# --------------------------------------------------------------------------- ECOSTRESS ET vs model ETa
def et_check(
    ctx: FieldContext,
    eco: list[tuple[dt.date, float]],
    model_eta: dict[dt.date, float],
    irrigated: bool,
    lang: str,
    today: dt.date,
    in_season: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(block, None). Shown as evidence only, never as a card: at the Fallon alfalfa field (VALIDATION V6) ECOSTRESS
    reads ~40 % of the model's ET on almost every overpass, so a "crop uses less water" alarm would fire nearly always
    and its threshold cannot be set from one validated field."""
    from .service import _why

    if not eco:
        return None, None
    pairs = [(d, v, model_eta[d]) for d, v in eco if d in model_eta and d <= today]
    last_d, last_v = eco[-1]
    recent = [(d, v, m) for d, v, m in pairs if (today - d).days <= ET_RECENT_DAYS and m >= 1.5]
    ratio = float(np.mean([v for _, v, _ in recent]) / np.mean([m for _, _, m in recent])) if recent else None
    steps = [
        f"NASA ECOSTRESS (70 m, sees this field) measured {last_v:.1f} mm/day of evapotranspiration on {last_d.isoformat()}"
        + (f"; the model had {model_eta[last_d]:.1f} mm/day." if last_d in model_eta else "."),
    ]
    if recent:
        steps.append(
            f"Clear overpasses in the last {ET_RECENT_DAYS} days: {len(recent)}; satellite / model ET = {ratio:.2f}."
        )
    steps.append(
        "Check at the Fallon alfalfa field (VALIDATION V6): on 110 clear summer overpasses 2018–2024 ECOSTRESS averaged "
        "2.3 mm/day and the model 6.2 mm/day, with no day-to-day agreement. The model assumes a well-watered crop without "
        "cutting cycles; ECOSTRESS's daily total is scaled from one instant. Which is closer on your field cannot be told "
        "from one check, so this comparison is shown but does not trigger advice."
    )
    why = _why(
        f"NASA ECOSTRESS measured field ET {last_v:.1f} mm/day on {last_d.isoformat()}"
        + (
            f" ({ratio:.0%} of the model's estimate in the last {ET_RECENT_DAYS} days)."
            if ratio is not None
            else "."
        ),
        steps,
        ["ecostress_et", "eta_model"],
        "ECOSTRESS L3T JET ensemble ET vs. FAO-56 crop ET",
        "evapotranspiration",
        0.35,
        "Field-scale satellite measurement, but on clear overpass days only and in large disagreement with the model at the validation field.",
        ET_CAVEATS,
        ["ecostress", "nasa_power"],
    )
    block = {
        "last_date": last_d.isoformat(),
        "last_et_mm": round(last_v, 2),
        "last_model_mm": round(model_eta[last_d], 2) if last_d in model_eta else None,
        "recent_overpasses": len(recent),
        "recent_ratio": round(ratio, 2) if ratio is not None else None,
        "why": why,
    }
    return block, None


# --------------------------------------------------------------------------- GRACE-DA weekly drought percentiles
def grace_da(
    ctx: FieldContext, irrigated: bool, lang: str, series: list[dict[str, Any]], today: dt.date
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(drought block, card). Card: irrigated field whose groundwater percentile is severely low (≤ 10th)."""
    from .service import _series, _why

    gws = [(d, v) for d, v in ctx.enrich.get("grace_da_gws") or [] if d <= today]
    if not gws:
        return None, None
    rtz = [(d, v) for d, v in ctx.enrich.get("grace_da_rtzsm") or [] if d <= today]
    sfc = [(d, v) for d, v in ctx.enrich.get("grace_da_sfsm") or [] if d <= today]
    d, g = gws[-1]
    r = rtz[-1][1] if rtz else None
    s = sfc[-1][1] if sfc else None
    series.append(
        _series(
            "grace_da_gws",
            "Groundwater percentile (GRACE-DA, weekly)",
            "%",
            [x for x, _ in gws],
            [v for _, v in gws],
            "grace_da",
            "observed",
        )
    )
    if rtz:
        series.append(
            _series(
                "grace_da_rtzsm",
                "Root-zone soil moisture percentile (GRACE-DA)",
                "%",
                [x for x, _ in rtz],
                [v for _, v in rtz],
                "grace_da",
                "observed",
            )
        )
    steps = [
        f"NASA GRACE-FO data assimilation (week of {d.isoformat()}, ~25 km): groundwater is wetter than {g:.0f} % of "
        f"the same weeks in 1948–2012 ({pct_class(g).replace('_', ' ')})."
        + (f" Root-zone soil moisture: {r:.0f}th percentile." if r is not None else "")
        + (f" Surface soil moisture: {s:.0f}th percentile." if s is not None else ""),
        f"Latency: the latest week is {(today - d).days} days old.",
        "These are the maps behind the U.S. Drought Monitor's groundwater input, now worldwide (GRACEDADM_CLSM025GL_7D).",
    ]
    low = irrigated and g <= GW_LOW_PCT
    if low:
        steps.append(
            "On an irrigated farm, severely low groundwater means wells may yield less and pumping costs rise; plan water "
            "use for the season and check your well level."
        )
    why = _why(
        f"Groundwater here is at the {g:.0f}th percentile for the time of year (GRACE-DA, week of {d.isoformat()}).",
        steps,
        ["grace_da_gws", "grace_da_rtzsm", "grace_tws"],
        "GRACE/GRACE-FO data assimilation into the Catchment land model (NASA GSFC)",
        "groundwater",
        0.5,
        "Model + satellite gravity; regional, and 2–3 months late.",
        GRACE_DA_CAVEATS,
        ["grace_da"],
    )
    block = {
        "week": d.isoformat(),
        "groundwater_pct": round(g, 1),
        "rootzone_pct": round(r, 1) if r is not None else None,
        "surface_pct": round(s, 1) if s is not None else None,
        "groundwater_class": pct_class(g),
        "why": why,
    }
    card = None
    if low:
        card = {
            "id": "groundwater_low",
            "category": "planning",
            "risk": "moderate" if g <= 5 else "low",
            "icon": "water-outline",
            "title": t("groundwater_low_title", lang, pct=max(1, round(g))),
            "detail": t("groundwater_low_detail", lang),
            "due": None,
            "amount": None,
            "why": why,
        }
    return block, card
