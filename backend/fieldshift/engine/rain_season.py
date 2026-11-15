"""Rain-season advisor: onset/cessation climatology, live 'this season' status card, sowing windows per crop,
and the planner constraint for rain-fed tropical fields. Science in ``science/onset.py``; ADR-021."""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
from typing import Any

import numpy as np

from ..data.sources import source_ref
from ..science import onset as on
from ..science.cropmodel import crops
from .context import FieldContext, build
from .messages import day_label, day_month, has, t, tr_crop

log = logging.getLogger("fieldshift.rain_season")
FORECAST_DAYS = 16
MODEL = "Agroclimatic onset (Sivakumar 1988; Stern et al. 1981), water-balance cessation (FAO), Liebmann/Dunning seasons"  # i18n: ok (t("model_onset"))


def _md(s: str | None, lang: str) -> str:
    """Localise a "15 Mar" day-month string from science/onset.py; anything else passes through."""
    if not s:
        return "?"
    try:
        return day_month(dt.datetime.strptime(f"{s} 2001", "%d %b %Y").date(), lang)
    except ValueError:
        return s


def _reason(site: on.SiteClimatology, lat: float, lang: str) -> str:
    app = on.params()["applicability"]
    if site.applicable:
        return t("reason_ok", lang)
    if abs(lat) > float(app["max_abs_lat"]):
        return t("reason_outside", lang, lat=app["max_abs_lat"])
    if not site.seasons:
        return t("reason_no_season", lang)
    return t("reason_no_dry", lang, n=site.dry_days)


# --------------------------------------------------------------------------- shared computation
def _site(ctx: FieldContext, today: dt.date) -> on.SiteClimatology:
    w = ctx.weather
    return on.site_climatology(w.dates, w.rain, w.et0, ctx.lat, ctx.idx(today))


def _status(ctx: FieldContext, today: dt.date, site: on.SiteClimatology) -> on.Status | None:
    w = ctx.weather
    i = ctx.idx(today)
    n = min(len(w.dates), i + 1 + FORECAST_DAYS)  # never look past the forecast horizon (also in replay mode)
    return on.season_status(w.dates[:n], w.rain[:n], w.et0[:n], i, site)


def _crop_rows(extra: str | None) -> list[tuple[str, str, list[float]]]:
    table = crops()
    ids = list(on.params()["crops"])
    if extra and extra not in ids:
        ids.insert(0, extra)
    out = []
    for cid in ids:
        c = table.get(cid)
        if c and c["type"] != "perennial":
            out.append((cid, c["name"], [float(x) for x in c["stages"]]))
    return out


def _sow_start(st: on.Status, today: dt.date) -> dt.date:
    sc = st.season
    if st.onset is not None:
        return max(st.onset, today)
    offs = [float(x) for x in sc.onset_offsets]
    exp = sc.date_at(float(np.median(offs)), st.year) if offs else sc.season.anchor(st.year)
    return max(exp, today)


def _short(name: str, lang: str = "en") -> str:
    return tr_crop(name, lang).split(" (")[0]


def _crop_advice(
    mine: dict[str, Any], sow: dict[str, Any], today: dt.date, lang: str, detail: str, risk: str
) -> tuple[str, str]:
    """Append the crop/variety part of the advice: sow-by date, or an earlier variety / shorter crop."""
    if mine["fits"]:
        until = dt.date.fromisoformat(mine["sow_until"])
        if until < today + dt.timedelta(days=60):
            detail += " " + t(
                "onset_sow_until", lang, crop=_short(mine["name"], lang), day=day_month(until, lang)
            )
        return detail, risk
    others = [r for r in sow["crops"] if r["crop"] != mine["crop"]]
    alt = max(others, key=lambda r: (r["fit_pct"], -r["cycle_days"])) if others else mine
    if (mine["max_variety_days_half"] or 0) < 45:
        if alt["fit_pct"] < 50:  # even the best short crop fails in most years: say so plainly
            late = t("onset_too_late_all", lang, crop=_short(mine["name"], lang), fit=alt["fit_pct"])
            # a "sow now" from the onset alone would contradict this: the crop advice wins
            detail = (
                late if detail.startswith(t("onset_advice_sow_now", lang, n=0)[:12]) else f"{detail} {late}"
            )
            return detail, "high" if risk in ("low", "moderate") else risk
        detail += " " + t(
            "onset_too_late",
            lang,
            crop=_short(mine["name"], lang),
            alt=_lc(_short(alt["name"], lang), lang),
            fit=alt["fit_pct"],
        )
        return detail, "moderate" if risk == "low" else risk
    days = (
        mine["max_variety_days"] if (mine["max_variety_days"] or 0) >= 60 else mine["max_variety_days_half"]
    )
    detail += " " + t(
        "onset_short_cycle",
        lang,
        crop=_short(mine["name"], lang),
        cycle=mine["cycle_days"],
        fit=mine["fit_pct"],
        days=days,
        alt=_lc(_short(alt["name"], lang), lang),
    )
    return detail, "moderate" if risk == "low" else risk


