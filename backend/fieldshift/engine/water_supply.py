"""Water-supply evidence for the advice: rain provenance (POWER + GPM IMERG) and the GRACE groundwater trend.

Kept out of service.py so the advice/rotation code only calls a few functions:
  * rain_step / rain_sources ........... Why-text and source ids for anything driven by rain
  * groundwater(ctx, irrigated, lang) .. drought-status block, Why series and (irrigated, falling) the card
  * rotation_water_weight .............. raises the water weight in rotation ranking where storage is falling
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..data import grace
from ..science import groundwater as gw
from .context import FieldContext
from .messages import t

GRACE_CAVEATS = ["gw_caveat_regional", "gw_caveat_total", "gw_caveat_latency"]  # message keys


def rain_sources(ctx: FieldContext) -> list[str]:
    return ["gpm_imerg"] if ctx.rain_meta.get("imerg_used") else []


def rain_step(ctx: FieldContext, lang: str = "en") -> str | None:
    """One sentence on where the rain numbers come from (for every rain-driven Why)."""
    m = ctx.rain_meta
    if m.get("imerg_used"):
        return t("rain_step_imerg", lang, last=m["imerg_last"])
    if m.get("reason") == "outside_validated_band":
        return t("rain_step_power_only", lang)
    return None


def rain_source_block(ctx: FieldContext) -> dict[str, Any]:
    m = ctx.rain_meta
    return {
        "method": m.get("method", "power"),
        "imerg_used": bool(m.get("imerg_used")),
        "imerg_last": m.get("imerg_last"),
        "annual_power_mm": m.get("annual_power_mm"),
        "annual_imerg_mm": m.get("annual_imerg_mm"),
    }


def _trend_text(tr: gw.StorageTrend, lang: str = "en") -> str:
    sig = (
        "gw_sig_yes"
        if tr.p_value < gw.ALPHA
        else ("gw_sig_likely" if tr.p_value < gw.ALPHA_LIKELY else "gw_sig_no")
    )
    return t(
        "gw_trend_text",
        lang,
        slope=tr.slope_cm_yr,
        se=1.96 * tr.slope_se_cm_yr,
        p=tr.p_value,
        sig=t(sig, lang),
    )


def groundwater(
    ctx: FieldContext, irrigated: bool, lang: str, series: list[dict[str, Any]], today: dt.date
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(drought-status block, card or None). The card is shown for irrigated fields where storage is falling."""
    from .service import _series, _why  # local import: service imports this module

    r = grace.tws_at(ctx.lat, ctx.lon)
    if r is None:
        return None, None
    tr = gw.analyse(r["dates"], r["tws_cm"], today)
    if tr is None:
        return None, None
    ctx.statuses["grace_fo"] = "cache"
    keep = [k for k, d in enumerate(r["dates"]) if d <= today]
    dates = [r["dates"][k] for k in keep]
    vals = r["tws_cm"][keep]
    series.append(
        _series(
            "grace_tws",
            t("series_grace_tws", lang),
            "cm",
            dates,
            vals,
            "grace_fo",
            "observed",
        )
    )
    series.append(
        _series(
            "grace_trend",
            t("series_grace_trend", lang),
            "cm",
            dates,
            gw.trend_line(dates, vals),
            "grace_fo",
            "modelled",
        )
    )
    falling = tr.status in ("declining", "likely_declining")
    steps = [
        t("gw_step_intro", lang, first=tr.first, last=tr.last, n=tr.n_months),
        t("gw_step_trend", lang, trend=_trend_text(tr, lang), change=tr.change_cm),
        t("gw_step_recent", lang, anom=tr.anomaly_cm, pct=100 - tr.percentile),
    ]
    if tr.recent_slope_cm_yr is not None:
        steps.append(t("gw_step_5y", lang, slope=tr.recent_slope_cm_yr))
    steps.append(t("gw_step_wells", lang))
    if r["moved_km"]:
        steps.append(t("gw_step_moved", lang, km=r["moved_km"]))
    conf = 0.6 if tr.status in ("declining", "rising") else 0.45
    note = t("gw_note_sig" if tr.p_value < gw.ALPHA else "gw_note_uncertain", lang)
    why = _why(
        t(
            "gw_sum",
            lang,
            status=t(f"gw_status_{tr.status}", lang),
            slope=tr.slope_cm_yr,
            year=tr.first[:4],
            p=tr.p_value,
        ),
        steps,
        ["grace_tws", "grace_trend"],
        t("model_grace", lang),
        "groundwater",
        conf,
        note,
        [t(k, lang) for k in GRACE_CAVEATS],
        ["grace_fo"],
    )
    block = {
        **tr.as_dict(),
        "trend_cm_per_year": tr.slope_cm_yr,
        "significant": tr.p_value < gw.ALPHA,
        "resolution_km": 300,
        "cell": [r["cell_lat"], r["cell_lon"]],
        "why": why,
    }
    card = None
    if irrigated and falling:
        steps_card = [
            *steps,
            t("gw_step_irrigated", lang),
            t("gw_step_rotations", lang),
        ]
        card = {
            "id": "groundwater_trend",
            "category": "planning",
            "risk": "moderate" if tr.status == "declining" else "low",
            "icon": "trending-down",
            "title": t("groundwater_title", lang, cm=max(1, round(abs(min(tr.change_cm, -0.5))))),
            "detail": t("groundwater_detail", lang),
            "due": None,
            "amount": None,
            "why": {**why, "steps": steps_card},
        }
    return block, card


def rotation_water_weight(
    lat: float, lon: float, irrigated: bool, today: dt.date, lang: str = "en"
) -> tuple[float, str | None]:
    """Multiplier for the 'water' priority in rotation ranking, and an explanation (irrigated + storage falling)."""
    if not irrigated:
        return 1.0, None
    r = grace.tws_at(lat, lon)
    tr = gw.analyse(r["dates"], r["tws_cm"], today) if r else None
    if tr is None or tr.status not in ("declining", "likely_declining"):
        return 1.0, None
    factor = 1.5 if tr.status == "declining" else 1.25
    return factor, t(
        "gw_rotation_note", lang, slope=tr.slope_cm_yr, year=tr.first[:4], p=tr.p_value, f=factor
    )


def latest_month(lat: float, lon: float) -> str | None:
    r = grace.tws_at(lat, lon)
    return r["dates"][-1].isoformat() if r else None


RAIN_CARDS = {"irrigate", "rainfed_ok", "rainfed_stress", "drought"}


def annotate_rain(
    ctx: FieldContext, cards: list[dict[str, Any]], series: list[dict[str, Any]], lang: str = "en"
) -> None:
    """Credit GPM IMERG wherever blended rain drives a card or chart (no-op when POWER rain is served)."""
    if not ctx.rain_meta.get("imerg_used"):
        return
    step = rain_step(ctx, lang)
    for cd in cards:
        if cd["id"] not in RAIN_CARDS:
            continue
        why = cd["why"]
        if "gpm_imerg" not in why["sources"]:
            why["sources"] = [*why["sources"], "gpm_imerg"]
        if step and step not in why["steps"]:
            why["steps"] = [*why["steps"], step]
    for s in series:
        if s["id"] == "precip":
            s["label"] = t("series_precip_imerg", lang)
            s["source"] = "gpm_imerg"
