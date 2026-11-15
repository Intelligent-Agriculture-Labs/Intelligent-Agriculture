"""Business logic behind the API: advice, simulation, rotations, climate trends."""

from __future__ import annotations

import datetime as dt
import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import yaml

from ..data import firms, sources
from ..data.sources import source_ref
from ..science import climate as climmod
from ..science import disease as dis
from ..science import drought as drt
from ..science import drought_ml
from ..science import pests as pst
from ..science import rotation as rot
from ..science.cropmodel import IRRIGATION_EFFICIENCY, crop, crops, gdd_requirement, simulate
from . import live_layers, risk_cards, satellite_water
from . import water_supply as wsup
from .context import FieldContext, build, enrichment
from .fire_cards import fire_cards
from .heat_cards import heat_stress_cards
from .messages import (
    crop_name,
    crop_names,
    day_label,
    day_month,
    has,
    month_name,
    risk_word,
    t,
    tr_crop,
    word,
)
from .solar_service import solar_pump_cards

log = logging.getLogger("fieldshift.service")


def norm_cdf(z: float) -> float:
    from scipy.stats import norm

    return float(norm.cdf(z))


CONFIG = Path(__file__).resolve().parents[1] / "config"
RISKS = ["low", "moderate", "high", "severe"]
_pool = ThreadPoolExecutor(max_workers=6)


@lru_cache
def rules() -> dict[str, Any]:
    with open(CONFIG / "rules.yaml") as f:
        return yaml.safe_load(f)


@lru_cache
def presets() -> list[dict[str, Any]]:
    with open(CONFIG / "presets.yaml") as f:
        return yaml.safe_load(f)["presets"]


# --------------------------------------------------------------------------- helpers
def _climatology(
    arr: np.ndarray, dates: list[dt.date], y0: int = 1991, y1: int = 2020, smooth: int = 15
) -> np.ndarray:
    """Day-of-year mean over y0–y1, circularly smoothed (moving average of `smooth` days). Returns 366 values."""
    doy = np.array([d.timetuple().tm_yday for d in dates]) - 1
    yrs = np.array([d.year for d in dates])
    sel = (yrs >= y0) & (yrs <= y1) & np.isfinite(arr[: len(dates)])
    s = np.bincount(doy[sel], weights=arr[: len(dates)][sel], minlength=366)
    n = np.bincount(doy[sel], minlength=366)
    clim = np.where(n > 0, s / np.maximum(n, 1), np.nan)
    k = np.ones(smooth) / smooth
    ext = np.concatenate([clim[-smooth:], clim, clim[:smooth]])
    ext = np.where(np.isfinite(ext), ext, np.nanmean(clim))
    return np.convolve(ext, k, mode="same")[smooth:-smooth]


def _series(
    sid: str,
    label: str,
    unit: str,
    dates: list[dt.date],
    vals: Any,
    source: str,
    kind: str = "observed",
    normal: Any | None = None,
) -> dict[str, Any]:
    pts = [
        {"date": d.isoformat(), "value": (None if v is None or not np.isfinite(v) else round(float(v), 3))}
        for d, v in zip(dates, vals, strict=False)
    ]
    out: dict[str, Any] = {
        "id": sid,
        "label": label,
        "unit": unit,
        "points": pts,
        "source": source,
        "kind": kind,
    }
    if normal is not None:
        out["normal"] = [
            {"date": d.isoformat(), "value": (None if not np.isfinite(v) else round(float(v), 3))}
            for d, v in zip(dates, normal, strict=False)
        ]
    return out


def _season_start(c: dict[str, Any], planting: dt.date, today: dt.date) -> dt.date:
    """For perennials the user gives the stand green-up date; roll it to the current season."""
    if c["type"] != "perennial":
        # annuals: pick the season instance that is running now or comes next (users enter last/next year's date)
        span = int(1.3 * sum(c["stages"]))
        p = dt.date(planting.year, planting.month, min(planting.day, 28))
        while p + dt.timedelta(days=span) < today:
            p = dt.date(p.year + 1, p.month, p.day)
        while (p - today).days > 365 - span and p.year > 1985:
            p = dt.date(p.year - 1, p.month, p.day)
        return p
    s = dt.date(today.year, planting.month, min(planting.day, 28))
    return s if s <= today else dt.date(today.year - 1, planting.month, min(planting.day, 28))


def _plan_card(c: dict[str, Any], lang: str, state_key: str) -> dict[str, Any]:
    return {
        "id": "plan_rotation",
        "category": "planning",
        "risk": "low",
        "icon": "swap-horizontal",
        "title": t("plan_title", lang),
        "detail": t("plan_detail", lang, crop=_crop_lc(c, lang), state=t(f"state_{state_key}", lang)),
        "due": None,
        "amount": None,
        "why": _why(
            t("plan_why_summary", lang),
            [t("plan_why_step_compare", lang)],
            ["tmax", "tmin"],
            t("model_season_state", lang),
            "rotations",
            0.8,
            t("plan_why_note", lang),
            [],
            ["nasa_power"],
        ),
    }


def _crop_lc(c: dict[str, Any], lang: str) -> str:
    """Crop name for use mid-sentence (lower-case except in German)."""
    n = tr_crop(c["name"], lang)
    return n if lang == "de" else n.lower()


def _lc(s: str, lang: str) -> str:
    """Lower-case a name for use mid-sentence (German nouns keep their capital)."""
    return s if lang == "de" else s.lower()


_INDICATOR_KEYS = {
    "SPEI-12 months": "dr_ind_spei12",
    "soil-moisture percentile": "dr_ind_sm",
    "vegetation health index": "dr_ind_vhi",
}


def _indicator_text(part: str, lang: str) -> str:
    """Translate the indicator name in a drought.combined_level() part ("soil-moisture percentile = 12")."""
    name, sep, val = part.partition(" = ")
    key = _INDICATOR_KEYS.get(name)
    return f"{t(key, lang)}{sep}{val}" if key else part


def _clim_years(ctx: FieldContext, n: int = 15) -> list[int]:
    last = ctx.today.year - 1
    return list(range(last - n + 1, last + 1))


def _why(
    summary: str,
    steps: list[str],
    series: list[str],
    model: str,
    doc: str,
    conf: float,
    note: str,
    caveats: list[str],
    srcs: list[str],
) -> dict[str, Any]:
    return {
        "summary": summary,
        "steps": steps,
        "series": series,
        "model": model,
        "model_doc": doc,
        "confidence": round(conf, 2),
        "confidence_note": note,
        "caveats": caveats,
        "sources": srcs,
    }


def _risk_max(a: str, b: str) -> str:
    return a if RISKS.index(a) >= RISKS.index(b) else b