def _lc(s: str, lang: str) -> str:
    return s if lang == "de" else s.lower()


def _status_dict(st: on.Status, today: dt.date) -> dict[str, Any]:
    return {
        "season": st.season.season.key,
        "label": st.season.season.label,
        "year": st.year,
        "phase": st.phase,
        "window_start": st.window_start.isoformat(),
        "window_end": st.window_end.isoformat(),
        "onset": st.onset.isoformat() if st.onset else None,
        "onset_in_forecast": st.onset_in_forecast,
        "false_start_pct": st.false_pct,
        "false_start_events": st.false_n,
        "days_checked": st.days_checked,
        "last_false_start": st.last_false_start.isoformat() if st.last_false_start else None,
        "cessation": st.cessation.isoformat() if st.cessation else None,
        "rain_since_window_mm": st.rain_since_window_mm,
        "advice": _sow_advice(st, today),
    }


def _sow_advice(st: on.Status, today: dt.date) -> str:
    """sow_now | sow_with_care | wait | prepare | too_late | none"""
    cfg = on.params()["advice"]
    if st.phase == "started":
        p = st.false_pct if st.false_pct is not None else 50
        if p < cfg["sow_now_max_false_pct"]:
            return "sow_now"
        return "wait" if p >= cfg["wait_min_false_pct"] else "sow_with_care"
    if st.phase == "established":
        return "sow_now"
    if st.phase in ("before", "forecast"):
        return "prepare"
    if st.phase in ("not_started", "false_start", "failed"):
        return "wait"
    return "none"


def _insights(site: on.SiteClimatology, ref_year: int, lang: str = "en") -> list[str]:
    split = int(on.params()["advice"]["trend_split_year"])
    out = []
    for sc in site.seasons:
        s = sc.summary(ref_year, split)
        tr, lab = s["trend"], s["label"]
        y0 = sc.years[0].year if sc.years else 1984
        if tr["onset_p"] < 0.1:
            key = "ins_onset_later" if tr["onset_days_per_decade"] > 0 else "ins_onset_earlier"
            out.append(t(key, lang, season=lab, d=abs(tr["onset_days_per_decade"]), year=y0, p=tr["onset_p"]))
        if tr["length_p"] < 0.1:
            key = "ins_length_longer" if tr["length_days_per_decade"] > 0 else "ins_length_shorter"
            out.append(
                t(key, lang, season=lab, d=abs(tr["length_days_per_decade"]), year=y0, p=tr["length_p"])
            )
        a, b = tr["false_start_pct_before"], tr["false_start_pct_since"]
        if a is not None and b is not None and abs(b - a) >= 10:
            out.append(t("ins_false_starts", lang, season=lab, a=a, b=b, split=split))
    if not out and site.seasons:
        out.append(t("ins_no_shift", lang))
    return out


