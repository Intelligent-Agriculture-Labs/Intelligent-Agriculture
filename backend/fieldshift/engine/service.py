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

from ..data import sources
from ..data.sources import source_ref
from ..science import climate as climmod
from ..science import disease as dis
from ..science import drought as drt
from ..science import drought_ml
from ..science import pests as pst
from ..science import rotation as rot
from ..science.cropmodel import IRRIGATION_EFFICIENCY, crop, crops, gdd_requirement, simulate
from .context import FieldContext, build, enrichment
from .messages import day_label, risk_word, t

log = logging.getLogger("fieldshift.service")
CONFIG = Path(__file__).resolve().parents[1] / "config"
RISKS = ["low", "moderate", "high", "severe"]
_pool = ThreadPoolExecutor(max_workers=4)


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
        "detail": t("plan_detail", lang, crop=c["name"].lower(), state=t(f"state_{state_key}", lang)),
        "due": None,
        "amount": None,
        "why": _why(
            "Between seasons is the time to decide what to grow next. FieldShift simulates your current rotation and alternatives "
            "over the last 15 seasons of NASA POWER weather at this location.",
            ["Rotations are compared on water, income, soil health, erosion, pest cycles and climate risk."],
            ["tmax", "tmin"],
            "Season-state rule",
            "rotations",
            0.8,
            "Season state follows directly from temperature and the season model.",
            [],
            ["nasa_power"],
        ),
    }


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
    ctx = build(lat, lon, today)
    try:
        ctx.enrich = enr_future.result(timeout=float(inp.get("enrich_timeout_s", 8)))
    except FutTimeout:
        log.info("enrichment timed out; continuing without satellite layers")
        ctx.enrich = {}
    for sid in ("modis_ndvi", "mod16", "smap_l3e", "modis_lst"):
        ctx.statuses[sid] = "live" if ctx.enrich.get(sid) else "unavailable"

    cid = inp["crop"]
    c = crop(cid)
    planting = _season_start(c, dt.date.fromisoformat(inp["planting_date"]), today)
    method = inp.get("irrigation", "sprinkler")
    irrigated = method != "none"
    w = ctx.weather
    cards: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    i_today = ctx.idx(today)
    caveat_grid = "Weather comes from NASA POWER (~50 km grid) and a forecast (~10–25 km): conditions at your field can differ, especially near hills or water."

    # ---------- water balance (current season)
    wstate: dict[str, Any] = {}
    years = _clim_years(ctx)
    gdd_req = gdd_requirement(c, w, planting, years) if c["type"] != "perennial" else None
    known = None
    if inp.get("last_irrigation_date") and inp.get("last_irrigation_mm"):
        known = {dt.date.fromisoformat(inp["last_irrigation_date"]): float(inp["last_irrigation_mm"])}
    horizon = today + dt.timedelta(days=rules()["irrigation"]["lookahead_days"])
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
        sm_dates = ddates
        series.append(
            _series(
                "soil_depletion",
                "Root-zone water used (depletion)",
                "mm",
                sm_dates,
                daily["dr"],
                "nasa_power",
                "modelled",
            )
        )
        series.append(
            _series(
                "raw_threshold", "Stress point (RAW)", "mm", sm_dates, daily["raw"], "nasa_power", "modelled"
            )
        )
        series.append(
            _series(
                "taw", "Total available water (TAW)", "mm", sm_dates, daily["taw"], "soilgrids", "modelled"
            )
        )
        series.append(
            _series(
                "irrigation_applied",
                "Irrigation (model schedule)",
                "mm",
                sm_dates,
                daily["irr"],
                "nasa_power",
                "modelled",
            )
        )
        steps = [
            f"Season started {planting.isoformat()}; crop stage today: {res.final_stage} (Kc ≈ {res.final_kc:.2f}).",
            f"Reference evapotranspiration ET₀ (FAO-56 Penman–Monteith from NASA POWER) over the next 7 days: {et07:.0f} mm; forecast rain: {rain7:.0f} mm.",
            f"Soil: {ctx.soil['texture'] if ctx.soil else 'loam (default)'} holds ~{ctx.taw_per_m:.0f} mm water per metre; root zone today holds {taw_t:.0f} mm (TAW); stress begins after {raw_t:.0f} mm are used (RAW).",
            f"Estimated water used from the root zone today: {dr_t:.0f} mm ({pct_left}% of available water left).",
        ]
        caveats = [caveat_grid]
        if irrigated and not known:
            caveats.append(
                "We assume you irrigated whenever the model said so. Enter your last irrigation for a sharper estimate."
            )
        conf = 0.7 if known else 0.55
        ndays = rules()["irrigation"]["lookahead_days"]
        if irrigated:
            if stress_day and stress_day <= horizon:
                k = ddates.index(stress_day)
                net = daily["dr"][k]
                gross = max(rules()["irrigation"]["min_amount_mm"], round(net / eff))
                wstate["next_irrigation_mm"] = gross
                days_left = (stress_day - today).days
                risk = "high" if days_left <= rules()["irrigation"]["urgent_days"] else "moderate"
                steps.append(
                    f"Projecting forward with the forecast, depletion reaches the stress point on {stress_day.isoformat()}."
                )
                steps.append(
                    f"Refilling the root zone needs ~{net:.0f} mm net; with {method} irrigation (~{eff:.0%} efficient) apply ~{gross} mm."
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
                            f"Your crop will run short of easily available soil water around {stress_day.isoformat()}. Irrigating ~{gross} mm before then avoids yield loss.",
                            steps,
                            ["soil_depletion", "raw_threshold", "et0", "precip"],
                            "FAO-56 single-Kc root-zone water balance",
                            "water-balance",
                            conf,
                            "Water balance driven by NASA POWER and forecast; field irrigation history is assumed.",
                            caveats,
                            ["nasa_power", "openmeteo_forecast", "soilgrids", "srtm"],
                        ),
                    }
                )
            else:
                steps.append(
                    f"With the forecast, depletion stays below the stress point for at least {ndays} days."
                )
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
                            f"Soil water stays above the stress point for the next {ndays} days.",
                            steps,
                            ["soil_depletion", "raw_threshold", "et0", "precip"],
                            "FAO-56 single-Kc root-zone water balance",
                            "water-balance",
                            conf,
                            "Water balance driven by NASA POWER and forecast.",
                            caveats,
                            ["nasa_power", "openmeteo_forecast", "soilgrids"],
                        ),
                    }
                )
        elif not (stress_day and stress_day <= horizon):
            steps.append(
                f"With the forecast, the crop stays above the stress point for at least {ndays} days."
            )
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
                        f"Rain and stored soil water cover crop demand for the next {ndays} days.",
                        steps,
                        ["soil_depletion", "raw_threshold", "precip"],
                        "FAO-56 single-Kc root-zone water balance",
                        "water-balance",
                        0.5,
                        "Rain-fed estimate from NASA POWER + forecast.",
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
                        "Without rain or irrigation, the crop will start to close its stomata and lose yield.",
                        steps,
                        ["soil_depletion", "raw_threshold", "precip"],
                        "FAO-56 single-Kc root-zone water balance",
                        "water-balance",
                        0.5,
                        "Rain-fed estimate from NASA POWER + forecast.",
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
                    "detail": t("plan_detail", lang, crop=c["name"].lower(), state=state),
                    "due": None,
                    "amount": None,
                    "why": _why(
                        "Between seasons is the time to decide what to grow next. FieldShift simulates your current rotation and alternatives "
                        "over the last 15 seasons of NASA POWER weather at this location.",
                        [
                            f"7-day mean temperature {np.nanmean((recent[0] + recent[1]) / 2):.1f} °C; {c['name']} grows very little below ~{c['t_base'] + 6} °C.",
                            "Rotations are compared on water, income, soil health, erosion, pest cycles and climate risk.",
                        ],
                        ["tmax", "tmin"],
                        "Season-state rule",
                        "rotations",
                        0.8,
                        "Season state follows directly from temperature and the season model.",
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
            "Rain",
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
            "Reference ET₀ (crop water demand)",
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
            "Max temperature",
            "°C",
            wd,
            w.tmax[i0:i1],
            "nasa_power",
            "observed",
            [clim_tmax[k] for k in doy],
        )
    )
    series.append(_series("tmin", "Min temperature", "°C", wd, w.tmin[i0:i1], "nasa_power", "observed"))
    fc_start = next((wd[k].isoformat() for k in range(len(wd)) if kinds[k] == 2), None)

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
    sm_pct = _smap_block(ctx, series)
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
            "SPI-90 (rain vs. normal)",
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
        f"Rain in the last 90 days: {acc90[i_today]:.0f} mm; typical for this time of year: {np.median(s90):.0f} mm (NASA POWER 1984–{today.year})."
        if rank_pct is not None
        else "Rain history unavailable.",
        *[f"Indicator: {p}" for p in parts],
        "Levels follow the U.S. Drought Monitor scale (D0–D4); indicators are blended by a weighted 'convergence of evidence'.",
    ]
    # ---- AI drought classifier (gradient boosting on USDM labels) where it was validated
    ml_info = None
    model_name = "SPI/SPEI (McKee 1993; Vicente-Serrano 2010) + satellite indicators"
    if drought_ml.in_validated_domain(lat, lon) and drought_ml.load() is not None:
        try:
            Xf = drought_ml.feature_matrix(pd_, w.rain[:obs_end], w.et0[:obs_end], w.tmax[:obs_end])
            pr = drought_ml.predict(Xf[-1])
        except (ValueError, IndexError):
            pr = None
        if pr is not None:
            ml_level, proba = pr
            meta = drought_ml.load()[1]  # type: ignore[index]
            hv = meta["ml_heldout"]
            ml_info = {
                "level": ml_level,
                "probabilities": [round(p_, 3) for p_ in proba],
                "rules_level": level,
                "model": "Gradient-boosted trees trained on U.S. Drought Monitor maps",
                "heldout_within1_acc": hv["within1_acc"],
                "heldout_spearman": hv["spearman_vs_dsci"],
                "n_counties": meta["n_counties"],
            }
            dsteps.append(
                f"AI classifier (gradient boosting on {meta['n_samples']:,} weekly U.S. Drought Monitor maps from {meta['n_counties']} counties): "
                f"{drt.LABELS[ml_level]} with {100 * max(proba):.0f} % probability. On counties it never saw it is within one category "
                f"{100 * hv['within1_acc']:.0f} % of the time (rule-based blend: {drt.LABELS[level]})."
            )
            level = ml_level
            model_name = "AI drought classifier (gradient boosting on USDM labels, NASA POWER features) + rule-based SPI/SPEI blend"
    drought = {
        "ml": ml_info,
        "level": level,
        "label": drt.LABELS[level],
        "spi30": spi30,
        "spi90": spi90,
        "spei90": spei90,
        "spei365": spei365,
        "sm_percentile": sm_pct,
        "vhi": vhi,
        "why": _why(
            f"{drt.LABELS[level]} based on {len(parts)} indicators.",
            dsteps,
            ["spi90", "precip", "et0", "ndvi", "smap_sm"],
            model_name,
            "drought",
            0.6 if len(parts) >= 3 else 0.45,
            "Agreement between independent indicators raises confidence.",
            [
                "SPI uses ~50 km NASA POWER rain; local storms can be missed.",
                "SMAP soil moisture is a 9 km footprint and only the top ~5 cm.",
            ],
            ["nasa_power", "smap_l3e", "smap_l4", "modis_ndvi"],
        ),
    }
    if level >= rules()["drought"]["card_min_level"]:
        risk = RISKS[min(3, max(1, level - 1))]
        cards.append(
            {
                "id": "drought",
                "category": "drought",
                "risk": risk,
                "icon": "flame",
                "title": t("drought_title", lang, label=drt.LABELS[level]),
                "detail": t("drought_detail", lang, pct=max(1, rank_pct or 50)),
                "due": None,
                "amount": None,
                "why": drought["why"],
            }
        )
    if ndvi_card:
        cards.append(ndvi_card)

    # ---------- disease (hourly forecast)
    in_season = planting <= today and (
        c["type"] == "perennial" or not any(cd["id"] == "plan_rotation" for cd in cards)
    )
    if in_season:
        cards.extend(_disease_cards(ctx, cid, today, lang, series))
    # ---------- pests
    if in_season:
        cards.extend(_pest_cards(ctx, cid, today, lang, lat, planting))
    # ---------- frost / heat
    cards.extend(_temp_cards(ctx, cid, today, lang, planting))

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
        )
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
            "Vegetation greenness (MODIS NDVI, 250 m)",
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
                f"The latest MODIS NDVI ({vals[last]:.2f}) is {abs(z):.1f} standard deviations below the {dates[0].year}–{today.year} average for this time of year ({mu:.2f}).",
                [
                    f"MODIS 16-day composite of {dates[last].isoformat()}: NDVI {vals[last]:.2f}.",
                    f"Same period in {int(same.sum()) - 1} earlier years: mean {mu:.2f}, standard deviation {sd:.2f}.",
                    "A strong negative anomaly can mean water stress, pest damage, hail, late planting or a different crop than in past years.",
                ],
                ["ndvi"],
                "NDVI anomaly (z-score vs. same-period climatology)",
                "ndvi",
                0.45,
                "250 m pixels mix your field with neighbours; a different crop than in past years also changes NDVI.",
                [
                    "MODIS pixel is 250 m (~6 ha): small fields are mixed with neighbouring land.",
                    "Cloudy periods reduce data quality.",
                ],
                ["modis_ndvi"],
            ),
        }
    return round(float(vci), 1), card