# --------------------------------------------------------------------------- advice
def advice(inp: dict[str, Any]) -> dict[str, Any]:
    lat, lon = float(inp["lat"]), float(inp["lon"])
    lang = inp.get("lang") or "en"
    today = dt.date.fromisoformat(inp["as_of"]) if inp.get("as_of") else dt.date.today()
    enr_future = _pool.submit(enrichment, lat, lon, today)
    live_future = _pool.submit(live_layers.fetch, lat, lon, today)  # SMAP L4, ECOSTRESS, GRACE-DA (Earthdata)
    fire_future = _pool.submit(firms.nearby_fires, lat, lon, today, 50.0)
    ctx = build(lat, lon, today)
    try:
        ctx.enrich = enr_future.result(timeout=float(inp.get("enrich_timeout_s", 8)))
    except FutTimeout:
        log.info("enrichment timed out; continuing without satellite layers")
        ctx.enrich = {}
    for sid in ("modis_ndvi", "mod16", "smap_l3e", "modis_lst"):
        ctx.statuses[sid] = "live" if ctx.enrich.get(sid) else "unavailable"
    try:
        live = live_future.result(timeout=float(inp.get("live_timeout_s", 15)))
    except Exception:  # live Earthdata layers are optional
        live = {}
    ctx.enrich = {**ctx.enrich, **{k: v for k, v in live.items() if k != "_status" and v}}
    for sid, st in (live.get("_status") or {}).items():
        ctx.statuses[sid] = st

    cid = inp["crop"]
    c = crop(cid)
    planting = _season_start(c, dt.date.fromisoformat(inp["planting_date"]), today)
    method = inp.get("irrigation", "sprinkler")
    irrigated = method != "none"
    w = ctx.weather
    cards: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    i_today = ctx.idx(today)
    caveat_grid = t("why_caveat_grid", lang)

    # ---------- water balance (current season)
    wstate: dict[str, Any] = {}
    wmodel: dict[str, Any] | None = None  # model root-zone state + daily ETa, for the satellite checks
    eco_obs: list[tuple[dt.date, float]] = []
    years = _clim_years(ctx)
    gdd_req = gdd_requirement(c, w, planting, years) if c["type"] != "perennial" else None
    known = None
    if inp.get("last_irrigation_date") and inp.get("last_irrigation_mm"):
        known = {dt.date.fromisoformat(inp["last_irrigation_date"]): float(inp["last_irrigation_mm"])}
    horizon = today + dt.timedelta(days=rules()["irrigation"]["lookahead_days"])
    # ---- satellite data fusion: observed canopy (Sentinel-2) rescales modelled crop water use
    fusion = None
    try:
        from .satellite_service import latest_for

        sat_res = latest_for(lat, lon, inp.get("polygon"), cid, today)
    except Exception:  # never let fusion break advice
        sat_res = None
    if sat_res and sat_res.get("kcb_now") and sat_res.get("timeseries"):
        sat_date = dt.date.fromisoformat(sat_res["timeseries"][-1]["date"])
        if 0 <= (today - sat_date).days <= 15 and planting <= sat_date:
            fusion = {
                "kcb_sat": float(sat_res["kcb_now"]),
                "date": sat_date,
                "ndvi": sat_res["timeseries"][-1]["value"],
            }
    if planting <= today:
        res = simulate(
            cid,
            w,
            planting,
            taw_per_m=ctx.taw_per_m,
            strategy="full" if irrigated else "rainfed",
            method=method,
            gdd_req=gdd_req,
            until=min(horizon, w.dates[-1]),
            known_irrigations=known,
            record_daily=True,
            irrigate_until_date=(min(known) - dt.timedelta(days=1)) if known else today,
            allocation_mm=inp.get("water_allocation_mm"),
        )
        if fusion is not None and res.daily:
            ddates0 = [dt.date.fromisoformat(x) for x in res.daily["date"]]
            if fusion["date"] in ddates0:
                kc_model = res.daily["kc"][ddates0.index(fusion["date"])]
                if kc_model > 0.2:
                    scale = float(np.clip((fusion["kcb_sat"] + 0.05) / kc_model, 0.4, 1.4))
                    fusion["kc_model"], fusion["scale"] = kc_model, scale
                    res = simulate(
                        cid,
                        w,
                        planting,
                        taw_per_m=ctx.taw_per_m,
                        strategy="full" if irrigated else "rainfed",
                        method=method,
                        gdd_req=gdd_req,
                        until=min(horizon, w.dates[-1]),
                        known_irrigations=known,
                        record_daily=True,
                        irrigate_until_date=(min(known) - dt.timedelta(days=1)) if known else today,
                        allocation_mm=inp.get("water_allocation_mm"),
                        kc_scale=scale,
                        kc_scale_from=fusion["date"],
                    )
        daily = res.daily
        ddates = [dt.date.fromisoformat(x) for x in daily["date"]]
        k_today = ddates.index(today) if today in ddates else len(ddates) - 1
        dr_t, taw_t, raw_t = daily["dr"][k_today], daily["taw"][k_today], daily["raw"][k_today]
        stress_day = next(
            (ddates[k] for k in range(k_today + 1, len(ddates)) if daily["dr"][k] >= daily["raw"][k]), None
        )
        if dr_t >= raw_t:
            stress_day = today
        eff = IRRIGATION_EFFICIENCY.get(method, 0.75)
        fw = ctx.forecast_window(7)
        rain7 = float(np.nansum(w.rain[fw]))
        et07 = float(np.nansum(w.et0[fw]))
        season_irr = sum(daily["irr"][: k_today + 1])
        wstate = {
            "root_zone_depletion_mm": round(dr_t, 1),
            "taw_mm": round(taw_t, 1),
            "raw_mm": round(raw_t, 1),
            "days_to_stress": (stress_day - today).days if stress_day else None,
            "next_irrigation_date": stress_day.isoformat() if (stress_day and irrigated) else None,
            "next_irrigation_mm": None,
            "season_et_mm": round(sum(daily["eta"][: k_today + 1]), 1),
            "season_rain_mm": round(sum(daily["rain"][: k_today + 1]), 1),
            "season_irrigation_mm": round(season_irr, 1),
            "forecast_rain_7d_mm": round(rain7, 1),
            "forecast_et0_7d_mm": round(et07, 1),
        }
        pct_left = round(100 * (1 - dr_t / taw_t)) if taw_t > 0 else 0
        wmodel = {
            "pct_left": pct_left,
            "eta": {ddates[k]: float(daily["eta"][k]) for k in range(len(ddates))},
        }
        sm_dates = ddates
        series.append(
            _series(
                "soil_depletion",
                t("series_soil_depletion", lang),
                "mm",
                sm_dates,
                daily["dr"],
                "nasa_power",
                "modelled",
            )
        )
        series.append(
            _series(
                "raw_threshold", t("series_raw", lang), "mm", sm_dates, daily["raw"], "nasa_power", "modelled"
            )
        )
        series.append(
            _series("taw", t("series_taw", lang), "mm", sm_dates, daily["taw"], "soilgrids", "modelled")
        )
        series.append(
            _series(
                "irrigation_applied",
                t("series_irrigation_applied", lang),
                "mm",
                sm_dates,
                daily["irr"],
                "nasa_power",
                "modelled",
            )
        )
        steps = [
            t(
                "wb_step_season",
                lang,
                date=planting.isoformat(),
                stage=word("stage", res.final_stage, lang),
                kc=res.final_kc,
            ),
            t("wb_step_et0", lang, et0=et07, rain=rain7),
            t(
                "wb_step_soil",
                lang,
                soil=word("soil", ctx.soil["texture"], lang) if ctx.soil else t("soil_default", lang),
                taw_m=ctx.taw_per_m,
                taw=taw_t,
                raw=raw_t,
            ),
            t("wb_step_used", lang, dr=dr_t, pct=pct_left),
        ]
        caveats = [caveat_grid]
        # ECOSTRESS field ET: live overpasses (Earthdata) + the pre-extracted record of the demo fields
        eco_map = dict(ctx.enrich.get("ecostress") or [])
        etp = sources.et_points(lat, lon)
        if etp:
            for d_, v in zip(etp["dates"], etp["eco_et_daily"], strict=True):
                if v is not None:
                    eco_map.setdefault(dt.date.fromisoformat(d_), v)
        if eco_map:
            eco = sorted((d_, v) for d_, v in eco_map.items() if planting <= d_ <= today)
            eco_obs = eco
            if eco:
                series.append(
                    _series(
                        "ecostress_et",
                        t("series_ecostress_et", lang),
                        "mm/day",
                        [d_ for d_, _ in eco],
                        [v for _, v in eco],
                        "ecostress",
                        "observed",
                    )
                )
                ld, lv = eco[-1]
                if ld in ddates:
                    steps.append(
                        t(
                            "wb_step_ecostress",
                            lang,
                            et=lv,
                            date=ld.isoformat(),
                            model=daily["eta"][ddates.index(ld)],
                        )
                    )
                if ctx.statuses.get("ecostress") in (None, "unavailable"):
                    ctx.statuses["ecostress"] = "cache"
        if fusion and "scale" in fusion:
            steps.append(
                t(
                    "wb_step_fusion",
                    lang,
                    date=fusion["date"].isoformat(),
                    ndvi=fusion["ndvi"],
                    kcb=fusion["kcb_sat"],
                    kc=fusion["kc_model"],
                    scale=fusion["scale"],
                )
            )
        if irrigated and not known:
            caveats.append(t("wb_caveat_assumed", lang))
        conf = (0.7 if known else 0.55) + (0.1 if fusion and "scale" in fusion else 0.0)
        ndays = rules()["irrigation"]["lookahead_days"]
        if irrigated:
            if stress_day and stress_day <= horizon:
                k = ddates.index(stress_day)
                net = daily["dr"][k]
                gross = max(rules()["irrigation"]["min_amount_mm"], round(net / eff))
                wstate["next_irrigation_mm"] = gross
                days_left = (stress_day - today).days
                risk = "high" if days_left <= rules()["irrigation"]["urgent_days"] else "moderate"
                steps.append(t("wb_step_stress_on", lang, date=stress_day.isoformat()))
                steps.append(
                    t("wb_step_refill", lang, net=net, method=word("irr", method, lang), eff=eff, gross=gross)
                )
                cards.append(
                    {
                        "id": "irrigate",
                        "category": "water",
                        "risk": risk,
                        "icon": "water",
                        "title": t("irrigate_title", lang, mm=gross, day=day_label(stress_day, today, lang)),
                        "detail": t(
                            "irrigate_detail", lang, day=day_label(stress_day, today, lang), rain=round(rain7)
                        ),
                        "due": stress_day.isoformat(),
                        "amount": {"value": gross, "unit": "mm"},
                        "why": _why(
                            t("wb_sum_irrigate", lang, date=stress_day.isoformat(), gross=gross),
                            steps,
                            ["soil_depletion", "raw_threshold", "et0", "precip", "ecostress_et"],
                            t("model_water_balance", lang),
                            "water-balance",
                            conf,
                            t("wb_note_assumed", lang),
                            caveats,
                            ["nasa_power", "openmeteo_forecast", "soilgrids", "srtm"],
                        ),
                    }
                )
            else:
                steps.append(t("wb_step_no_stress", lang, days=ndays))
                cards.append(
                    {
                        "id": "irrigate",
                        "category": "water",
                        "risk": "low",
                        "icon": "water-outline",
                        "title": t("no_irrigation_title", lang, days=ndays),
                        "detail": t("no_irrigation_detail", lang, pct=pct_left),
                        "due": None,
                        "amount": None,
                        "why": _why(
                            t("wb_sum_no_irrigation", lang, days=ndays),
                            steps,
                            ["soil_depletion", "raw_threshold", "et0", "precip", "ecostress_et"],
                            t("model_water_balance", lang),
                            "water-balance",
                            conf,
                            t("wb_note", lang),
                            caveats,
                            ["nasa_power", "openmeteo_forecast", "soilgrids"],
                        ),
                    }
                )
        elif not (stress_day and stress_day <= horizon):
            steps.append(t("wb_step_rainfed_ok", lang, days=ndays))
            cards.append(
                {
                    "id": "rainfed_ok",
                    "category": "water",
                    "risk": "low",
                    "icon": "rainy-outline",
                    "title": t("rainfed_ok_title", lang, days=ndays),
                    "detail": t("no_irrigation_detail", lang, pct=pct_left),
                    "due": None,
                    "amount": None,
                    "why": _why(
                        t("wb_sum_rainfed_ok", lang, days=ndays),
                        steps,
                        ["soil_depletion", "raw_threshold", "precip"],
                        t("model_water_balance", lang),
                        "water-balance",
                        0.5,
                        t("wb_note_rainfed", lang),
                        caveats,
                        ["nasa_power", "openmeteo_forecast", "soilgrids"],
                    ),
                }
            )
        else:
            days_left = (stress_day - today).days
            cards.append(
                {
                    "id": "rainfed_stress",
                    "category": "water",
                    "risk": "high" if days_left <= 3 else "moderate",
                    "icon": "sunny",
                    "title": t("rainfed_stress_title", lang, day=day_label(stress_day, today, lang)),
                    "detail": t("rainfed_stress_detail", lang),
                    "due": stress_day.isoformat(),
                    "amount": None,
                    "why": _why(
                        t("wb_sum_rainfed_stress", lang),
                        steps,
                        ["soil_depletion", "raw_threshold", "precip"],
                        t("model_water_balance", lang),
                        "water-balance",
                        0.5,
                        t("wb_note_rainfed", lang),
                        caveats,
                        ["nasa_power", "openmeteo_forecast", "soilgrids"],
                    ),
                }
            )
    else:
        wstate = {
            "root_zone_depletion_mm": 0,
            "taw_mm": 0,
            "raw_mm": 0,
            "days_to_stress": None,
            "next_irrigation_date": None,
            "next_irrigation_mm": None,
            "season_et_mm": 0,
            "season_rain_mm": 0,
            "season_irrigation_mm": 0,
            "forecast_rain_7d_mm": round(float(np.nansum(w.rain[ctx.forecast_window(7)])), 1),
            "forecast_et0_7d_mm": round(float(np.nansum(w.et0[ctx.forecast_window(7)])), 1),
        }
        cards.extend(_planting_cards(ctx, cid, planting, method, lang))
        if (planting - today).days > 30:
            cards.append(_plan_card(c, lang, "harvested"))

    # ---------- off-season: dormant perennial or harvested annual -> rotation planning card (the Field Shift question)
    if planting <= today:
        killed = any(e["type"] == "killing_frost" and e["date"] <= today.isoformat() for e in res.events)
        harvested = c["type"] != "perennial" and res.end < today
        recent = w.tmax[max(0, i_today - 6) : i_today + 1], w.tmin[max(0, i_today - 6) : i_today + 1]
        cold = bool(
            np.nanmean((recent[0] + recent[1]) / 2) < c["t_base"] + 6
        )  # growth negligible (alfalfa < ~11 °C)
        if killed or harvested or (c["type"] == "perennial" and cold):
            state = t("state_harvested" if harvested else "state_dormant", lang)
            cards.append(
                {
                    "id": "plan_rotation",
                    "category": "planning",
                    "risk": "low",
                    "icon": "swap-horizontal",
                    "title": t("plan_title", lang),
                    "detail": t("plan_detail", lang, crop=_crop_lc(c, lang), state=state),
                    "due": None,
                    "amount": None,
                    "why": _why(
                        t("plan_why_summary", lang),
                        [
                            t(
                                "plan_why_step_cold",
                                lang,
                                temp=np.nanmean((recent[0] + recent[1]) / 2),
                                crop=crop_name(cid, lang, c["name"]),
                                tbase=c["t_base"] + 6,
                            ),
                            t("plan_why_step_compare", lang),
                        ],
                        ["tmax", "tmin"],
                        t("model_season_state", lang),
                        "rotations",
                        0.8,
                        t("plan_why_note", lang),
                        [],
                        ["nasa_power"],
                    ),
                }
            )

    # ---------- weather series for Why views (last 120 days + forecast)
    i0 = max(0, i_today - 120)
    i1 = min(len(w.dates), i_today + 17)
    wd = w.dates[i0:i1]
    pdates = ctx.weather.dates
    clim_rain = _climatology(w.rain, pdates)
    clim_et0 = _climatology(w.et0, pdates)
    clim_tmax = _climatology(w.tmax, pdates)
    doy = [d.timetuple().tm_yday - 1 for d in wd]
    kinds = ctx.provenance[i0:i1]
    series.append(
        _series(
            "precip",
            t("series_precip", lang),
            "mm/day",
            wd,
            w.rain[i0:i1],
            "nasa_power",
            "observed",
            [clim_rain[k] for k in doy],
        )
    )
    series.append(
        _series(
            "et0",
            t("series_et0", lang),
            "mm/day",
            wd,
            w.et0[i0:i1],
            "nasa_power",
            "observed",
            [clim_et0[k] for k in doy],
        )
    )
    series.append(
        _series(
            "tmax",
            t("series_tmax", lang),
            "°C",
            wd,
            w.tmax[i0:i1],
            "nasa_power",
            "observed",
            [clim_tmax[k] for k in doy],
        )
    )
    series.append(_series("tmin", t("series_tmin", lang), "°C", wd, w.tmin[i0:i1], "nasa_power", "observed"))
    fc_start = next((wd[k].isoformat() for k in range(len(wd)) if kinds[k] == 2), None)

    # ---------- satellite checks of the water balance (SMAP root zone, ECOSTRESS ET)
    sm_block, sm_card = satellite_water.smap_check(
        ctx, wmodel["pct_left"] if wmodel else None, irrigated, lang, today
    )
    et_block, et_card = (
        satellite_water.et_check(
            ctx, eco_obs, wmodel["eta"], irrigated, lang, today, in_season=planting <= today
        )
        if wmodel and eco_obs
        else (None, None)
    )
    if et_block is not None and wmodel:
        md = sorted(d_ for d_ in wmodel["eta"] if d_ <= today)
        series.append(
            _series(
                "eta_model",
                "Crop ET (model)",
                "mm/day",
                md,
                [wmodel["eta"][d_] for d_ in md],
                "nasa_power",
                "modelled",
            )
        )
    if sm_block or et_block:
        wstate["satellite"] = {"smap": sm_block, "et": et_block}
    cards.extend(cd for cd in (sm_card, et_card) if cd)

    # ---------- drought
    obs_end = i_today + 1
    pd_ = w.dates[:obs_end]
    spi30 = drt.spi_at(w.rain[:obs_end], pd_, today, 30)
    spi90 = drt.spi_at(w.rain[:obs_end], pd_, today, 90)
    spei90 = drt.standardized_at((w.rain - w.et0)[:obs_end], pd_, today, 90)
    spei365 = drt.standardized_at(
        (w.rain - w.et0)[:obs_end], pd_, today, 365
    )  # EXP-03: improves USDM agreement
    vhi, ndvi_card = _ndvi_block(ctx, series, lang, today, planting, c)
    sm_pct = _smap_block(ctx, series, lang)
    level, parts = drt.combined_level(spi30, spi90, spei90, sm_pct, vhi, spei365=spei365)
    acc90 = drt.rolling_sum(w.rain[:obs_end], 90)
    spi_series_d = w.dates[max(0, obs_end - 365) : obs_end]
    spi_vals = [
        drt.spi_at(w.rain[:obs_end], pd_, d, 90) if k % 7 == 0 or d == today else None
        for k, d in enumerate(spi_series_d)
    ]
    series.append(
        _series(
            "spi90",
            t("series_spi90", lang),
            "σ",
            spi_series_d,
            [np.nan if v is None else v for v in spi_vals],
            "nasa_power",
            "observed",
        )
    )
    rank_pct = None
    same = drt._same_window(pd_, today, 3)
    s90 = acc90[same]
    s90 = s90[np.isfinite(s90)]
    if len(s90) > 10 and np.isfinite(acc90[i_today]):
        rank_pct = round(100 * float(np.mean(s90 <= acc90[i_today])))
    dsteps = [
        t("dr_step_rain90", lang, rain=acc90[i_today], typ=np.median(s90), year=today.year)
        if rank_pct is not None
        else t("dr_step_no_history", lang),
        *[t("dr_indicator", lang, text=_indicator_text(p, lang)) for p in parts],
        t("dr_step_scale", lang),
    ]
    gw_block, gw_card = wsup.groundwater(ctx, irrigated, lang, series, today)
    gda_block, gda_card = satellite_water.grace_da(ctx, irrigated, lang, series, today)
    if gda_block is not None:
        dsteps.append(
            f"Groundwater now (NASA GRACE-FO data assimilation, week of {gda_block['week']}, ~25 km): "
            f"{gda_block['groundwater_pct']:.0f}th percentile"
            + (
                f"; root-zone soil moisture {gda_block['rootzone_pct']:.0f}th"
                if gda_block["rootzone_pct"] is not None
                else ""
            )
            + ". Context only; not part of the level."
        )
    if (rs := wsup.rain_step(ctx, lang)) is not None:
        dsteps.insert(1, rs)
    if gw_block is not None:
        dsteps.append(
            t(
                "dr_step_grace",
                lang,
                slope=gw_block["slope_cm_yr"],
                p=gw_block["p_value"],
                change=gw_block["change_cm"],
            )
        )
    # ---- AI drought classifier (gradient boosting on USDM labels) where it was validated
    ml_info = None
    model_name = t("model_drought_rules", lang)
    loaded_ml = drought_ml.load()
    if loaded_ml is not None and drought_ml.in_validated_domain(lat, lon, loaded_ml[1]):
        meta = loaded_ml[1]
        try:
            # the classifier was trained on POWER rain features: feed it POWER rain, not the IMERG blend
            rain_ml = ctx.rain_power if ctx.rain_power is not None else w.rain
            Xf = drought_ml.features_for(meta)(pd_, rain_ml[:obs_end], w.et0[:obs_end], w.tmax[:obs_end])
            pr = drought_ml.predict(Xf[-1])
        except (ValueError, IndexError):
            pr = None
        if pr is not None:
            ml_level, proba = pr
            hv = meta["ml_heldout"]
            region = drought_ml.region_of(lat, lon) or "US"
            reg = meta.get("per_region", {}).get(region)
            if reg is not None and region != "US":
                # held-out numbers for this region (leave-one-region-out), on the harmonised None/D0/D1/D2+ scale
                rv = reg["harmonised"][meta.get("served_key", "new_model")]
                within1, rho = rv["within1_acc"], rv["spearman"]
                where = t("dr_ml_where_region", lang, n=reg["n_sites"], label=reg["label"].upper())
            else:
                within1, rho = hv["within1_acc"], hv["spearman_vs_dsci"]
                where = t("dr_ml_where_us", lang)
            n_sites = meta.get("n_sites", meta["n_counties"])
            ml_info = {
                "level": ml_level,
                "probabilities": [round(p_, 3) for p_ in proba],
                "rules_level": level,
                "model": "Gradient-boosted trees trained on drought maps (U.S. Drought Monitor"  # i18n: ok (API metadata)
                + (
                    ", European Drought Observatory, Global Drought Observatory)"  # i18n: ok
                    if meta.get("feature_set") == "v2"
                    else ")"
                ),
                "heldout_within1_acc": within1,
                "heldout_spearman": rho,
                "n_counties": meta["n_counties"],
                "n_sites": n_sites,
                "region": region,
            }
            dsteps.append(
                t(
                    "dr_step_ml",
                    lang,
                    n_samples=f"{meta['n_samples']:,}",
                    n_sites=n_sites,
                    label=t(f"drought_level_{ml_level}", lang),
                    prob=100 * max(proba),
                    where=where,
                    acc=100 * within1,
                    rules_label=t(f"drought_level_{level}", lang),
                )
            )
            level = ml_level
            model_name = t("model_drought_ml", lang)
    drought = {
        "ml": ml_info,
        "level": level,
        "label": t(f"drought_level_{level}", lang),
        "spi30": spi30,
        "spi90": spi90,
        "spei90": spei90,
        "spei365": spei365,
        "sm_percentile": sm_pct,
        "vhi": vhi,
        "why": _why(
            t("dr_sum", lang, label=t(f"drought_level_{level}", lang), n=len(parts)),
            dsteps,
            ["spi90", "precip", "et0", "ndvi", "smap_sm"],
            model_name,
            "drought",
            0.6 if len(parts) >= 3 else 0.45,
            t("dr_note", lang),
            [t("dr_caveat_spi", lang), t("dr_caveat_smap", lang)],
            ["nasa_power", *wsup.rain_sources(ctx), "smap_l3e", "smap_l4", "modis_ndvi"]
            + (["grace_fo"] if gw_block is not None else [])
            + (["grace_da"] if gda_block is not None else []),
        ),
        "groundwater": gw_block,
        "grace_da": gda_block,
        "rain_source": wsup.rain_source_block(ctx),
    }
    if level >= rules()["drought"]["card_min_level"]:
        risk = RISKS[min(3, max(1, level - 1))]
        cards.append(
            {
                "id": "drought",
                "category": "drought",
                "risk": risk,
                "icon": "flame",
                "title": t("drought_title", lang, label=t(f"drought_level_{level}", lang)),
                "detail": (
                    t(
                        "drought_detail_12m",
                        lang,
                        pct=max(1, rank_pct or 50),
                        pct12=max(1, round(100 * float(norm_cdf(spei365)))),
                    )
                    if spei365 is not None
                    else t("drought_detail", lang, pct=max(1, rank_pct or 50))
                ),
                "due": None,
                "amount": None,
                "why": drought["why"],
            }
        )
    if ndvi_card:
        cards.append(ndvi_card)
    if gw_card:
        cards.append(gw_card)
    if gda_card:
        cards.append(gda_card)
    wsup.annotate_rain(ctx, cards, series, lang)

    # ---------- disease (hourly forecast)
    in_season = planting <= today and (
        c["type"] == "perennial" or not any(cd["id"] == "plan_rotation" for cd in cards)
    )
    # leaf diseases need leaves: annual crops only from emergence (~20 days after sowing)
    leafy = c["type"] == "perennial" or (today - planting).days >= 20
    if in_season and leafy:
        cards.extend(_disease_cards(ctx, cid, today, lang, series))
    # ---------- pests
    if in_season:
        cards.extend(_pest_cards(ctx, cid, today, lang, lat, planting))
        # global weather-driven pest & disease models (rice blast, rusts, tropical late blight, ...)
        cards.extend(risk_cards.cards(ctx, cid, c["type"], today, lang, planting, series))
    # ---------- frost / heat
    cards.extend(_temp_cards(ctx, cid, today, lang, planting))
    # ---------- rainy-season onset / false start / sowing window (rain-fed, tropics; engine/rain_season.py)
    if not irrigated:
        from .rain_season import onset_cards

        cards.extend(onset_cards(ctx, cid, today, lang, series))
    # ---------- heat stress for people and livestock, solar pump option, fires / residue burning
    cards.extend(heat_stress_cards(ctx, today, lang, series, _why))
    cards.extend(solar_pump_cards(ctx, inp, planting, lang, _why))
    try:
        fire_res = fire_future.result(timeout=float(inp.get("enrich_timeout_s", 8)) + 12)
    except Exception:  # FIRMS is optional
        fire_res = None
    cards.extend(fire_cards(lat, lon, cid, today, lang, _why, fire_res, ctx.statuses))

    # rank: risk desc, then due date asc
    def sort_key(cd: dict[str, Any]) -> tuple[int, str]:
        return (-RISKS.index(cd["risk"]), cd["due"] or "9999")

    cards.sort(key=sort_key)
    for k, cd in enumerate(cards, 1):
        cd["priority"] = k

    srcs = [
        source_ref(sid, ctx.statuses.get(sid, "live"), _last(ctx, sid))
        for sid in (
            "nasa_power",
            "openmeteo_forecast",
            "srtm",
            "soilgrids",
            "modis_ndvi",
            "smap_l3e",
            "smap_l4",
            "mod16",
            "ecostress",
            "firms",
            "gpm_imerg",
            "gpm_imerg_nrt",
            "grace_fo",
            "grace_da",
        )
        if (sid not in ("ecostress", "firms") or ctx.statuses.get(sid))
        and (sid != "gpm_imerg" or ctx.rain_meta.get("imerg_used"))
        and (sid != "gpm_imerg_nrt" or ctx.rain_meta.get("imerg_nrt_last"))
        and (sid != "grace_fo" or ctx.statuses.get("grace_fo"))
        and (sid != "grace_da" or ctx.statuses.get("grace_da") not in (None, "unavailable"))
    ]
    offline = any(s["status"] == "demo" for s in srcs)
    area = _polygon_area_ha(inp.get("polygon"))
    return {
        "field": {
            **{
                k: inp.get(k)
                for k in (
                    "lat",
                    "lon",
                    "crop",
                    "planting_date",
                    "irrigation",
                    "water_allocation_mm",
                    "lang",
                    "as_of",
                    "polygon",
                )
            },
            "elevation_m": ctx.elevation_m,
            "slope_pct": ctx.slope_pct,
            "soil": ctx.soil,
            "area_ha": area,
        },
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "as_of": today.isoformat(),
        "forecast_start": fc_start,
        "cards": cards,
        "drought": drought,
        "water": wstate,
        "series": series,
        "sources": srcs,
        "mock": False,
        "offline": offline,
    }