# --------------------------------------------------------------------------- API
def rain_season_api(
    lat: float, lon: float, crop: str | None = None, as_of: dt.date | None = None, lang: str = "en"
) -> dict[str, Any]:
    today = as_of or dt.date.today()
    ctx = build(lat, lon, today)
    site = _site(ctx, today)
    split = int(on.params()["advice"]["trend_split_year"])
    st = _status(ctx, today, site) if (site.seasons and site.applicable) else None
    sowing = None
    if st is not None and st.phase not in ("ended",):
        sowing = on.sowing_windows(
            st.season,
            st.year,
            _sow_start(st, today),
            _crop_rows(crop),
            float(on.params()["advice"]["reliability"]),
        )
    crit = on.Criteria.from_config()
    card = None
    if site.seasons and site.applicable:
        cards = _cards_from(ctx, site, st, crop, today, lang, None)
        card = cards[0] if cards else None
    return {
        "lat": lat,
        "lon": lon,
        "as_of": today.isoformat(),
        "applicable": site.applicable,
        "reason": _reason(site, lat, lang),
        "regime": site.info["regime"],
        "harmonic_ratio": site.info["harmonic_ratio"],
        "dry_season_days": site.dry_days,
        "criteria": {
            "onset": t(
                "crit_onset",
                lang,
                days=crit.onset_days,
                mm=crit.onset_mm,
                dry=crit.max_dry_spell_days,
                check=crit.check_days,
            ),
            "dry_day_mm": crit.dry_day_mm,
            "cessation": t("crit_cessation", lang, awc=crit.awc_mm),
            "false_start": t("crit_false_start", lang, dry=crit.max_dry_spell_days, check=crit.check_days),
        },
        "seasons": [sc.summary(today.year, split) for sc in site.seasons],
        "status": _status_dict(st, today) if st else None,
        "sowing": sowing,
        "card": card,
        "insights": _insights(site, today.year, lang),
        "method": t("model_onset", lang),
        "model_doc": "rain-onset",
        "source": source_ref(
            "nasa_power",
            ctx.statuses.get("nasa_power", "live"),
            ctx.power_last.isoformat() if ctx.power_last else None,
        ),
    }