def _smap_block(ctx: FieldContext, series: list[dict[str, Any]]) -> float | None:
    """SMAP soil moisture: L4 root-zone percentile (preferred, already a climatological percentile) or L3E surface."""
    today = ctx.today
    pts = sources.smap_points(ctx.lat, ctx.lon)
    if pts:
        dates = [dt.date.fromisoformat(x) for x in pts["dates"]]
        keep = [k for k, d in enumerate(dates) if (today - dt.timedelta(days=365)) <= d <= today]
        if keep:
            kd = [dates[k] for k in keep]
            series.append(
                _series(
                    "smap_sm",
                    "Surface soil moisture (SMAP L3E, 9 km)",
                    "m³/m³",
                    kd,
                    [np.nan if pts["l3e_sm"][k] is None else pts["l3e_sm"][k] for k in keep],
                    "smap_l3e",
                    "observed",
                )
            )
            series.append(
                _series(
                    "smap_rootzone",
                    "Root-zone soil moisture (SMAP L4, 0–100 cm, 9 km)",
                    "m³/m³",
                    kd,
                    [np.nan if pts["l4_rootzone"][k] is None else pts["l4_rootzone"][k] for k in keep],
                    "smap_l4",
                    "observed",
                )
            )
            ctx.statuses["smap_l3e"] = "cache"
            ctx.statuses["smap_l4"] = "cache"
            if not ctx.enrich.get("smap_l3e"):
                ctx.enrich["smap_l3e"] = [
                    (dates[k], pts["l3e_sm"][k]) for k in keep if pts["l3e_sm"][k] is not None
                ]
            ctx.enrich.setdefault(
                "smap_l4",
                [(dates[k], pts["l4_rootzone"][k]) for k in keep if pts["l4_rootzone"][k] is not None],
            )
            recent = [pts["l4_rootzone_pctl"][k] for k in keep[-3:] if pts["l4_rootzone_pctl"][k] is not None]
            if recent and (today - kd[-1]).days <= 10:
                p = float(np.mean(recent))
                return round(p * 100 if p <= 1.0 else p, 1)
    sm = ctx.enrich.get("smap_l3e") or []
    if len(sm) < 5:
        return None
    sdates = [d for d, _ in sm]
    vals = np.array([v for _, v in sm])
    series.append(
        _series(
            "smap_sm", "Surface soil moisture (SMAP, 9 km)", "m³/m³", sdates, vals, "smap_l3e", "observed"
        )
    )
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
        if cid not in meta["crops"]:
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
                f"{meta['name']} infection risk",
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
                    disease=meta["name"],
                    day=day_label(first, today, lang),
                ),
                "detail": t("disease_detail", lang),
                "due": first.isoformat(),
                "amount": None,
                "why": _why(
                    f"Forecast hourly humidity and temperature favour {meta['name'].lower()} infection, peaking on {dmax.isoformat()}.",
                    [
                        f"Model: {meta['ref']}.",
                        f"On {dmax.isoformat()}: {wet_hours} hours with relative humidity ≥ 90 %, minimum temperature {tmin_d:.0f} °C.",
                        f"Risk score {smax:.2f} (0 = unfavourable, 1 = fully favourable).",
                        "Risk means the weather suits infection — it does not mean the disease is present. Scout before you spray.",
                    ],
                    [f"risk_{did}", "tmin", "precip"],
                    meta["ref"],
                    "disease",
                    0.5,
                    "Leaf wetness is estimated from humidity; forecast skill drops after ~3 days.",
                    [
                        "Forecast grid ~10–25 km; humid hollows and irrigated canopies are wetter than the grid.",
                        "Relative humidity ≥ 90 % is a proxy for leaf wetness.",
                    ],
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
            title = t("pest_title", lang, pest=p["name"], event=ev["label"].lower(), days=days_until)
            due = (today + dt.timedelta(days=days_until)).isoformat()
            action = ev["action"]
            risk = "moderate" if days_until > 3 else "high"
        elif p.get("recurring") and c_type != "perennial" and 0 <= (today - planting).days <= 60:
            title = f"{p['name']}: {lastev['action'] if lastev else ev['action'] if ev else ''}".strip()
            title = f"{p['name']}: scout weekly (generation {st['generation']})" if lang == "en" else title
            due = today.isoformat()
            action = "Young plants are most vulnerable in the whorl stage; scout 20 plants in 5 spots weekly (FAO FAW guidance)."
            risk = "moderate"
        elif recent and lastev:
            title = t("pest_now_title", lang, pest=p["name"], event=lastev["label"].lower())
            due = today.isoformat()
            action = lastev["action"]
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
                    f"Insects develop with heat. Since {st['biofix']}, {st['dd_today']} degree-days (base {p['t_low']} °C) have accumulated.",
                    [
                        f"Degree-days to date: {st['dd_today']} °C·d; in 7 days: {st['dd_in_week']} °C·d (NASA POWER + forecast).",
                        f"Next life stage '{ev['label'] if ev else lastev['label']}' at {ev['dd'] if ev else lastev['dd']} °C·d ({p['ref']}).",
                        "Degree-day models predict *when* to scout, not *how many* insects there are.",
                    ],
                    ["tmax", "tmin"],
                    f"Degree-day phenology ({p['ref']})",
                    "pests",
                    0.55,
                    "Thresholds are regional literature values; local biofix observations improve timing.",
                    [
                        "Air temperature from a ~50 km grid; field microclimate differs.",
                        "Uses 1 Jan (N) / 1 Jul (S) biofix unless a trap catch is entered.",
                    ],
                    ["nasa_power", "openmeteo_forecast"],
                ),
            }
        )
    return out


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
                    "detail": t("frost_detail", lang, crop=c["name"], kill=kill),
                    "due": fdates[k].isoformat(),
                    "amount": None,
                    "why": _why(
                        f"Forecast minimum {tmin[k]:.1f} °C on {fdates[k].isoformat()} vs. damage threshold {kill} °C for {c['name']}.",
                        [
                            f"Forecast Tmin {tmin[k]:.1f} °C.",
                            f"Damage threshold for {c['name']}: {kill} °C (literature).",
                        ],
                        ["tmin"],
                        "Threshold rule on forecast minimum temperature",
                        "frost",
                        0.6,
                        "Frost is very local; low spots can be 2–4 °C colder.",
                        [
                            "Forecast is for 2 m air temperature; ground frost can occur at higher air temperatures."
                        ],
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
                    "detail": t("heat_detail", lang, crop=c["name"], thr=c["t_heat"]),
                    "due": fdates[k].isoformat(),
                    "amount": None,
                    "why": _why(
                        f"Forecast maximum {tmax[k]:.1f} °C exceeds the heat-stress threshold of {c['t_heat']} °C.",
                        [
                            f"Forecast Tmax {tmax[k]:.1f} °C on {fdates[k].isoformat()}.",
                            f"Heat threshold for {c['name']}: {c['t_heat']} °C.",
                        ],
                        ["tmax"],
                        "Threshold rule on forecast maximum temperature",
                        "heat",
                        0.6,
                        "Short heat spikes matter most at flowering.",
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
            "title": t("planting_title", lang, start=start.strftime("%d %b"), end=end.strftime("%d %b")),
            "detail": t("planting_detail", lang, n=len(years), y=round(best[1], 1)),
            "due": start.isoformat(),
            "amount": None,
            "why": _why(
                "Sowing dates were simulated with the FieldShift season model over past seasons of NASA POWER weather.",
                [
                    f"{p.strftime('%d %b')}: median {m:.1f} t/ha, bad-year (p10) {p10:.1f} t/ha"
                    for p, m, p10, _ in results
                ],
                [],
                "Planting-window optimisation (season model × 15 years)",
                "planting",
                0.5,
                "Past weather is a guide, not a forecast; variety choice changes the result.",
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
                "Crop coefficient (canopy development)",
                "–",
                dd,
                mid.daily["kc"],
                "nasa_power",
                "modelled",
            ),
            _series(
                "soil_depletion", "Root-zone depletion", "mm", dd, mid.daily["dr"], "nasa_power", "modelled"
            ),
            _series(
                "raw_threshold", "Stress point (RAW)", "mm", dd, mid.daily["raw"], "nasa_power", "modelled"
            ),
        ]
    steps = [
        f"Simulated {len(rows)} seasons ({years[0]}–{years[-1]}) of real NASA POWER weather at this location.",
        f"Scenario: {strategy.replace('_', ' ')} irrigation, {dT:+.1f} °C, rain × {rf:.2f}.",
        f"Median yield {summ.get('yield_median')} t/ha vs. {base.get('yield_median')} t/ha with full irrigation and today's climate.",
        f"Median irrigation {summ.get('irrigation_median_mm')} mm vs. {base.get('irrigation_median_mm')} mm.",
        "Warmer scenarios shorten the season (thermal time) and raise water demand (ET₀ +3 %/°C).",
    ]
    return {
        "crop": cid,
        "scenario": req,
        "years": rows,
        "summary": summ,
        "baseline": base,
        "daily_example": daily,
        "why": _why(
            "What-if results from the FieldShift season model (FAO-56 water balance + FAO-33 yield response).",
            steps,
            ["kc", "soil_depletion"],
            "FAO-56 water balance + FAO-33 yield response + thermal-time phenology",
            "season-model",
            0.5,
            "Relative differences between scenarios are more reliable than absolute yields.",
            [
                "Yields are water-limited potentials for good management (scaled to typical yields). Low-input farms often reach far less "
                "(the 'yield gap'); compare scenarios, not absolute numbers.",
                "Pests, diseases and nutrient limits are not simulated.",
            ],
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
    pr = {
        "water": 0.3,
        "soil": 0.2,
        "income": 0.25,
        "pests": 0.1,
        "risk": 0.15,
        **(req.get("priorities") or {}),
    }
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
        "name": "Your current rotation",
        "idea": "What you grow today.",
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
                notes.append(f"{crop(s['crop'])['name']}: not enough simulated seasons")
            elif np.mean([f > 0 for f in ss.frost]) > 0.3 and crop(s["crop"])["type"] not in (
                "perennial",
                "cover",
            ):
                feasible = False
                notes.append(f"{crop(s['crop'])['name']}: frost during the season in >30 % of years")
            elif (
                ss.yields
                and np.median(ss.yields) < 0.35 * crop(s["crop"])["typical_yield_t_ha"]
                and crop(s["crop"])["typical_yield_t_ha"] > 0
            ):
                feasible = False
                notes.append(f"{crop(s['crop'])['name']}: local season too short/cold or too dry")
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
        water_label = "Irrigation water" if irrigated else "Crop water shortfall"
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
                "label": "Gross margin (indicative)"
                if abs(lat) >= 20
                else "Net revenue after ~30 % input costs (indicative)",
                "value": round(raw["income"]),
                "unit": "USD/ha/yr",
                "score": scores["income"],
                "vs_current": round(scores["income"] - cs["income"], 1),
            },
            {
                "id": "soil",
                "label": "Soil-health index",
                "value": round(raw["soil"]),
                "unit": "0–100",
                "score": round(scores["soil"], 1),
                "vs_current": round(scores["soil"] - cs["soil"], 1),
            },
            {
                "id": "erosion",
                "label": "Erosion risk (relative)",
                "value": round(raw["erosion"], 2),
                "unit": "index",
                "score": round(sc["fixed_scores"]["erosion"], 1),
                "vs_current": round(sc["fixed_scores"]["erosion"] - cur[2]["fixed_scores"]["erosion"], 1),
            },
            {
                "id": "pests",
                "label": "Pest-cycle disruption",
                "value": round(raw["pests"]),
                "unit": "0–100",
                "score": round(scores["pests"], 1),
                "vs_current": round(scores["pests"] - cs["pests"], 1),
            },
            {
                "id": "risk",
                "label": "Climate risk (bad seasons)",
                "value": round(100 * raw["risk"]),
                "unit": "% (lower better)",
                "score": round(scores["risk"], 1),
                "vs_current": round(scores["risk"] - cs["risk"], 1),
            },
            {
                "id": "nitrogen",
                "label": "Biological N",
                "value": round(raw["nitrogen"]),
                "unit": "kg N/ha/yr",
                "score": min(100.0, raw["nitrogen"]),
                "vs_current": round(min(100.0, raw["nitrogen"]) - min(100.0, craw["nitrogen"]), 1),
            },
            {
                "id": "bare_days",
                "label": "Bare-soil days",
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
                "name": tpl["name"],
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
                "why_suggested": tpl.get("idea", ""),
                "evidence": _evidence(tpl, st, ctx, normals, irrigated),
                "benefits": _benefits(mets) if tpl["id"] != "current" else [],
                "info_gaps": _gaps(tpl),
                "risks_local_review": _risks(tpl, notes),
                "sources": ["nasa_power", "srtm", "soilgrids"],
            }
        )

    vuln = _vulnerable_periods(ctx, normals, lat)
    clim = climate_api(lat, lon, today)
    return {
        "strategies": strategies,
        "climate_context": clim["insights"][:4],
        "vulnerable_periods": vuln,
        "sources": [source_ref(s, ctx.statuses.get(s, "live")) for s in ("nasa_power", "srtm", "soilgrids")],
        "disclaimer": "FieldShift compares rotations under the last 15 seasons of NASA weather at your location. It supports, but does not replace, "
        "your judgement and local agronomic advice. Prices and costs are indicative and must be checked against your market.",
        "years_simulated": [years[0], years[-1]],
    }


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
) -> list[str]:
    ev = []
    hot = max(normals, key=lambda n: n["et0"])
    ev.append(
        f"Peak crop water demand in {dt.date(2000, int(hot['month']), 1):%B}: ET₀ ≈ {hot['et0']:.0f} mm/month vs. {hot['precip']:.0f} mm rain (NASA POWER 1991–2020)."
    )
    for s, ss in zip(tpl["slots"], st, strict=True):
        if not ss.yields:
            continue
        cname = crop(s["crop"])["name"]
        if irrigated:
            ev.append(
                f"{cname}: simulated median irrigation {np.median(ss.irr):.0f} mm, median yield {np.median(ss.yields):.1f} t/ha over {ss.n} seasons."
            )
        else:
            ev.append(
                f"{cname}: simulated median yield {np.median(ss.yields):.1f} t/ha; failed seasons {100 * ss.fail_share:.0f} % of {ss.n}."
            )
    seen = set()
    uniq = []
    for e in ev:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    if ctx.slope_pct is not None:
        uniq.append(
            f"Field slope {ctx.slope_pct:.1f} % (NASA SRTM 30 m) — {'low' if ctx.slope_pct < 3 else 'notable'} erosion leverage."
        )
    return uniq[:6]


