"""Advice cards for the global pest and disease risk models (`science/globalrisk.py`).

Cards keep the common card schema (id, category, risk, icon, title, detail, due, amount, why). A card is
produced only when (1) the crop is a host, (2) the field is inside the model's geographic range, (3) the crop is
in its at-risk season and (4) the score reaches the model's threshold within the forecast window.
Texts come from config/pest_disease.yaml (en, es, fr, sw, hi, de; English fallback).
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Any

import numpy as np
import yaml

from ..science import globalrisk as gr
from ..science import leafwet as lw
from .messages import CONFIG, day_label, risk_word, t

SATURATING_IN_TROPICS = {"gray_leaf_spot", "coffee_leaf_rust", "black_sigatoka"}
WINDOW_DAYS = 7


@lru_cache
def texts() -> dict[str, Any]:
    with open(CONFIG / "pest_disease.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def tx(key: str, lang: str, **kw: Any) -> str:
    m = texts()["messages"].get(key, {})
    tpl = m.get(lang) or m.get("en") or key
    return str(tpl).format(**kw)


def name(mid: str, lang: str) -> str:
    m = texts()["models"][mid]["name"]
    return str(m.get(lang) or m["en"])


def action(mid: str, lang: str) -> str:
    m = texts()["models"][mid]["action"]
    return str(m.get(lang) or m["en"])


def loc(v: Any, lang: str) -> str:
    """A YAML text that is either a plain string or a {en, es, ...} translation mapping."""
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("en") or "")
    return str(v)


def legacy_name(did: str, lang: str, default: str) -> str:
    m = texts().get("legacy_disease_names", {}).get(did)
    if not m:
        return default
    return str(m.get(lang) or m.get("en") or default)


def legacy_pest(pid: str, lang: str, default: str) -> str:
    m = texts().get("legacy_pest_names", {}).get(pid)
    return str((m.get(lang) or m.get("en")) if m else default)


def legacy_event(label: str, lang: str) -> str:
    """Life-stage label in `lang`, lower-case (titles embed it mid-sentence); English fallback."""
    if lang == "en":
        return label.lower()
    m = texts().get("legacy_pest_events", {}).get(label)
    return str(m.get(lang) if m and m.get(lang) else label.lower())


def risk_input(ctx: Any, planting: dt.date | None) -> gr.RiskInput:
    w = ctx.weather
    return gr.RiskInput(
        lat=ctx.lat,
        lon=ctx.lon,
        today=ctx.today,
        dates=list(w.dates),
        tmax=np.asarray(w.tmax, dtype=float),
        tmin=np.asarray(w.tmin, dtype=float),
        rain=np.asarray(w.rain, dtype=float),
        hourly=lw.from_dict(ctx.hourly) if ctx.hourly else None,
        elevation_m=ctx.elevation_m,
        planting=planting,
        rh=np.asarray(ctx.rh, dtype=float) if getattr(ctx, "rh", None) is not None else None,
    )


def _annual_rain(x: gr.RiskInput, years: int = 10) -> float | None:
    i = x.di(x.today)
    n = 365 * years
    if i < n:
        return None
    return float(np.nansum(x.rain[i - n : i])) / years


def cards(
    ctx: Any,
    cid: str,
    crop_type: str,
    today: dt.date,
    lang: str,
    planting: dt.date,
    series: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    x: gr.RiskInput | None = None
    perennial = crop_type == "perennial"
    for mid, m in gr.MODELS.items():
        if not gr.applies(mid, cid) or not m.in_range(ctx.lat, ctx.lon, ctx.elevation_m):
            continue
        if not m.in_season(today, planting, perennial):
            continue
        if m.hourly and not ctx.hourly:
            continue
        if x is None:
            x = risk_input(ctx, planting)
        if mid == "desert_locust":
            ar = _annual_rain(x)
            if ar is None or ar > gr.LOCUST_MAX_ANNUAL_RAIN_MM:
                continue
        gr.LANG.set(lang)
        res = m.fn(x)
        lo = today - dt.timedelta(days=m.window_back)
        hi = today + dt.timedelta(days=WINDOW_DAYS)
        win = {d: v for d, v in res.scores.items() if lo <= d <= hi}
        if not win:
            continue
        sdates = sorted(d for d in res.scores if (today - d).days <= 30)
        series.append(
            {
                "id": f"risk_{mid}",
                "label": t("series_model_risk", lang, name=name(mid, lang)),
                "unit": "0–1",
                "points": [{"date": d.isoformat(), "value": round(res.scores[d], 3)} for d in sdates],
                "source": "openmeteo_forecast" if m.hourly else "nasa_power",
                "kind": "forecast",
            }
        )
        dmax = max(win, key=lambda d: (win[d], -abs((d - today).days)))
        smax = win[dmax]
        if smax < m.min_score:
            continue
        first = min(d for d, v in win.items() if v >= m.min_score)
        due = max(first, today)
        risk = gr.risk_label(smax)
        # in the humid tropics gridded RH >= 90 % flags leaf wetness almost every night, so these models
        # saturate and cannot separate bad from normal years (VALIDATION V11): never louder than "moderate"
        capped = mid in SATURATING_IN_TROPICS and abs(ctx.lat) <= gr.TROPIC and risk in ("high", "severe")
        if capped:
            risk = "moderate"
        nm = name(mid, lang)
        title = tx(
            "risk_title_disease" if m.kind == "disease" else "risk_title_pest",
            lang,
            risk=risk_word(risk, lang),
            name=nm,
            day=day_label(due, today, lang),
        )
        meta = texts()["models"][mid]
        steps = [t("risk_step_model", lang, model=meta["model"])]
        steps += res.evidence.get(dmax, [])
        steps.append(t("risk_step_score", lang, score=smax, date=dmax.isoformat()))
        if "sv7" in res.extra:
            steps.append(t("risk_step_sv7", lang, date=dmax.isoformat(), sv=res.extra["sv7"].get(dmax, 0)))
        if meta.get("references"):
            steps.append(t("risk_step_refs", lang, refs="; ".join(meta["references"])))
        if capped:
            steps.append(t("risk_step_capped", lang))
        steps.append(t("risk_step_scout_disease" if m.kind == "disease" else "risk_step_scout_pest", lang))
        out.append(
            {
                "id": f"{m.kind}_{mid}",
                "category": m.kind,
                "risk": risk,
                "icon": "bug" if m.kind == "disease" else "bug-outline",
                "title": title,
                "detail": action(mid, lang),
                "due": due.isoformat(),
                "amount": None,
                "why": {
                    "summary": loc(meta["summary"], lang),
                    "steps": steps,
                    "series": [f"risk_{mid}", "tmin", "precip"],
                    "model": meta["model"],
                    "model_doc": "global-pest-disease",
                    "confidence": meta.get("confidence", 0.45),
                    "confidence_note": loc(meta["confidence_note"], lang)
                    if meta.get("confidence_note")
                    else t("risk_note_default", lang),
                    "caveats": [
                        t("risk_caveat_grid", lang),
                        *(loc(c, lang) for c in meta.get("caveats", [])),
                    ],
                    "sources": ["openmeteo_forecast", "nasa_power"]
                    if m.hourly
                    else ["nasa_power", "openmeteo_forecast"],
                },
            }
        )
    return out