# --------------------------------------------------------------------------- advice card
def onset_cards(
    ctx: FieldContext,
    cid: str,
    today: dt.date,
    lang: str,
    series: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The 'this season' rain card for rain-fed fields in tropical/monsoon settings. Never raises."""
    try:
        site = _site(ctx, today)
        if not site.applicable or not site.seasons:
            return []
        st = _status(ctx, today, site)
        return _cards_from(ctx, site, st, cid, today, lang, series)
    except Exception:  # advice must never fail because of this card
        log.exception("rain onset card failed")
        return []


def _cum_series(ctx: FieldContext, st: on.Status, today: dt.date, lang: str = "en") -> dict[str, Any]:
    """Cumulative rain since the search window opened, with the median of past seasons as 'normal'."""
    w = ctx.weather
    i0 = ctx.idx(st.window_start)
    i1 = min(len(w.dates), ctx.idx(today) + 1 + FORECAST_DAYS)
    i1 = min(i1, i0 + st.season.season.search_before + st.season.season.length + 30)
    rain = np.nan_to_num(w.rain)
    vals = np.cumsum(rain[i0:i1])
    past = []
    for sy in st.season.years:
        ws = st.season.season.anchor(sy.year) - dt.timedelta(days=st.season.season.search_before)
        j0 = ctx.idx(ws)
        if j0 >= 0 and j0 + (i1 - i0) <= ctx.idx(today):
            past.append(np.cumsum(rain[j0 : j0 + (i1 - i0)]))
    normal = np.median(np.array(past), axis=0) if past else None
    d = w.dates[i0:i1]
    return {
        "id": "rain_season_cum",
        "label": t(
            "series_rain_since", lang, date=day_month(st.window_start, lang), season=st.season.season.label
        ),
        "unit": "mm",
        "points": [
            {"date": x.isoformat(), "value": round(float(v), 1)} for x, v in zip(d, vals, strict=True)
        ],
        "source": "nasa_power",
        "kind": "observed",
        **(
            {
                "normal": [
                    {"date": x.isoformat(), "value": round(float(v), 1)}
                    for x, v in zip(d, normal, strict=True)
                ]
            }
            if normal is not None
            else {}
        ),
    }


def _cards_from(
    ctx: FieldContext,
    site: on.SiteClimatology,
    st: on.Status | None,
    cid: str | None,
    today: dt.date,
    lang: str,
    series: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if st is None or st.phase == "ended":
        return []
    sc = st.season
    split = int(on.params()["advice"]["trend_split_year"])
    summ = sc.summary(st.year, split)
    crit = on.Criteria.from_config()
    lab = sc.season.label
    on_d = summ["onset"] or {}
    p20, p50, p80 = (_md(on_d.get(k), lang) for k in ("p20", "p50", "p80"))
    offs = [float(x) for x in sc.onset_offsets]
    p80_date = sc.date_at(float(np.percentile(offs, 80)), st.year) if offs else st.window_end
    p20_date = sc.date_at(float(np.percentile(offs, 20)), st.year) if offs else st.window_start
    reliability = float(on.params()["advice"]["reliability"])
    rows = _crop_rows(cid)
    sow = on.sowing_windows(sc, st.year, _sow_start(st, today), rows, reliability)
    mine = next((r for r in sow["crops"] if r["crop"] == cid), None)
    advice = _sow_advice(st, today)
    n_years = len(sc.years)
    fs = summ["false_start_pct"]

    # ---- title / detail / risk / due per phase
    risk, due = "low", None
    if st.phase == "before":
        title = t("onset_before_title", lang, season=lab, date=p50)
        detail = t("onset_before_detail", lang, p20=p20, p80=p80, fs=round(fs or 0))
        due = p20_date.isoformat()
    elif st.phase == "not_started":
        late = today > p80_date
        title = t("onset_late_title" if late else "onset_waiting_title", lang, season=lab)
        detail = t("onset_waiting_detail", lang, p50=p50, p20=p20, p80=p80, mm=round(crit.onset_mm))
        risk = "moderate" if late else "low"
        due = today.isoformat()
    elif st.phase == "forecast":
        assert st.onset is not None
        title = t("onset_forecast_title", lang, season=lab, day=day_label(st.onset, today, lang))
        detail = t("onset_forecast_detail", lang, mm=round(crit.onset_mm))
        due = st.onset.isoformat()
    elif st.phase == "started":
        assert st.onset is not None
        pct = st.false_pct if st.false_pct is not None else 50
        title = t("onset_started_title", lang, season=lab, day=day_label(st.onset, today, lang), pct=pct)
        detail = t(f"onset_advice_{advice}", lang, n=crit.max_dry_spell_days)
        risk = {"sow_now": "low", "sow_with_care": "moderate", "wait": "high"}[advice]
        due = today.isoformat()
    elif st.phase == "false_start":
        assert st.last_false_start is not None
        title = t("onset_false_title", lang, day=day_label(st.last_false_start, today, lang))
        detail = t("onset_false_detail", lang, mm=round(crit.onset_mm))
        risk = "high"
        due = today.isoformat()
    elif st.phase == "established":
        assert st.onset is not None
        title = t("onset_established_title", lang, season=lab, day=day_label(st.onset, today, lang))
        end = sow["end_of_season"]
        detail = t(
            "onset_established_detail",
            lang,
            end=day_month(dt.date.fromisoformat(end), lang) if end else "?",
        )
    else:  # failed
        title = t("onset_failed_title", lang, season=lab)
        detail = t("onset_failed_detail", lang)
        risk = "high"
        due = today.isoformat()
    if mine is not None and st.phase in ("before", "not_started", "forecast", "started", "established"):
        detail, risk = _crop_advice(mine, sow, today, lang, detail, risk)

    # ---- Why
    regime = site.info["regime"]
    steps = [
        t(
            "on_step_seasons",
            lang,
            y0=sc.years[0].year if sc.years else 1984,
            y1=today.year - 1,
            list=", ".join(
                t(
                    "on_step_season_item",
                    lang,
                    season=s.season.label,
                    date=_md(s.summary(st.year, split)["climatological_onset"], lang),
                )
                for s in site.seasons
            ),
            regime=t(f"regime_{regime}", lang) if has(f"regime_{regime}") else regime,
            ratio=site.info["harmonic_ratio"],
        ),
        t(
            "on_step_rule",
            lang,
            days=crit.onset_days,
            mm=crit.onset_mm,
            dry=crit.max_dry_spell_days,
            check=crit.check_days,
        ),
        t("on_step_onset_stats", lang, season=lab, n=n_years, p50=p50, p20=p20, p80=p80),
        t(
            "on_step_false",
            lang,
            dry=crit.max_dry_spell_days,
            fs=fs if fs is not None else "–",
            failed=summ["failed_pct"],
        ),
    ]
    ln = summ["length_days"]
    if ln:
        steps.append(t("on_step_length", lang, awc=crit.awc_mm, p50=ln["p50"], p20=ln["p20"]))
    steps.append(
        t("on_step_rain_since", lang, date=day_month(st.window_start, lang), mm=st.rain_since_window_mm)
    )
    if st.phase == "started" and st.false_pct is not None:
        steps.append(
            t(
                "on_step_apparent",
                lang,
                date=st.onset,
                checked=st.days_checked,
                check=crit.check_days,
                n=st.false_n,
                pct=st.false_pct,
            )
        )
    if mine is not None:
        steps.append(
            t(
                "on_step_crop",
                lang,
                crop=tr_crop(mine["name"], lang),
                need=mine["need_days"],
                cycle=mine["cycle_days"],
                sow=mine["sow_from"],
                fit=mine["fit_pct"],
                end=sow["end_of_season"],
                rel=round(100 * reliability),
            )
            + (
                t("on_step_crop_fits", lang, date=mine["sow_until"])
                if mine["fits"]
                else t("on_step_crop_short", lang, days=mine["max_variety_days"])
            )
        )
    tr = summ["trend"]
    steps.append(
        t(
            "on_step_trend",
            lang,
            season=lab,
            on=tr["onset_days_per_decade"],
            onp=tr["onset_p"],
            ln=tr["length_days_per_decade"],
            lnp=tr["length_p"],
        )
    )
    if series is not None:
        with contextlib.suppress(ValueError, IndexError):
            series.append(_cum_series(ctx, st, today, lang))
    conf = 0.5 if st.phase != "forecast" else 0.4
    return [
        {
            "id": "rain_onset",
            "category": "planning",
            "risk": risk,
            "icon": "rainy",
            "title": title,
            "detail": detail,
            "due": due,
            "amount": None,
            "why": {
                "summary": t("onset_why_summary", lang, season=lab),
                "steps": steps,
                "series": ["rain_season_cum", "precip"],
                "model": t("model_onset", lang),
                "model_doc": "rain-onset",
                "confidence": conf,
                "confidence_note": t("on_note", lang),
                "caveats": [
                    t("on_caveat_grid", lang),
                    t("on_caveat_agronomic", lang),
                    t("on_caveat_cycle", lang),
                ],
                "sources": ["nasa_power", "openmeteo_forecast"],
            },
        }
    ]


# --------------------------------------------------------------------------- planner constraint
def planner_season(
    ctx: FieldContext,
    c: dict[str, Any],
    cid: str,
    p_next: dt.date,
    today: dt.date,
    irrigated: bool,
    lang: str = "en",
) -> dict[str, Any] | None:
    """Onset climatology for the season the planned sowing date belongs to (rain-fed, tropical, annual only).
    Returns the sowing limits the planner's date scan must respect, or None where they don't apply."""
    if irrigated or c["type"] == "perennial":
        return None
    try:
        site = _site(ctx, today)
    except (ValueError, IndexError):
        return None
    if not site.applicable or not site.seasons:
        return None
    best = None
    for sc in site.seasons:
        offs = [float(x) for x in sc.onset_offsets]
        if len(offs) < 8:
            continue
        for y in (p_next.year - 1, p_next.year, p_next.year + 1):
            med = sc.date_at(float(np.median(offs)), y)
            dist = abs((p_next - med).days)
            if best is None or dist < best[0]:
                best = (dist, sc, y)
    if best is None:
        return None
    _, sc, y = best
    offs = [float(x) for x in sc.onset_offsets]
    p20, p50, p80 = (sc.date_at(float(np.percentile(offs, q)), y) for q in (20, 50, 80))
    rel = float(on.params()["advice"]["reliability"])
    sow = on.sowing_windows(sc, y, p50, [(cid, c["name"], [float(x) for x in c["stages"]])], rel)
    row = sow["crops"][0] if sow["crops"] else None
    latest = dt.date.fromisoformat(row["sow_until"]) if row and row["sow_until"] else None
    return {
        "season": sc.season.label,
        "onset_p20": p20.isoformat(),
        "onset_median": p50.isoformat(),
        "onset_p80": p80.isoformat(),
        "latest_sowing": latest.isoformat() if latest else None,
        "end_of_season": sow["end_of_season"],
        "false_start_pct": sc.false_start_pct(),
        "max_variety_days": row["max_variety_days"] if row else None,
        "note": (
            t(
                "plan_onset_note",
                lang,
                season=sc.season.label,
                p50=day_month(p50, lang),
                p20=day_month(p20, lang),
                p80=day_month(p80, lang),
            )
            + (
                t("plan_onset_sow_by", lang, rel=round(100 * rel), date=day_month(latest, lang))
                if latest
                else t(
                    "plan_onset_early_variety",
                    lang,
                    n=round(10 * rel),
                    days=row["max_variety_days"] if row else "?",
                )
            )
        ),
    }


def onset_ok(d: dt.date, lim: dict[str, Any]) -> bool:
    """A planned sowing date respects the onset climatology: rains have started by then in at least half of
    past years, and the crop can still finish grain fill before the season ends (8 in 10 years)."""
    if d < dt.date.fromisoformat(lim["onset_median"]):
        return False
    return not (lim["latest_sowing"] and d > dt.date.fromisoformat(lim["latest_sowing"]))