def _last(ctx: FieldContext, sid: str) -> str | None:
    if sid == "nasa_power":
        return ctx.power_last.isoformat() if ctx.power_last else None
    if sid == "openmeteo_forecast":
        return ctx.weather.dates[-1].isoformat()
    if sid == "gpm_imerg":
        return ctx.rain_meta.get("imerg_last")
    if sid == "gpm_imerg_nrt":
        return ctx.rain_meta.get("imerg_nrt_last")
    if sid == "grace_da":
        g = ctx.enrich.get("grace_da_gws")
        return g[-1][0].isoformat() if g else None
    if sid == "grace_fo":
        return wsup.latest_month(ctx.lat, ctx.lon)
    s = ctx.enrich.get(sid)
    return s[-1][0].isoformat() if s else None


def _polygon_area_ha(poly: list[list[float]] | None) -> float | None:
    if not poly or len(poly) < 3:
        return None
    lat0 = np.radians(np.mean([p[1] for p in poly]))
    xs = [np.radians(p[0]) * 6371000 * np.cos(lat0) for p in poly]
    ys = [np.radians(p[1]) * 6371000 for p in poly]
    a = 0.5 * abs(sum(xs[i] * ys[(i + 1) % len(xs)] - xs[(i + 1) % len(xs)] * ys[i] for i in range(len(xs))))
    return round(a / 10000, 2)