def _benefits(mets: list[dict[str, Any]]) -> list[str]:
    phr = {
        "water": "Uses less water: {v} {u}",
        "income": "Higher indicative margin: {v} {u}",
        "soil": "Healthier soil (index {v}/100)",
        "erosion": "Lower erosion risk (index {v})",
        "pests": "Breaks pest and disease cycles (score {v}/100)",
        "risk": "Fewer bad seasons ({v} % risk)",
        "nitrogen": "More biological nitrogen: {v} {u}",
        "bare_days": "Fewer bare-soil days: {v} {u}",
    }
    out = [
        phr[m["id"]].format(v=m["value"], u=m["unit"]) + " vs. your current rotation."
        for m in mets
        if m["vs_current"] >= 8
    ]
    return out or ["Similar overall to your current rotation; may suit different priorities."]


def _gaps(tpl: dict[str, Any]) -> list[str]:
    gaps = [
        "Prices and costs are national averages — local market access (hay buyers, elevators) is not known to FieldShift."
    ]
    if any(crop(s["crop"]).get("low_confidence") for s in tpl["slots"]):
        gaps.append(
            "Some crops here (e.g. teff, cover mixes) are not in FAO-56; their water parameters are literature estimates."
        )
    gaps.append("Soil data are 250 m SoilGrids estimates, not a field soil test.")
    return gaps


