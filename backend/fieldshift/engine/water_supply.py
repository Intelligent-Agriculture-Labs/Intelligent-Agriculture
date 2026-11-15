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

GRACE_CAVEATS = [
    "This is a regional signal: your own well can stay steady while the region loses water, or the reverse.",
    "GRACE senses total water storage (groundwater + soil water + surface water + snow) over ~300 km "
    "(one 3° mascon), not the aquifer under your field; local wells can behave differently.",
    "GRACE data arrive ~2–3 months late, and the GRACE → GRACE-FO gap (Jul 2017 – May 2018) has no data.",
]


def rain_sources(ctx: FieldContext) -> list[str]:
    return ["gpm_imerg"] if ctx.rain_meta.get("imerg_used") else []


def rain_step(ctx: FieldContext) -> str | None:
    """One sentence on where the rain numbers come from (for every rain-driven Why)."""
    m = ctx.rain_meta
    if m.get("imerg_used"):
        return (
            f"Rain: NASA POWER (MERRA-2) and NASA GPM IMERG satellite rain averaged day by day (IMERG to {m['imerg_last']}; "
            f"later days use POWER scaled to IMERG's climatology). Against 18 rain gauges on 6 continents this blend "
            f"beat POWER alone at 16 (VALIDATION V13)."
        )
    if m.get("reason") == "outside_validated_band":
        return "Rain: NASA POWER only — GPM IMERG blending is validated only between 45° S and 45° N."
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


def _trend_text(tr: gw.StorageTrend) -> str:
    sig = (
        "statistically significant"
        if tr.p_value < gw.ALPHA
        else ("probable but not certain" if tr.p_value < gw.ALPHA_LIKELY else "not significant")
    )
    return f"{tr.slope_cm_yr:+.2f} ± {1.96 * tr.slope_se_cm_yr:.2f} cm/yr (95 % range), p = {tr.p_value:.3f} — {sig}"


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
            "Water storage anomaly (GRACE/GRACE-FO, ~300 km)",
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
            "Long-term trend (fitted)",
            "cm",
            dates,
            gw.trend_line(dates, vals),
            "grace_fo",
            "modelled",
        )
    )
    falling = tr.status in ("declining", "likely_declining")
    steps = [
        f"NASA GRACE and GRACE-FO weigh the water stored under and on the land each month ({tr.first} to {tr.last}, "
        f"{tr.n_months} months; JPL RL06.3 mascons).",
        f"Trend at this location: {_trend_text(tr)}. Change since 2003: {tr.change_cm:+.0f} cm of water.",
        f"Last 3 months (seasonal cycle removed): {tr.anomaly_cm:+.0f} cm vs. the 2004–2009 mean, "
        f"lower than {100 - tr.percentile:.0f} % of months on record.",
    ]
    if tr.recent_slope_cm_yr is not None:
        steps.append(
            f"Last 5 years alone: {tr.recent_slope_cm_yr:+.1f} cm/yr (wet or dry spells dominate short windows)."
        )
    steps.append(
        "Check against wells (VALIDATION V14): in 11 U.S. aquifer regions, GRACE's yearly storage moved with USGS "
        "groundwater levels in all 11 (median r = 0.56) and the trend direction matched in 8; it can disagree where "
        "irrigation recharge keeps shallow wells steady while the wider region dries (e.g. Fallon, Nevada)."
    )
    if r["moved_km"]:
        steps.append(f"Nearest land cell used ({r['moved_km']} km away).")
    conf = 0.6 if tr.status in ("declining", "rising") else 0.45
    note = (
        "A long, statistically tested record; but the footprint is ~300 km and includes soil and surface water."
        if tr.p_value < gw.ALPHA
        else "Year-to-year swings are large compared with the trend, so its direction is uncertain."
    )
    status_word = {
        "declining": "falling",
        "likely_declining": "probably falling",
        "stable": "no clear trend",
        "likely_rising": "probably rising",
        "rising": "rising",
    }[tr.status]
    why = _why(
        f"Water stored in this region is {status_word}: {tr.slope_cm_yr:+.1f} cm per year since {tr.first[:4]} "
        f"(p = {tr.p_value:.2f}).",
        steps,
        ["grace_tws", "grace_trend"],
        "Harmonic regression with AR(1)-adjusted trend test on GRACE/GRACE-FO mascons",
        "groundwater",
        conf,
        note,
        GRACE_CAVEATS,
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
            "On an irrigated farm, falling storage means pumping is drawing down the aquifer faster than rain and rivers "
            "refill it: wells get deeper and pumping costs rise.",
            "Water-saving rotations (fewer thirsty crops in a row, deficit irrigation, winter cover crops instead of "
            "summer-irrigated crops) reduce the draw; compare them in the Rotations tab.",
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
    lat: float, lon: float, irrigated: bool, today: dt.date
) -> tuple[float, str | None]:
    """Multiplier for the 'water' priority in rotation ranking, and an explanation (irrigated + storage falling)."""
    if not irrigated:
        return 1.0, None
    r = grace.tws_at(lat, lon)
    tr = gw.analyse(r["dates"], r["tws_cm"], today) if r else None
    if tr is None or tr.status not in ("declining", "likely_declining"):
        return 1.0, None
    factor = 1.5 if tr.status == "declining" else 1.25
    return factor, (
        f"NASA GRACE/GRACE-FO: water storage in this region is falling ({tr.slope_cm_yr:+.1f} cm/yr since {tr.first[:4]}, "
        f"p = {tr.p_value:.2f}), so water use counts {factor:g}× in the ranking. Prefer rotations that pump less."
    )


def latest_month(lat: float, lon: float) -> str | None:
    r = grace.tws_at(lat, lon)
    return r["dates"][-1].isoformat() if r else None


RAIN_CARDS = {"irrigate", "rainfed_ok", "rainfed_stress", "drought"}


def annotate_rain(ctx: FieldContext, cards: list[dict[str, Any]], series: list[dict[str, Any]]) -> None:
    """Credit GPM IMERG wherever blended rain drives a card or chart (no-op when POWER rain is served)."""
    if not ctx.rain_meta.get("imerg_used"):
        return
    step = rain_step(ctx)
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
            s["label"] = "Rain (NASA POWER + GPM IMERG)"
            s["source"] = "gpm_imerg"
