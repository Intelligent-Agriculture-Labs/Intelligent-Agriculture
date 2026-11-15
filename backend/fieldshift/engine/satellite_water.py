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


def _caveats(prefix: str, lang: str) -> list[str]:
    return [t(f"{prefix}_{i}", lang) for i in (1, 2)]


def pct_label(p: float, lang: str) -> str:
    return t(f"sw_pct_{pct_class(p)}", lang)


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
        t("sw_smap_step_obs", lang, date=d.isoformat())
        + (t("sw_smap_rz_val", lang, v=rz[1]) if rz else t("sw_na", lang))
        + (t("sw_smap_sf_val", lang, v=sf[1]) if sf else "")
        + (t("sw_smap_pctl", lang, pct=pctl, cls=pct_label(pctl, lang)) if pctl is not None else "."),
    ]
    if model_pct_left is not None:
        steps.append(t("sw_smap_model", lang, pct=model_pct_left))
    steps.append(t("sw_smap_validation", lang))
    if agreement == "satellite_drier":
        steps.append(t("sw_smap_step_drier", lang))
    elif agreement == "satellite_wetter":
        steps.append(t("sw_smap_step_wetter", lang))
    elif agreement == "agree":
        steps.append(t("sw_smap_step_agree", lang))
    if irrigated:
        steps.append(t("sw_smap_step_irrigated", lang))
    why = _why(
        t(f"sw_smap_summary_{agreement}", lang),
        steps,
        ["smap_rootzone", "smap_sm", "soil_depletion"],
        t("sw_smap_model_name", lang),
        "soil-moisture",
        0.55 if agreement == "agree" else 0.45,
        t("sw_smap_note", lang),
        _caveats("sw_smap_caveat", lang),
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
        t("sw_et_step_obs", lang, et=last_v, date=last_d.isoformat())
        + (t("sw_et_model_val", lang, et=model_eta[last_d]) if last_d in model_eta else "."),
    ]
    if recent:
        steps.append(t("sw_et_step_recent", lang, days=ET_RECENT_DAYS, n=len(recent), ratio=ratio))
    steps.append(t("sw_et_validation", lang))
    why = _why(
        t("sw_et_summary", lang, et=last_v, date=last_d.isoformat())
        + (t("sw_et_summary_ratio", lang, ratio=ratio, days=ET_RECENT_DAYS) if ratio is not None else "."),
        steps,
        ["ecostress_et", "eta_model"],
        t("sw_et_model_name", lang),
        "evapotranspiration",
        0.35,
        t("sw_et_note", lang),
        _caveats("sw_et_caveat", lang),
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
            t("sw_series_grace_gws", lang),
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
                t("sw_series_grace_rtzsm", lang),
                "%",
                [x for x, _ in rtz],
                [v for _, v in rtz],
                "grace_da",
                "observed",
            )
        )
    steps = [
        t("sw_gda_step_obs", lang, date=d.isoformat(), pct=g, cls=pct_label(g, lang))
        + (t("sw_gda_rz", lang, pct=r) if r is not None else "")
        + (t("sw_gda_sf", lang, pct=s) if s is not None else ""),
        t("sw_gda_latency", lang, days=(today - d).days),
        t("sw_gda_usdm", lang),
    ]
    low = irrigated and g <= GW_LOW_PCT
    if low:
        steps.append(t("sw_gda_step_low", lang))
    why = _why(
        t("sw_gda_summary", lang, pct=g, date=d.isoformat()),
        steps,
        ["grace_da_gws", "grace_da_rtzsm", "grace_tws"],
        t("sw_gda_model_name", lang),
        "groundwater",
        0.5,
        t("sw_gda_note", lang),
        _caveats("sw_gda_caveat", lang),
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