def _ndvi_block(
    ctx: FieldContext,
    series: list[dict[str, Any]],
    lang: str,
    today: dt.date,
    planting: dt.date,
    c: dict[str, Any],
) -> tuple[float | None, dict[str, Any] | None]:
    nd = ctx.enrich.get("modis_ndvi") or []
    if len(nd) < 46:
        return None, None
    dates = [d for d, _ in nd]
    vals = np.array([v for _, v in nd])
    # composite-period climatology (by day-of-year bin of 16 days)
    bins = np.array([d.timetuple().tm_yday // 16 for d in dates])
    recent = [k for k, d in enumerate(dates) if (today - d).days <= 365]
    normal = []
    for k in recent:
        same = (bins == bins[k]) & (np.arange(len(dates)) != k)
        normal.append(float(np.mean(vals[same])) if same.any() else np.nan)
    series.append(
        _series(
            "ndvi",
            t("series_ndvi", lang),
            "NDVI",
            [dates[k] for k in recent],
            vals[recent],
            "modis_ndvi",
            "observed",
            normal,
        )
    )
    last = len(dates) - 1
    same = bins == bins[last]
    vmin, vmax = vals[same].min(), vals[same].max()
    vci = 100 * (vals[last] - vmin) / (vmax - vmin) if vmax > vmin else 50.0
    sd = vals[same & (np.arange(len(dates)) != last)].std()
    mu = vals[same & (np.arange(len(dates)) != last)].mean()
    z = (vals[last] - mu) / sd if sd > 0 else 0.0
    card = None
    in_season = (today - planting).days > 30
    if z <= rules()["ndvi"]["anomaly_z"] and in_season and (today - dates[last]).days <= 40:
        pct = round(100 * (1 - vals[last] / mu)) if mu > 0 else 0
        card = {
            "id": "ndvi_anomaly",
            "category": "planning",
            "risk": "moderate",
            "icon": "search",
            "title": t("ndvi_title", lang, pct=pct),
            "detail": t("ndvi_detail", lang, date=dates[last].isoformat()),
            "due": None,
            "amount": None,
            "why": _why(
                t("ndvi_sum", lang, v=vals[last], z=abs(z), y0=dates[0].year, y1=today.year, mu=mu),
                [
                    t("ndvi_step_latest", lang, date=dates[last].isoformat(), v=vals[last]),
                    t("ndvi_step_clim", lang, n=int(same.sum()) - 1, mu=mu, sd=sd),
                    t("ndvi_step_meaning", lang),
                ],
                ["ndvi"],
                t("model_ndvi", lang),
                "ndvi",
                0.45,
                t("ndvi_note", lang),
                [t("ndvi_caveat_pixel", lang), t("caveat_clouds", lang)],
                ["modis_ndvi"],
            ),
        }
    return round(float(vci), 1), card


def _smap_block(ctx: FieldContext, series: list[dict[str, Any]], lang: str = "en") -> float | None:
    """SMAP soil moisture for the drought status and the Why charts. Sources, merged by date: the pre-extracted record
    of the demo sites (data/smap_points, SMAP L4 via NSIDC OPeNDAP), live SMAP L4 (Earthdata, last ~6 weeks) and ORNL's
    L3E subsets. Returns the root-zone percentile (SMAP L4's own climatological percentile; where L4 has none, the rank
    of today's root-zone value among the same ±30 days in the site record), or the L3E surface percentile."""
    today = ctx.today
    rz: dict[dt.date, float] = {}
    sf: dict[dt.date, float] = {}
    pc: dict[dt.date, float] = {}
    pts = sources.smap_points(ctx.lat, ctx.lon)
    hist_rz: list[tuple[dt.date, float]] = []
    if pts:
        surf_key = "l4_surface" if any(v is not None for v in pts.get("l4_surface") or []) else "l3e_sm"
        for k, ds in enumerate(pts["dates"]):
            d = dt.date.fromisoformat(ds)
            if d > today:
                continue
            if pts["l4_rootzone"][k] is not None:
                hist_rz.append((d, float(pts["l4_rootzone"][k])))
            if d < today - dt.timedelta(days=365):
                continue
            for dst, key in ((rz, "l4_rootzone"), (sf, surf_key), (pc, "l4_rootzone_pctl")):
                v = (pts.get(key) or [None] * len(pts["dates"]))[k]
                if v is not None:
                    dst[d] = float(v)
        if ctx.statuses.get("smap_l4") in (None, "unavailable"):
            ctx.statuses["smap_l4"] = "cache"
    for dst, sid in ((rz, "smap_l4"), (sf, "smap_l4_surface"), (pc, "smap_l4_pctl")):
        for d, v in ctx.enrich.get(sid) or []:
            if d <= today:
                dst[d] = float(v)
    if rz:
        kd = sorted(rz)
        if sf:
            sd = sorted(sf)
            series.append(
                _series(
                    "smap_sm",
                    "Surface soil moisture (SMAP L4, 0–5 cm, 9 km)",
                    "m³/m³",
                    sd,
                    [sf[d] for d in sd],
                    "smap_l4",
                    "observed",
                )
            )
        series.append(
            _series(
                "smap_rootzone",
                "Root-zone soil moisture (SMAP L4, 0–100 cm, 9 km)",
                "m³/m³",
                kd,
                [rz[d] for d in kd],
                "smap_l4",
                "observed",
            )
        )
        ctx.enrich.setdefault("smap_l4", [(d, rz[d]) for d in kd])
        if (today - kd[-1]).days > 10:
            return None
        recent = [pc[d] for d in sorted(pc)[-3:] if (today - d).days <= 10]
        if recent:
            p = float(np.mean(recent))
            return round(p * 100 if p <= 1.0 else p, 1)
        # no L4 percentile here (fill value): rank today's root zone among the same season in the site record
        same = [
            v
            for d, v in hist_rz
            if abs((d.timetuple().tm_yday - today.timetuple().tm_yday + 182) % 365 - 182) <= 30
        ]
        if len(same) >= 60:
            return drt.percentile_of(float(np.mean([rz[d] for d in kd[-3:]])), np.array(same))
        return None
    sm = ctx.enrich.get("smap_l3e") or []
    if len(sm) < 5:
        return None
    sdates = [d for d, _ in sm]
    vals = np.array([v for _, v in sm])
    series.append(_series("smap_sm", t("series_smap", lang), "m³/m³", sdates, vals, "smap_l3e", "observed"))
    if len(vals) >= 20:
        return drt.percentile_of(float(np.mean(vals[-3:])), vals)
    return None


def _disease_cards(
    ctx: FieldContext, cid: str, today: dt.date, lang: str, series: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not ctx.hourly:
        return []
    days = dis.hourly_by_day(ctx.hourly)
    scores = dis.daily_scores(days)
    out = []
    win = rules()["disease"]["window_days"]
    for did, meta in dis.DISEASES.items():
        if cid not in meta["crops"] or not dis.in_range(did, ctx.lat):
            continue
        s = scores[did]
        fut = {d: v for d, v in s.items() if today <= d <= today + dt.timedelta(days=win)}
        if not fut:
            continue
        dmax = max(fut, key=lambda d: fut[d])
        smax = fut[dmax]
        sdates = sorted(s)
        series.append(
            _series(
                f"risk_{did}",
                t("series_infection_risk", lang, name=risk_cards.legacy_name(did, lang, meta["name"])),
                "0–1",
                sdates,
                [s[d] for d in sdates],
                "openmeteo_forecast",
                "forecast",
            )
        )
        wet_hours = int((days[dmax]["rh"] >= 90).sum()) if dmax in days else 0
        tmin_d = float(days[dmax]["t"].min()) if dmax in days else float("nan")
        if smax < rules()["disease"]["min_score_card"]:
            continue
        risk = dis.risk_label(smax)
        first = min(d for d, v in fut.items() if v >= rules()["disease"]["min_score_card"])
        out.append(
            {
                "id": f"disease_{did}",
                "category": "disease",
                "risk": risk,
                "icon": "bug",
                "title": t(
                    "disease_title",
                    lang,
                    risk=risk_word(risk, lang),
                    disease=risk_cards.legacy_name(did, lang, meta["name"]),
                    day=day_label(first, today, lang),
                ),
                "detail": t("disease_detail", lang),
                "due": first.isoformat(),
                "amount": None,
                "why": _why(
                    t(
                        "dis_sum",
                        lang,
                        name=_lc(risk_cards.legacy_name(did, lang, meta["name"]), lang),
                        date=dmax.isoformat(),
                    ),
                    [
                        t("dis_step_model", lang, ref=word("dis_ref", did, lang)),
                        t("dis_step_day", lang, date=dmax.isoformat(), hours=wet_hours, tmin=tmin_d),
                        t("dis_step_score", lang, score=smax),
                        t("dis_step_scout", lang),
                    ],
                    [f"risk_{did}", "tmin", "precip"],
                    word("dis_ref", did, lang),
                    "disease",
                    0.5,
                    t("dis_note", lang),
                    [t("dis_caveat_grid", lang), t("dis_caveat_rh", lang)],
                    ["openmeteo_forecast", "nasa_power"],
                ),
            }
        )
    return out


def _pest_cards(
    ctx: FieldContext, cid: str, today: dt.date, lang: str, lat: float, planting: dt.date
) -> list[dict[str, Any]]:
    out = []
    c_type = crop(cid)["type"]
    w = ctx.weather
    for pid, p in pst.PESTS.items():
        if cid not in p["crops"] or not pst.present(pid, lat, ctx.lon):
            continue
        st = pst.status(
            pid, w.dates, w.tmax, w.tmin, today, lat, planting=planting if c_type != "perennial" else None
        )
        ev = st["next_event"]
        days_until = st["days_until_next"]
        lastev = st["last_event"]
        recent = False
        if lastev:
            # was the last event passed within the last N days?
            bf = dt.date.fromisoformat(st["biofix"])  # noqa: F841
            dd = pst.degree_days(w.tmax, w.tmin, p["t_low"], p["t_high"])
            i0 = ctx.idx(bf)
            cum = np.cumsum(dd[i0 : ctx.idx(today) + 1])
            k = int(np.searchsorted(cum, lastev["dd"]))
            recent = (len(cum) - 1 - k) <= rules()["pests"]["show_recent_days"]
        if ev and days_until is not None and days_until <= rules()["pests"]["window_days"]:
            key = "pest_soon_title" if days_until <= 1 else "pest_title"
            title = t(
                key,
                lang,
                pest=risk_cards.legacy_pest(pid, lang, p["name"]),
                event=risk_cards.legacy_event(ev["label"], lang),
                days=days_until,
            )
            due = (today + dt.timedelta(days=days_until)).isoformat()
            action = _pest_action(pid, p, ev, lang)
            risk = "moderate" if days_until > 3 else "high"
        elif p.get("recurring") and c_type != "perennial" and 0 <= (today - planting).days <= 60:
            title = t(
                "pest_scout_title",
                lang,
                pest=risk_cards.legacy_pest(pid, lang, p["name"]),
                gen=st["generation"],
            )
            due = today.isoformat()
            action = t("pest_faw_action", lang)
            risk = "moderate"
        elif recent and lastev:
            title = t(
                "pest_now_title",
                lang,
                pest=risk_cards.legacy_pest(pid, lang, p["name"]),
                event=risk_cards.legacy_event(lastev["label"], lang),
            )
            due = today.isoformat()
            action = _pest_action(pid, p, lastev, lang)
            risk = "high"
        else:
            continue
        out.append(
            {
                "id": f"pest_{pid}",
                "category": "pest",
                "risk": risk,
                "icon": "bug-outline",
                "title": title,
                "detail": action,
                "due": due,
                "amount": None,
                "why": _why(
                    t("pest_sum", lang, biofix=st["biofix"], dd=st["dd_today"], tlow=p["t_low"]),
                    [
                        t("pest_step_dd", lang, dd=st["dd_today"], dd7=st["dd_in_week"]),
                        t(
                            "pest_step_next",
                            lang,
                            stage=risk_cards.legacy_event((ev or lastev)["label"], lang),
                            dd=(ev or lastev)["dd"],
                            ref=p["ref"],
                        ),
                        t("pest_step_when", lang),
                    ],
                    ["tmax", "tmin"],
                    t("model_pest_dd", lang, ref=p["ref"]),
                    "pests",
                    0.55,
                    t("pest_note", lang),
                    [t("pest_caveat_grid", lang), t("pest_caveat_biofix", lang)],
                    ["nasa_power", "openmeteo_forecast"],
                ),
            }
        )
    return out


def _pest_action(pid: str, p: dict[str, Any], ev: dict[str, Any], lang: str) -> str:
    """Translated IPM action of a pest life-stage event (config/messages/pests.yaml); English fallback."""
    for i, e in enumerate(p["events"]):
        if e[1] == ev["label"] and has(f"pest_action_{pid}_{i}"):
            return t(f"pest_action_{pid}_{i}", lang)
    return str(ev["action"])


def _temp_cards(
    ctx: FieldContext, cid: str, today: dt.date, lang: str, planting: dt.date
) -> list[dict[str, Any]]:
    c = crop(cid)
    w = ctx.weather
    out = []
    fw = ctx.forecast_window(rules()["frost"]["window_days"])
    fdates = w.dates[fw]
    tmin = w.tmin[fw]
    tmax = w.tmax[fw]
    kill = c["t_kill"]
    sensitive_now = c["type"] != "perennial" and planting <= today + dt.timedelta(days=7)
    if len(tmin) and sensitive_now:
        k = int(np.nanargmin(tmin))
        if tmin[k] <= kill + rules()["frost"]["margin_c"]:
            risk = "severe" if tmin[k] <= kill else "high"
            out.append(
                {
                    "id": "frost",
                    "category": "weather",
                    "risk": risk,
                    "icon": "snow",
                    "title": t(
                        "frost_title", lang, day=day_label(fdates[k], today, lang), t=round(float(tmin[k]))
                    ),
                    "detail": t("frost_detail", lang, crop=crop_name(cid, lang, c["name"]), kill=kill),
                    "due": fdates[k].isoformat(),
                    "amount": None,
                    "why": _why(
                        t(
                            "frost_sum",
                            lang,
                            tmin=tmin[k],
                            date=fdates[k].isoformat(),
                            kill=kill,
                            crop=crop_name(cid, lang, c["name"]),
                        ),
                        [
                            t("frost_step_tmin", lang, tmin=tmin[k]),
                            t("frost_step_thr", lang, crop=crop_name(cid, lang, c["name"]), kill=kill),
                        ],
                        ["tmin"],
                        t("model_frost", lang),
                        "frost",
                        0.6,
                        t("frost_note", lang),
                        [t("frost_caveat", lang)],
                        ["openmeteo_forecast"],
                    ),
                }
            )
    if len(tmax):
        k = int(np.nanargmax(tmax))
        if tmax[k] >= c["t_heat"] and planting <= today:
            out.append(
                {
                    "id": "heat",
                    "category": "weather",
                    "risk": "moderate" if tmax[k] < c["t_heat"] + 3 else "high",
                    "icon": "thermometer",
                    "title": t(
                        "heat_title", lang, day=day_label(fdates[k], today, lang), t=round(float(tmax[k]))
                    ),
                    "detail": t("heat_detail", lang, crop=crop_name(cid, lang, c["name"]), thr=c["t_heat"]),
                    "due": fdates[k].isoformat(),
                    "amount": None,
                    "why": _why(
                        t("heat_sum", lang, tmax=tmax[k], thr=c["t_heat"]),
                        [
                            t("heat_step_tmax", lang, tmax=tmax[k], date=fdates[k].isoformat()),
                            t("heat_step_thr", lang, crop=crop_name(cid, lang, c["name"]), thr=c["t_heat"]),
                        ],
                        ["tmax"],
                        t("model_heat", lang),
                        "heat",
                        0.6,
                        t("heat_note", lang),
                        [],
                        ["openmeteo_forecast", "nasa_power"],
                    ),
                }
            )
    return out


def _planting_cards(
    ctx: FieldContext, cid: str, planting: dt.date, method: str, lang: str
) -> list[dict[str, Any]]:
    """Planting-window optimisation: simulate ±35 days around the intended date over past seasons."""
    c = crop(cid)
    w = ctx.weather
    years = _clim_years(ctx, 15)
    cands = [planting + dt.timedelta(days=d) for d in range(-35, 36, 7)]
    results = []
    for p in cands:
        req = gdd_requirement(c, w, p, years)
        ys = []
        for y in years:
            try:
                pp = dt.date(y, p.month, min(p.day, 28))
                r = simulate(
                    cid,
                    w,
                    pp,
                    taw_per_m=ctx.taw_per_m,
                    strategy="full" if method != "none" else "rainfed",
                    method=method,
                    gdd_req=req,
                )
                ys.append(r.yield_t_ha)
            except (ValueError, IndexError):
                pass
        if len(ys) >= 8:
            arr = np.array(ys)
            score = float(np.median(arr) - 0.5 * (np.median(arr) - np.percentile(arr, 10)))
            results.append((p, float(np.median(arr)), float(np.percentile(arr, 10)), score))
    if not results:
        return []
    best = max(results, key=lambda r: r[3])
    good = [r for r in results if r[3] >= 0.97 * best[3]]
    start, end = min(r[0] for r in good), max(r[0] for r in good)
    end = max(end, start + dt.timedelta(days=7))  # candidates are a week apart: a window is at least one week
    return [
        {
            "id": "sowing",
            "category": "planning",
            "risk": "low" if start <= planting <= end else "moderate",
            "icon": "calendar",
            "title": t("planting_title", lang, start=day_month(start, lang), end=day_month(end, lang)),
            "detail": t("planting_detail", lang, n=len(years), y=round(best[1], 1)),
            "due": start.isoformat(),
            "amount": None,
            "why": _why(
                t("sow_sum", lang),
                [t("sow_step", lang, date=day_month(p, lang), m=m, p10=p10) for p, m, p10, _ in results],
                [],
                t("model_sowing", lang),
                "planting",
                0.5,
                t("sow_note", lang),
                [],
                ["nasa_power", "soilgrids"],
            ),
        }
    ]


# --------------------------------------------------------------------------- what-if simulation
def simulate_api(req: dict[str, Any]) -> dict[str, Any]:
    lat, lon = float(req["lat"]), float(req["lon"])
    today = dt.date.fromisoformat(req["as_of"]) if req.get("as_of") else dt.date.today()
    ctx = build(lat, lon, today)
    cid = req["crop"]
    c = crop(cid)
    p0 = dt.date.fromisoformat(req["planting_date"])
    nyears = int(req.get("years") or 20)
    last = today.year - 1 if (today.month, today.day) < (12, 1) else today.year
    if c["type"] != "perennial" and (p0.month >= 9):
        last -= 1  # fall-sown crops need the following year's weather
    years = list(range(last - nyears + 1, last + 1))
    strategy = req.get("irrigation_strategy", "full")
    method = req.get("irrigation_method", "sprinkler")
    lang = req.get("lang") or "en"

    def run(w_: Any, strat: str) -> tuple[list[dict[str, Any]], Any]:
        req_gdd = gdd_requirement(
            c, ctx.weather, p0, years
        )  # thermal requirement fixed = variety stays the same
        out = []
        mid = None
        for y in years:
            try:
                p = dt.date(y, p0.month, min(p0.day, 28))
                r = simulate(
                    cid,
                    w_,
                    p,
                    taw_per_m=ctx.taw_per_m,
                    strategy=strat,
                    method=method,
                    allocation_mm=req.get("water_allocation_mm"),
                    gdd_req=req_gdd,
                    record_daily=(y == years[len(years) // 2]),
                )
            except (ValueError, IndexError):
                continue
            if r.daily:
                mid = r
            out.append(
                {
                    "year": y,
                    "yield_t_ha": r.yield_t_ha,
                    "et_mm": r.et_mm,
                    "irrigation_mm": r.irrigation_mm,
                    "rain_mm": r.rain_mm,
                    "stress_days": r.stress_days,
                    "heat_days": r.heat_days,
                    "frost_events": r.frost_events,
                    "harvest_date": r.end.isoformat(),
                    "biomass_t_ha": r.biomass_t_ha,
                    "cuts": r.cuts,
                }
            )
        return out, mid

    def summarise(rows: list[dict[str, Any]], base_median: float | None = None) -> dict[str, Any]:
        if not rows:
            return {}
        y = np.array([r["yield_t_ha"] for r in rows])
        irr = np.array([r["irrigation_mm"] for r in rows])
        et = np.array([r["et_mm"] for r in rows])
        ref = base_median if base_median else float(np.median(y))
        return {
            "yield_median": round(float(np.median(y)), 2),
            "yield_p10": round(float(np.percentile(y, 10)), 2),
            "yield_p90": round(float(np.percentile(y, 90)), 2),
            "irrigation_median_mm": round(float(np.median(irr)), 0),
            "et_median_mm": round(float(np.median(et)), 0),
            "stress_days_median": round(float(np.median([r["stress_days"] for r in rows])), 0),
            "water_productivity_kg_m3": round(float(np.median(y) * 1000 / max(1.0, np.median(et) * 10)), 2),
            "failure_risk_pct": round(100 * float(np.mean(y < 0.5 * ref)), 0),
        }

    dT = float(req.get("delta_t_c") or 0.0)
    rf = float(req.get("rain_factor") or 1.0)
    base_rows, _ = run(ctx.weather, "full" if strategy != "rainfed" else "rainfed")
    base = summarise(base_rows)
    rows, mid = run(ctx.weather.perturbed(dT, rf), strategy)
    summ = summarise(rows, base.get("yield_median"))
    daily = []
    if mid:
        dd = [dt.date.fromisoformat(x) for x in mid.daily["date"]]
        daily = [
            _series(
                "kc",
                t("series_kc", lang),
                "–",
                dd,
                mid.daily["kc"],
                "nasa_power",
                "modelled",
            ),
            _series(
                "soil_depletion",
                t("series_depletion_short", lang),
                "mm",
                dd,
                mid.daily["dr"],
                "nasa_power",
                "modelled",
            ),
            _series(
                "raw_threshold", t("series_raw", lang), "mm", dd, mid.daily["raw"], "nasa_power", "modelled"
            ),
        ]
    steps = [
        t("sim_step_years", lang, n=len(rows), y0=years[0], y1=years[-1]),
        t("sim_step_scenario", lang, strategy=word("strategy", strategy, lang), dt=dT, rf=rf),
        t("sim_step_yield", lang, y=summ.get("yield_median"), base=base.get("yield_median")),
        t(
            "sim_step_irrigation",
            lang,
            v=summ.get("irrigation_median_mm"),
            base=base.get("irrigation_median_mm"),
        ),
        t("sim_step_warmer", lang),
    ]
    return {
        "crop": cid,
        "scenario": req,
        "years": rows,
        "summary": summ,
        "baseline": base,
        "daily_example": daily,
        "why": _why(
            t("sim_sum", lang),
            steps,
            ["kc", "soil_depletion"],
            t("model_season", lang),
            "season-model",
            0.5,
            t("sim_note", lang),
            [t("sim_caveat_yieldgap", lang), t("sim_caveat_pests", lang)],
            ["nasa_power", "soilgrids"],
        ),
    }


# --------------------------------------------------------------------------- rotations
def rotations_api(req: dict[str, Any]) -> dict[str, Any]:
    lat, lon = float(req["lat"]), float(req["lon"])
    today = dt.date.fromisoformat(req["as_of"]) if req.get("as_of") else dt.date.today()
    ctx = build(lat, lon, today)
    w = ctx.weather
    method = req.get("irrigation", "sprinkler")
    irrigated = method != "none"
    strategy = (
        "allocation"
        if (irrigated and req.get("water_allocation_mm"))
        else ("full" if irrigated else "rainfed")
    )
    alloc = req.get("water_allocation_mm")
    lang = req.get("lang") or "en"
    pr = {
        "water": 0.3,
        "soil": 0.2,
        "income": 0.25,
        "pests": 0.1,
        "risk": 0.15,
        **(req.get("priorities") or {}),
    }
    gw_factor, gw_note = wsup.rotation_water_weight(lat, lon, irrigated, today, lang)
    pr["water"] *= gw_factor
    last_full = today.year - 2  # leave room for fall-sown crops into the following year
    years = list(range(last_full - 14, last_full + 1))
    pd_ = w.dates[: ctx.idx(today) + 1]
    normals = climmod.monthly_normals(pd_, w.tmax, w.tmin, w.rain, w.et0, 1991, 2020)
    onset = rot.rainy_onset(normals) if abs(lat) < 20 else None
    med = rot.is_mediterranean(normals, lat)

    # erosive rain share per month (heavy-rain days ≥ 95th pct of wet days, NASA POWER)
    rain = w.rain[: len(pd_)]
    wet = rain[rain >= 1]
    thr = float(np.percentile(wet, 90)) if len(wet) > 50 else 20.0
    months = np.array([d.month for d in pd_])
    heavy = np.array([np.sum(rain[(months == m)] * (rain[(months == m)] >= thr)) for m in range(1, 13)])
    erosive_share = list(heavy / heavy.sum()) if heavy.sum() > 0 else [1 / 12] * 12

    cfg = rot.rotation_config()
    current = {
        "id": "current",
        "name": t("rot_tpl_current_name", lang),
        "idea": t("rot_tpl_current_idea", lang),
        "slots": [{"crop": cr, "year": k + 1} for k, cr in enumerate(req["current_rotation"])],
    }
    templates = [current] + list(cfg["templates"])

    slot_cache: dict[tuple[str, str | None, str | None], rot.SlotStats] = {}

    def slot_stats(s: dict[str, Any]) -> rot.SlotStats:
        key = (s["crop"], s.get("plant"), s.get("irrigate_until"))
        if key not in slot_cache:
            slot_cache[key] = rot.evaluate_slot(
                s["crop"],
                w,
                years,
                lat,
                onset,
                ctx.taw_per_m,
                strategy,
                method,
                alloc,
                s.get("plant"),
                s.get("irrigate_until"),
                med,
            )
        return slot_cache[key]

    evaluated = []
    for tpl in templates:
        st = [slot_stats(s) for s in tpl["slots"]]
        # climate feasibility: every annual slot must complete its season in >= 80 % of years without killing frost
        feasible = True
        notes = []
        for s, ss in zip(tpl["slots"], st, strict=True):
            if ss.n < 0.6 * len(years):
                feasible = False
                notes.append(t("rot_note_few_seasons", lang, crop=crop_name(s["crop"], lang)))
            elif np.mean([f > 0 for f in ss.frost]) > 0.3 and crop(s["crop"])["type"] not in (
                "perennial",
                "cover",
            ):
                feasible = False
                notes.append(t("rot_note_frost", lang, crop=crop_name(s["crop"], lang)))
            elif (
                ss.yields
                and np.median(ss.yields)
                < 0.35 * crop(s["crop"])["typical_yield_t_ha"] * w.yield_factor(s["crop"], irrigated)
                and crop(s["crop"])["typical_yield_t_ha"] > 0
            ):
                feasible = False
                notes.append(t("rot_note_unfit", lang, crop=crop_name(s["crop"], lang)))
        if tpl["id"] != "current" and not feasible:
            continue
        if not irrigated and tpl["id"] != "current" and "irrigated" in tpl.get("tags", []):
            continue
        zone = "tropical" if abs(lat) < 20 else "temperate"
        if tpl["id"] != "current" and zone not in tpl.get("zones", ["temperate", "tropical"]):
            continue
        sc = rot.score_strategy(tpl, st, erosive_share, ctx.slope_pct, irrigated, smallholder=abs(lat) < 20)
        evaluated.append((tpl, st, sc, notes))

    raws = [e[2]["raw"] for e in evaluated]
    s_water = rot.relative_scores(raws, "water", higher_better=False, floor=0.0)
    s_income = rot.relative_scores(raws, "income", higher_better=True)
    out = []
    for k, (tpl, st, sc, notes) in enumerate(evaluated):
        fx = sc["fixed_scores"]
        scores = {
            "water": s_water[k],
            "income": s_income[k],
            "soil": fx["soil"],
            "pests": fx["pests"],
            "risk": fx["risk"],
        }
        total = sum(pr[m] * scores[m] for m in scores) / max(1e-9, sum(pr.values()))
        out.append((tpl, st, sc, notes, scores, round(float(total), 1)))
    cur = next(o for o in out if o[0]["id"] == "current")
    alts = sorted(
        [o for o in out if o[0]["id"] != "current" and not _same_rotation(o[0], cur[0])], key=lambda o: -o[5]
    )[:4]
    chosen = [cur] + alts

    def metric_list(o: Any) -> list[dict[str, Any]]:
        tpl, st, sc, notes, scores, total = o
        raw = sc["raw"]
        craw = cur[2]["raw"]
        cs = cur[4]
        water_label = t("met_water_irrigated" if irrigated else "met_water_rainfed", lang)
        return [
            {
                "id": "water",
                "label": water_label,
                "value": round(raw["water"]),
                "unit": "mm/yr",
                "score": scores["water"],
                "vs_current": round(scores["water"] - cs["water"], 1),
            },
            {
                "id": "income",
                "label": t("met_income_margin" if abs(lat) >= 20 else "met_income_net", lang),
                "value": round(raw["income"]),
                "unit": "USD/ha/yr",
                "score": scores["income"],
                "vs_current": round(scores["income"] - cs["income"], 1),
            },
            {
                "id": "soil",
                "label": t("met_soil", lang),
                "value": round(raw["soil"]),
                "unit": "0–100",
                "score": round(scores["soil"], 1),
                "vs_current": round(scores["soil"] - cs["soil"], 1),
            },
            {
                "id": "erosion",
                "label": t("met_erosion", lang),
                "value": round(raw["erosion"], 2),
                "unit": "index",
                "score": round(sc["fixed_scores"]["erosion"], 1),
                "vs_current": round(sc["fixed_scores"]["erosion"] - cur[2]["fixed_scores"]["erosion"], 1),
            },
            {
                "id": "pests",
                "label": t("met_pests", lang),
                "value": round(raw["pests"]),
                "unit": "0–100",
                "score": round(scores["pests"], 1),
                "vs_current": round(scores["pests"] - cs["pests"], 1),
            },
            {
                "id": "risk",
                "label": t("met_risk", lang),
                "value": round(100 * raw["risk"]),
                "unit": "% (lower better)",
                "score": round(scores["risk"], 1),
                "vs_current": round(scores["risk"] - cs["risk"], 1),
            },
            {
                "id": "nitrogen",
                "label": t("met_nitrogen", lang),
                "value": round(raw["nitrogen"]),
                "unit": "kg N/ha/yr",
                "score": min(100.0, raw["nitrogen"]),
                "vs_current": round(min(100.0, raw["nitrogen"]) - min(100.0, craw["nitrogen"]), 1),
            },
            {
                "id": "bare_days",
                "label": t("met_bare_days", lang),
                "value": round(raw["bare_days"]),
                "unit": "days/yr",
                "score": round(100 * (1 - raw["bare_days"] / 365), 1),
                "vs_current": round(100 * (craw["bare_days"] - raw["bare_days"]) / 365, 1),
            },
        ]

    strategies = []
    for o in chosen:
        tpl, st, sc, notes, scores, total = o
        mets = metric_list(o)
        strategies.append(
            {
                "id": tpl["id"],
                "name": _tpl_text(tpl, "name", lang),
                "is_current": tpl["id"] == "current",
                "slots": [
                    {
                        "year": s["year"],
                        "crop": s["crop"],
                        "season": _season_name(s, crop(s["crop"])),
                        "start_month": ss.plant.month,
                        "end_month": ((ss.plant.month - 1 + max(1, ss.length // 30)) % 12) + 1,
                    }
                    for s, ss in zip(tpl["slots"], st, strict=True)
                ],
                "calendar": sc["calendar"],
                "metrics": mets,
                "total_score": total,
                "why_suggested": _tpl_text(tpl, "idea", lang),
                "evidence": _evidence(tpl, st, ctx, normals, irrigated, lang),
                "benefits": _benefits(mets, lang) if tpl["id"] != "current" else [],
                "info_gaps": _gaps(tpl, lang),
                "risks_local_review": _risks(tpl, notes, lang),
                "sources": ["nasa_power", "srtm", "soilgrids"] + (["grace_fo"] if gw_note else []),
            }
        )

    vuln = _vulnerable_periods(ctx, normals, lat, lang)
    clim = climate_api(lat, lon, today, lang)
    return {
        "strategies": strategies,
        "climate_context": clim["insights"][:4],
        "groundwater_note": gw_note,
        "vulnerable_periods": vuln,
        "sources": [source_ref(s, ctx.statuses.get(s, "live")) for s in ("nasa_power", "srtm", "soilgrids")],
        "disclaimer": t("rot_disclaimer", lang),
        "years_simulated": [years[0], years[-1]],
    }


def _tpl_text(tpl: dict[str, Any], field: str, lang: str) -> str:
    """Translated template name/idea (config/messages/rotations.yaml); the YAML text if not translated."""
    key = f"rot_tpl_{tpl['id']}_{field}"
    return t(key, lang) if has(key) else str(tpl.get(field, ""))


def _same_rotation(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return [s["crop"] for s in a["slots"]] == [s["crop"] for s in b["slots"]] and not any(
        s.get("irrigate_until") for s in a["slots"]
    )


def _season_name(s: dict[str, Any], c: dict[str, Any]) -> str:
    if c["type"] == "perennial":
        return "perennial"
    if c["type"] == "cover":
        return "cover"
    m = int((s.get("plant") or "05-01").split("-")[0])
    return "winter" if m >= 9 else ("spring" if m <= 4 else "summer")


def _evidence(
    tpl: dict[str, Any],
    st: list[rot.SlotStats],
    ctx: FieldContext,
    normals: list[dict[str, float]],
    irrigated: bool,
    lang: str = "en",
) -> list[str]:
    ev = []
    hot = max(normals, key=lambda n: n["et0"])
    ev.append(
        t("rot_ev_peak", lang, month=month_name(int(hot["month"]), lang), et0=hot["et0"], rain=hot["precip"])
    )
    for s, ss in zip(tpl["slots"], st, strict=True):
        if not ss.yields:
            continue
        cname = crop_name(s["crop"], lang)
        if irrigated:
            ev.append(
                t("rot_ev_irrigated", lang, crop=cname, irr=np.median(ss.irr), y=np.median(ss.yields), n=ss.n)
            )
        else:
            ev.append(
                t(
                    "rot_ev_rainfed",
                    lang,
                    crop=cname,
                    y=np.median(ss.yields),
                    fail=100 * ss.fail_share,
                    n=ss.n,
                )
            )
    seen = set()
    uniq = []
    for e in ev:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    if ctx.slope_pct is not None:
        uniq.append(
            t("rot_ev_slope_low" if ctx.slope_pct < 3 else "rot_ev_slope_notable", lang, slope=ctx.slope_pct)
        )
    return uniq[:6]


_UNIT_KEYS = {
    "mm/yr": "unit_mm_yr",
    "USD/ha/yr": "unit_usd_ha_yr",
    "index": "unit_index",
    "% (lower better)": "unit_pct_lower_better",
    "kg N/ha/yr": "unit_kgn_ha_yr",
    "days/yr": "unit_days_yr",
    "days": "unit_days",
    "doy": "unit_doy",
}


def unit_text(unit: str, lang: str) -> str:
    """Display form of a wire unit in `lang` (numeric units such as mm or °C are language-neutral)."""
    key = _UNIT_KEYS.get(unit)
    return t(key, lang) if key else unit


def _benefits(mets: list[dict[str, Any]], lang: str = "en") -> list[str]:
    out = [
        t(f"rot_ben_{m['id']}", lang, v=m["value"], u=unit_text(m["unit"], lang))
        for m in mets
        if m["vs_current"] >= 8
    ]
    return out or [t("rot_ben_similar", lang)]


def _gaps(tpl: dict[str, Any], lang: str = "en") -> list[str]:
    gaps = [t("rot_gap_prices", lang)]
    if any(crop(s["crop"]).get("low_confidence") for s in tpl["slots"]):
        gaps.append(t("rot_gap_lowconf", lang))
    gaps.append(t("rot_gap_soil", lang))
    return gaps


def _risks(tpl: dict[str, Any], notes: list[str], lang: str = "en") -> list[str]:
    out = list(notes)
    crops_in = {s["crop"] for s in tpl["slots"]}
    if "alfalfa" in crops_in:
        out.append(t("rot_risk_alfalfa", lang))
    if any(s.get("irrigate_until") for s in tpl["slots"]):
        out.append(t("rot_risk_split", lang))
    if "teff" in crops_in:
        out.append(t("rot_risk_teff", lang))
    if "cover_rye_vetch" in crops_in:
        out.append(t("rot_risk_cover", lang))
    out.append(t("rot_risk_herbicide", lang))
    return out


def _vulnerable_periods(
    ctx: FieldContext, normals: list[dict[str, float]], lat: float, lang: str = "en"
) -> list[dict[str, Any]]:
    out = []
    for n in normals:
        if n["et0"] > 3 * max(1.0, n["precip"]) and n["et0"] > 100:
            out.append(
                {
                    "month": n["month"],
                    "issue": t("vuln_water", lang, et0=n["et0"], rain=n["precip"]),
                    "risk": "high",
                }
            )
        elif n["tmin"] < 0 and n["tmax"] > 10:
            out.append(
                {
                    "month": n["month"],
                    "issue": t("vuln_frost", lang, tmin=n["tmin"]),
                    "risk": "moderate",
                }
            )
        elif n["tmax"] >= 33:
            out.append(
                {
                    "month": n["month"],
                    "issue": t("vuln_heat", lang, tmax=n["tmax"]),
                    "risk": "moderate",
                }
            )
    return out


# --------------------------------------------------------------------------- climate
def climate_api(lat: float, lon: float, today: dt.date | None = None, lang: str = "en") -> dict[str, Any]:
    today = today or dt.date.today()
    ctx = build(lat, lon, today)
    w = ctx.weather
    n = ctx.idx(today) + 1
    d = w.dates[:n]
    # trends since 1984 need one homogeneous rain record: POWER only (IMERG starts in 1998)
    rain_h = ctx.rain_power if ctx.rain_power is not None else w.rain
    ym = climmod.yearly_metrics(d, w.tmax[:n], w.tmin[:n], rain_h[:n], w.et0[:n], lat)
    units = {
        "tmax_summer": "°C",
        "tmin_winter": "°C",
        "gdd": "°C·d",
        "frost_free_days": "days",
        "last_spring_frost_doy": "doy",
        "first_fall_frost_doy": "doy",
        "heat_days": "days",
        "precip_annual": "mm",
        "precip_growing": "mm",
        "et0_annual": "mm",
        "water_deficit": "mm",
        "heavy_rain_days": "days",
        "dry_spell_max": "days",
    }
    labels = {mid: (t(f"clim_{mid}", lang, thr=ym["heavy_thr_mm"]), u) for mid, u in units.items()}
    years = ym["years"]
    metrics = []
    insights = []
    for mid, (label, unit) in labels.items():
        vals = ym["metrics"][mid]
        slope, p = climmod.trend(years, vals)
        v = [x for x in vals if x is not None]
        base = float(np.mean([x for x in vals[:15] if x is not None])) if v else 0.0
        recent = float(np.mean([x for x in vals[-10:] if x is not None])) if v else 0.0
        metrics.append(
            {
                "id": mid,
                "label": label,
                "unit": unit,
                "values": [None if x is None else round(x, 1) for x in vals],
                "trend_per_decade": round(slope, 2),
                "p_value": round(p, 3),
                "baseline_mean": round(base, 1),
                "recent_mean": round(recent, 1),
            }
        )
        if p < 0.1 and mid in (
            "tmax_summer",
            "gdd",
            "frost_free_days",
            "heat_days",
            "water_deficit",
            "et0_annual",
            "precip_growing",
            "heavy_rain_days",
            "last_spring_frost_doy",
        ):
            insights.append(
                t(
                    "clim_insight_up" if slope > 0 else "clim_insight_down",
                    lang,
                    label=label,
                    slope=abs(slope),
                    unit=unit_text(unit, lang),
                    year=years[0],
                    base=base,
                    recent=recent,
                    p=p,
                )
            )
    if not insights:
        insights.append(t("clim_no_trend", lang, year=years[0]))
    normals = climmod.monthly_normals(d, w.tmax, w.tmin, w.rain, w.et0, 1991, 2020)
    return {
        "years": years,
        "metrics": metrics,
        "monthly_normals": normals,
        "insights": insights,
        "source": source_ref(
            "nasa_power",
            ctx.statuses.get("nasa_power", "live"),
            ctx.power_last.isoformat() if ctx.power_last else None,
        ),
    }


def crop_list() -> list[dict[str, Any]]:
    return [
        {
            "id": k,
            "name": v["name"],
            "names": crop_names(k),
            "family": v["family"],
            "type": v["type"],
            "n_fixing": v["n_fix_kg_ha"] > 0,
            "root_depth_m": v["root_m"][1],
            "season_days": int(sum(v["stages"])) if v["type"] != "perennial" else 365,
            "typical_yield_t_ha": v["typical_yield_t_ha"],
            "icon": v["icon"],
        }
        for k, v in crops().items()
    ]


def median_or_none(x: list[float]) -> float | None:
    return median(x) if x else None


__all__ = ["advice", "simulate_api", "rotations_api", "climate_api", "crop_list", "presets", "sources"]