def _risks(tpl: dict[str, Any], notes: list[str]) -> list[str]:
    out = list(notes)
    crops_in = {s["crop"] for s in tpl["slots"]}
    if "alfalfa" in crops_in:
        out.append(
            "Alfalfa autotoxicity: do not re-seed alfalfa directly after alfalfa; check stand age and weeds."
        )
    if any(s.get("irrigate_until") for s in tpl["slots"]):
        out.append(
            "Split-season irrigation depends on water-right rules and stand health — confirm with your water district."
        )
    if "teff" in crops_in:
        out.append(
            "Teff needs a fine, firm seedbed and has a niche hay market — verify buyers before planting."
        )
    if "cover_rye_vetch" in crops_in:
        out.append("Cover crops use some spring water in dry regions; terminate early if the season is dry.")
    out.append("Check herbicide carry-over restrictions before switching crops.")
    return out


def _vulnerable_periods(
    ctx: FieldContext, normals: list[dict[str, float]], lat: float
) -> list[dict[str, Any]]:
    out = []
    for n in normals:
        if n["et0"] > 3 * max(1.0, n["precip"]) and n["et0"] > 100:
            out.append(
                {
                    "month": n["month"],
                    "issue": f"High water demand: ET₀ {n['et0']:.0f} mm vs. rain {n['precip']:.0f} mm",
                    "risk": "high",
                }
            )
        elif n["tmin"] < 0 and n["tmax"] > 10:
            out.append(
                {
                    "month": n["month"],
                    "issue": f"Frost risk with active growth (mean Tmin {n['tmin']:.0f} °C)",
                    "risk": "moderate",
                }
            )
        elif n["tmax"] >= 33:
            out.append(
                {
                    "month": n["month"],
                    "issue": f"Heat stress likely (mean Tmax {n['tmax']:.0f} °C)",
                    "risk": "moderate",
                }
            )
    return out


