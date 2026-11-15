"""Heat-stress card for people (outdoor WBGT, NIOSH work–rest) and livestock (THI)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..data import heatwx
from ..science import heatstress as hs
from .messages import WEEKDAYS, t

RISKS = ["low", "moderate", "high", "severe"]
# Card risk per livestock class. "alert" (mild stress) is reported in the reasoning but does not raise
# a card by itself; Marai's sheep/goat classes are stricter (22.2 = onset), so only their top class counts.
LIVESTOCK_RISK = {"none": "low", "alert": "low", "danger": "moderate", "emergency": "high"}


def _card_class(animal: str, cls: str) -> str:
    if hs.LIVESTOCK[animal]["index"] == "marai":
        return {"emergency": "danger", "danger": "alert"}.get(cls, "none" if cls == "none" else "alert")
    return cls


DAY_HOURS = range(6, 21)  # outdoor working day considered for the advice (local time)


def animal_label(animal: str, lang: str = "en") -> str:
    """Livestock class name in `lang` (config/messages/heat.yaml: animal_<id>)."""
    return t(f"animal_{animal}", lang)


def _days_label(days: list[dt.date], lang: str) -> str:
    wd = WEEKDAYS.get(lang, WEEKDAYS["en"])
    if len(days) == 1:
        return wd[days[0].weekday()]
    return f"{wd[days[0].weekday()]}–{wd[days[-1].weekday()]}"


def _first_run(days: list[dt.date]) -> list[dt.date]:
    run = days[:1]
    for d in days[1:]:
        if (d - run[-1]).days == 1:
            run.append(d)
        else:
            break
    return run


def restricted_window(daily: dict[dt.date, dict[str, Any]], run: list[dt.date]) -> tuple[int, int]:
    """Clock hours [start, end) in which work is restricted on at least half of the days in `run`.
    Uses the run's worst level band ("high"/"severe" hours) when those exist, else any restriction."""
    worst = max((daily[d]["level"] for d in run), key=RISKS.index)
    band = ("high", "severe") if worst in ("high", "severe") else ("moderate", "high", "severe")
    counts: dict[int, int] = {}
    for d in run:
        for h, lv in daily[d]["hours"].items():
            if lv in band:
                counts[h] = counts.get(h, 0) + 1
    need = max(1, (len(run) + 1) // 2)
    hours = sorted(h for h, n in counts.items() if n >= need) or sorted(counts)
    return hours[0], hours[-1] + 1


def heat_assessment(ctx: Any, today: dt.date, days: int = 7) -> dict[str, Any] | None:
    """Hourly WBGT + THI for the next `days` days. None when no hourly weather is available."""
    end = today + dt.timedelta(days=days - 1)
    wx = heatwx.hourly_heat_weather(ctx, today, end)
    if wx is None:
        return None
    p = hs.pressure_hpa(ctx.elevation_m)
    rows = hs.assess_hours(
        ctx.lat, ctx.lon, wx.times, wx.t, wx.rh, wx.wind2, wx.ghi, wx.utc_offset_h, p, wx.direct
    )
    rows = [r for r in rows if today <= r.time.date() <= end]
    if not rows:
        return None
    daily: dict[dt.date, dict[str, Any]] = {}
    for r in rows:
        d = daily.setdefault(
            r.time.date(),
            {"wbgt_max": -99.0, "level": "low", "hours": {}, "peak": None, "thi": {}, "tmax": -99.0},
        )
        d["tmax"] = max(d["tmax"], r.t)
        if r.wbgt > d["wbgt_max"]:
            d["wbgt_max"], d["peak"] = r.wbgt, r
        clock = (r.time - dt.timedelta(hours=1)).hour  # hour-ending stamp -> hour start
        if clock in DAY_HOURS and r.level != "low":
            d["hours"][clock] = r.level
            if RISKS.index(r.level) > RISKS.index(d["level"]):
                d["level"] = r.level
        for a in hs.LIVESTOCK:
            v, cls = hs.livestock_class(a, r.t, r.rh)
            cur = d["thi"].get(a)
            if cur is None or v > cur[0]:
                d["thi"][a] = (v, cls)
    return {"daily": daily, "origin": wx.origin, "sources": wx.sources, "notes": wx.notes, "pressure": p}


def heat_stress_cards(
    ctx: Any, today: dt.date, lang: str, series: list[dict[str, Any]], why: Any
) -> list[dict[str, Any]]:
    try:
        a = heat_assessment(ctx, today)
    except Exception:  # never let an optional card break advice
        return []
    if a is None:
        return []
    daily = a["daily"]
    dates = sorted(daily)
    series.append(
        {
            "id": "wbgt_max",
            "label": t("series_wbgt", lang),
            "unit": "°C",
            "points": [{"date": d.isoformat(), "value": round(daily[d]["wbgt_max"], 1)} for d in dates],
            "source": a["sources"][0],
            "kind": "forecast",
        }
    )
    series.append(
        {
            "id": "thi_cattle",
            "label": t("series_thi", lang),
            "unit": "THI",
            "points": [
                {"date": d.isoformat(), "value": round(daily[d]["thi"]["dairy_cattle"][0], 1)} for d in dates
            ],
            "source": a["sources"][0],
            "kind": "forecast",
        }
    )
    hot = [d for d in dates if daily[d]["level"] != "low"]
    # livestock: worst class over the window per animal
    worst: dict[str, tuple[float, str, dt.date]] = {}
    for d in dates:
        for an, (v, cls) in daily[d]["thi"].items():
            if an not in worst or hs.LIVESTOCK_CLASSES.index(cls) > hs.LIVESTOCK_CLASSES.index(worst[an][1]):
                worst[an] = (v, cls, d)
    stressed = {an: w for an, w in worst.items() if w[1] != "none"}
    serious = {an: w for an, w in stressed.items() if _card_class(an, w[1]) in ("danger", "emergency")}
    if not hot and not serious:
        return []
    worker_risk = max((daily[d]["level"] for d in hot), key=RISKS.index, default="low")
    animal_risk = max(
        (LIVESTOCK_RISK[_card_class(an, w[1])] for an, w in stressed.items()), key=RISKS.index, default="low"
    )
    risk = max(worker_risk, animal_risk, key=RISKS.index)
    steps: list[str] = []
    caveats = [t("hs_caveat_sun", lang), t("hs_caveat_grid", lang), *a["notes"]]
    if hot:
        run = _first_run(hot)
        start_h, end_h = restricted_window(daily, run)
        peak_day = max(run, key=lambda d: daily[d]["wbgt_max"])
        pk = daily[peak_day]["peak"]
        rest_min = int(round((1 - pk.work_frac) * 60 / 5) * 5)
        level_word = t(f"heat_level_{worker_risk}", lang)
        key = "heat_stress_title" if start_h >= 8 else "heat_stress_title_allday"
        title = t(
            key,
            lang,
            level=level_word,
            days=_days_label(run, lang),
            start=f"{start_h:02d}:00",
            end=f"{end_h:02d}:00",
            safe=f"{start_h:02d}:00",
        )
        if pk.work_frac < 0.25:
            detail = t(
                "heat_stress_detail_stop",
                lang,
                wbgt=round(pk.wbgt, 1),
                start=f"{start_h:02d}:00",
                end=f"{end_h:02d}:00",
            )
        else:
            detail = t(
                "heat_stress_detail", lang, rest=rest_min, wbgt=round(pk.wbgt, 1), after=f"{end_h:02d}:00"
            )
        due = run[0].isoformat()
        steps += [
            t(
                "hs_step_weather",
                lang,
                origin=a["origin"].replace("+", " + "),
                date=peak_day.isoformat(),
                hour=f"{pk.time.hour:02d}",
                t=pk.t,
                rh=pk.rh,
                wind=pk.wind2,
                ghi=pk.ghi,
            ),
            t("hs_step_wbgt", lang, wbgt=pk.wbgt, p=a["pressure"]),
            t("hs_step_niosh", lang, rel300=hs.rel_wbgt(300), rel115=hs.rel_wbgt(115)),
            t(
                "hs_step_work",
                lang,
                wbgt=pk.wbgt,
                pct=round(pk.work_frac * 100),
                rest=rest_min,
                rel=hs.rel_wbgt(300, False),
            ),
            t(
                "hs_step_daily",
                lang,
                list=", ".join(f"{d.isoformat()[5:]} {daily[d]['wbgt_max']:.1f} °C" for d in dates),
            ),
            t(
                "hs_step_hours",
                lang,
                days=_days_label(run, lang),
                start=f"{start_h:02d}",
                end=f"{end_h:02d}",
            ),
        ]
    else:
        an, (v, cls, d0) = max(
            serious.items(), key=lambda kv: hs.LIVESTOCK_CLASSES.index(_card_class(kv[0], kv[1][1]))
        )
        title = t("heat_animals_title", lang, day=_days_label([d0], lang))
        detail = t("heat_animals_detail", lang)
        due = d0.isoformat()
    if stressed:
        if hot and serious:
            title += t("heat_title_animals", lang)
        for an, (v, cls, d0) in stressed.items():
            spec = hs.LIVESTOCK[an]
            thr = (
                t("hs_thr_single", lang, v=spec["threshold"])
                if "threshold" in spec
                else t("hs_thr_classes", lang, a=spec["bounds"][0], b=spec["bounds"][1], c=spec["bounds"][2])
            )
            name = animal_label(an, lang)
            steps.append(
                t(
                    "hs_step_animal",
                    lang,
                    animal=name[:1].upper() + name[1:],
                    v=v,
                    date=d0.isoformat(),
                    cls=t(f"thi_class_{cls}", lang),
                    thr=thr,
                    ref=spec["ref"],
                )
            )
        steps.append(t("hs_step_livestock", lang))
        caveats.append(t("hs_caveat_housed", lang))
    return [
        {
            "id": "heat_stress",
            "category": "weather",
            "risk": risk,
            "icon": "sunny",
            "title": title,
            "detail": detail,
            "due": due,
            "amount": None,
            "why": why(
                t("hs_sum", lang),
                steps,
                ["wbgt_max", "thi_cattle", "tmax"],
                t("model_heat_stress", lang),
                "heat-stress",
                0.6 if a["origin"] != "context+climatology" else 0.45,
                t("hs_note", lang),
                caveats,
                list(dict.fromkeys(["nasa_power", *a["sources"]])),
            ),
        }
    ]