# --------------------------------------------------------------------------- climate
def climate_api(lat: float, lon: float, today: dt.date | None = None) -> dict[str, Any]:
    today = today or dt.date.today()
    ctx = build(lat, lon, today)
    w = ctx.weather
    n = ctx.idx(today) + 1
    d = w.dates[:n]
    ym = climmod.yearly_metrics(d, w.tmax[:n], w.tmin[:n], w.rain[:n], w.et0[:n], lat)
    labels = {
        "tmax_summer": ("Warm-season mean max temperature", "°C"),
        "tmin_winter": ("Winter mean min temperature", "°C"),
        "gdd": ("Growing degree-days (base 10 °C)", "°C·d"),
        "frost_free_days": ("Frost-free season length", "days"),
        "last_spring_frost_doy": ("Last spring frost (day of year)", "doy"),
        "first_fall_frost_doy": ("First autumn frost (day of year)", "doy"),
        "heat_days": ("Days ≥ 35 °C", "days"),
        "precip_annual": ("Annual rain", "mm"),
        "precip_growing": ("Warm-season rain", "mm"),
        "et0_annual": ("Annual reference ET₀", "mm"),
        "water_deficit": ("Warm-season water deficit (ET₀ − rain)", "mm"),
        "heavy_rain_days": (f"Heavy-rain days (≥ {ym['heavy_thr_mm']} mm)", "days"),
        "dry_spell_max": ("Longest warm-season dry spell", "days"),
    }
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
            direction = "risen" if slope > 0 else "fallen"
            insights.append(
                f"{label} has {direction} by {abs(slope):.1f} {unit} per decade since {years[0]} "
                f"({base:.0f} → {recent:.0f} {unit}; Mann–Kendall p = {p:.2f})."
            )
    if not insights:
        insights.append(
            f"No statistically clear trend (p < 0.1) in the main indicators since {years[0]}; year-to-year variability dominates."
        )
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
