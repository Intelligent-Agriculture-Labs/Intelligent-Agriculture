"""Solar irrigation pump advisor: NASA POWER climatology + FAO-56 crop water need -> PV pump size and costs."""

from __future__ import annotations

import calendar
import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..science import solarpump as sp
from ..science.cropmodel import IRRIGATION_EFFICIENCY, crop
from .context import FieldContext, build
from .messages import crop_name, t, word

CONFIG = Path(__file__).resolve().parents[1] / "config"
MONTHS_EN = [calendar.month_name[m] for m in range(13)]
MONTHS = {
    "en": MONTHS_EN,
    "es": [
        "",
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ],
    "fr": [
        "",
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ],
    "de": [
        "",
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
    "sw": [
        "",
        "Januari",
        "Februari",
        "Machi",
        "Aprili",
        "Mei",
        "Juni",
        "Julai",
        "Agosti",
        "Septemba",
        "Oktoba",
        "Novemba",
        "Desemba",
    ],
    "hi": [
        "",
        "जनवरी",
        "फ़रवरी",
        "मार्च",
        "अप्रैल",
        "मई",
        "जून",
        "जुलाई",
        "अगस्त",
        "सितंबर",
        "अक्टूबर",
        "नवंबर",
        "दिसंबर",
    ],
}


@lru_cache
def cfg() -> dict[str, Any]:
    with open(CONFIG / "solar_pump.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def kc_curve(c: dict[str, Any]) -> list[float]:
    """Daily FAO-56 Kc over one season (piecewise linear: ini, development, mid, late).
    Perennials: the per-cutting-cycle curve is averaged and held over `season_days`."""
    ini, dev, mid, late = (int(x) for x in c["stages"])
    k: list[float] = []
    k += [c["kc_ini"]] * ini
    k += [c["kc_ini"] + (c["kc_mid"] - c["kc_ini"]) * (i + 1) / dev for i in range(dev)]
    k += [c["kc_mid"]] * mid
    k += [c["kc_mid"] + (c["kc_end"] - c["kc_mid"]) * (i + 1) / late for i in range(late)]
    if c.get("type") == "perennial":
        return [float(np.mean(k))] * int(c.get("season_days", 210))
    return [float(x) for x in k]


def monthly_climatology(ctx: FieldContext, years: int = 20) -> dict[int, dict[str, float]]:
    """Per calendar month: mean ET0 (mm/day), rain (mm/month), all-sky irradiance (kWh/m²/day), Tmax (°C)."""
    w = ctx.weather
    last = ctx.today.year - 1
    y0 = last - years + 1
    obs = np.array([p == 0 for p in ctx.provenance])
    out: dict[int, dict[str, float]] = {}
    mon = np.array([d.month for d in w.dates])
    yr = np.array([d.year for d in w.dates])
    in_years = (yr >= y0) & (yr <= last) & obs[: len(w.dates)]
    pw = ctx.power
    if pw is not None:
        pmon = np.array([d.month for d in pw.dates])
        pyr = np.array([d.year for d in pw.dates])
        psel = (pyr >= y0) & (pyr <= last)
        rs = pw["ALLSKY_SFC_SW_DWN"]
    for m in range(1, 13):
        sel = in_years & (mon == m)
        n_years = len(set(yr[sel].tolist())) or 1
        rain_month = float(np.nansum(w.rain[sel])) / n_years
        psh = float("nan")
        if pw is not None:
            v = rs[psel & (pmon == m)]
            v = v[np.isfinite(v)]
            if len(v):
                psh = float(np.mean(v)) / 3.6  # MJ m-2 d-1 -> kWh m-2 d-1
        out[m] = {
            "et0": float(np.nanmean(w.et0[sel])) if sel.any() else float("nan"),
            "rain": rain_month,
            "psh": psh,
            "tmax": float(np.nanmean(w.tmax[sel])) if sel.any() else float("nan"),
        }
    return out


def season_month_kc(c: dict[str, Any], planting: dt.date) -> dict[int, float]:
    """Mean daily Kc per calendar month (days outside the season count as 0) for a typical year."""
    kc = kc_curve(c)
    acc: dict[int, float] = {}
    for i, k in enumerate(kc):
        d = planting + dt.timedelta(days=i)
        acc[d.month] = acc.get(d.month, 0.0) + k
    return {m: acc[m] / calendar.monthrange(2001, m)[1] for m in acc}


def _polygon_area_ha(poly: list[list[float]] | None) -> float | None:
    if not poly or len(poly) < 3:
        return None
    lat0 = np.radians(np.mean([p[1] for p in poly]))
    xs = np.radians([p[0] for p in poly]) * 6371000 * np.cos(lat0)
    ys = np.radians([p[1] for p in poly]) * 6371000
    return float(abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1))) / 2 / 1e4)


def solar_pump(
    lat: float,
    lon: float,
    crop_id: str,
    planting_date: str | dt.date,
    irrigation: str = "drip",
    *,
    area_ha: float | None = None,
    polygon: list[list[float]] | None = None,
    static_head_m: float | None = None,
    diesel_price_usd_l: float | None = None,
    capex_usd_kwp: float | None = None,
    as_of: str | None = None,
    ctx: FieldContext | None = None,
    lang: str = "en",
) -> dict[str, Any]:
    conf = cfg()
    d = conf["defaults"]
    today = dt.date.fromisoformat(as_of) if as_of else dt.date.today()
    ctx = ctx or build(lat, lon, today)
    c = crop(crop_id)
    pd_ = planting_date if isinstance(planting_date, dt.date) else dt.date.fromisoformat(planting_date)
    area = area_ha or _polygon_area_ha(polygon) or float(d["area_ha"])
    method = irrigation if irrigation in conf["pressure_head_m"] else "drip"
    static = float(static_head_m if static_head_m is not None else d["static_head_m"])
    pressure = float(conf["pressure_head_m"][method])
    head = (static + pressure) * (1 + float(conf["friction_frac"]))
    eff = IRRIGATION_EFFICIENCY.get(method, 0.75) if method != "none" else 0.75
    clim = monthly_climatology(ctx)
    kcm = season_month_kc(c, pd_)
    months = [
        (m, clim[m]["et0"], kcm[m], clim[m]["rain"], clim[m]["psh"], clim[m]["tmax"])
        for m in sorted(kcm)
        if np.isfinite(clim[m]["et0"]) and np.isfinite(clim[m]["psh"]) and kcm[m] > 0
    ]
    if not months:
        raise ValueError("no NASA POWER climatology for this location")
    des = sp.size_system(
        months,
        area,
        head,
        eff,
        eta_mp=float(d["eta_mp"]),
        other_losses=float(d["other_losses"]),
        capex_usd_kwp=float(capex_usd_kwp or d["capex_usd_kwp"]),
        om_frac=float(d["om_frac"]),
        lifetime_y=int(d["lifetime_y"]),
        discount=float(d["discount"]),
        diesel_eta=float(d["diesel_eta"]),
        diesel_price_usd_l=float(diesel_price_usd_l or d["diesel_price_usd_l"]),
        diesel_om_frac=float(d["diesel_om_frac"]),
    )
    dm = next(r for r in des.months if r.month == des.design_month)
    needs_water = des.annual_m3 > 0 and des.kwp > 0
    mname = MONTHS.get(lang, MONTHS_EN)[dm.month]
    mword = word("irr", method, lang)
    steps = [
        t(
            "solar_step_need",
            lang,
            month=mname,
            et0=dm.et0_mm_day,
            y0=ctx.today.year - 20,
            y1=ctx.today.year - 1,
            crop=crop_name(crop_id, lang, c["name"]),
            kc=dm.kc,
        ),
        t(
            "solar_step_rain",
            lang,
            peff=dm.peff_mm,
            rain=dm.rain_mm,
            net=dm.net_mm,
            method=mword,
            eff=eff,
            gross=dm.gross_mm,
            m3=dm.volume_m3_day,
            area=area,
        ),
        t("solar_step_head", lang, head=head, static=static, method=mword, pressure=pressure),
        t(
            "solar_step_energy",
            lang,
            head=head,
            m3=dm.volume_m3_day,
            kwh=dm.e_hyd_kwh_day,
            wh=des.hyd_kwh_m3 * 1000,
        ),
        t(
            "solar_step_sun",
            lang,
            month=mname,
            psh=dm.psh,
            pr=dm.pr,
            tair=dm.t_air_c,
            tf=sp.pv_temperature_factor(dm.t_air_c),
            loss=d["other_losses"],
        ),
        t("solar_step_size", lang, eta=d["eta_mp"], kwp=des.kwp, flow=des.flow_m3_h),
        t(
            "solar_step_cost",
            lang,
            m3=f"{des.annual_m3:,.0f}",
            usd=des.solar_usd_m3,
            capex=f"{des.solar_capex_usd:,.0f}",
            life=d["lifetime_y"],
            disc=d["discount"],
            om=d["om_frac"],
        ),
        t(
            "solar_step_diesel",
            lang,
            eta=d["diesel_eta"],
            ml=des.diesel_l_m3 * 1000,
            usd=des.diesel_usd_m3,
            litres=f"{des.diesel_l_year:,.0f}",
            co2=des.co2_t_year,
        ),
    ]
    monthly = [
        {
            "month": r.month,
            "et0_mm_day": round(r.et0_mm_day, 2),
            "kc": round(r.kc, 2),
            "rain_mm": round(r.rain_mm, 1),
            "effective_rain_mm": round(r.peff_mm, 1),
            "net_irrigation_mm": round(r.net_mm, 1),
            "volume_m3_day": round(r.volume_m3_day, 1),
            "hydraulic_kwh_day": round(r.e_hyd_kwh_day, 2),
            "irradiance_kwh_m2_day": round(r.psh, 2),
            "performance_ratio": round(r.pr, 3),
            "kwp_needed": round(r.kwp_needed, 2),
        }
        for r in des.months
    ]
    return {
        "lat": lat,
        "lon": lon,
        "crop": crop_id,
        "irrigation": method,
        "area_ha": round(area, 3),
        "needs_irrigation": needs_water,
        "design_month": des.design_month,
        "peak_need_month": des.peak_need_month,
        "head_m": round(head, 1),
        "peak_volume_m3_day": round(dm.volume_m3_day, 1),
        "pv_kwp": round(des.kwp, 2),
        "pump_flow_m3_h": round(des.flow_m3_h, 2),
        "hydraulic_kwh_per_m3": round(des.hyd_kwh_m3, 4),
        "pv_kwh_per_m3": round(des.pv_kwh_m3, 4),
        "season_volume_m3": round(des.annual_m3),
        "season_pv_kwh": round(des.annual_pv_kwh),
        "solar_capex_usd": round(des.solar_capex_usd),
        "solar_usd_per_m3": round(des.solar_usd_m3, 3),
        "diesel_l_per_m3": round(des.diesel_l_m3, 4),
        "diesel_usd_per_m3": round(des.diesel_usd_m3, 3),
        "diesel_l_per_season": round(des.diesel_l_year),
        "co2_avoided_t_per_season": round(des.co2_t_year, 2),
        "monthly": monthly,
        "assumptions": {
            **d,
            "static_head_m": static,
            "pressure_head_m": pressure,
            "friction_frac": conf["friction_frac"],
        },
        "steps": steps,
        "sources": conf["sources"],
    }


def solar_pump_cards(
    ctx: FieldContext, inp: dict[str, Any], planting: dt.date, lang: str, why: Any
) -> list[dict[str, Any]]:
    """Optional low-priority planning card for irrigated fields."""
    if inp.get("irrigation", "none") == "none":
        return []
    try:
        r = solar_pump(
            ctx.lat,
            ctx.lon,
            inp["crop"],
            planting,
            inp.get("irrigation", "drip"),
            polygon=inp.get("polygon"),
            ctx=ctx,
            lang=lang,
        )
    except (ValueError, KeyError):
        return []
    if not r["needs_irrigation"] or not np.isfinite(r["pv_kwp"]):
        return []
    month = MONTHS.get(lang, MONTHS_EN)[r["design_month"]]
    return [
        {
            "id": "solar_pump",
            "category": "planning",
            "risk": "low",
            "icon": "sunny-outline",
            "title": t("solar_pump_title", lang, kwp=f"{r['pv_kwp']:.1f}"),
            "detail": t(
                "solar_pump_detail",
                lang,
                m3=round(r["peak_volume_m3_day"]),
                month=month,
                head=round(r["head_m"]),
                solar=f"{r['solar_usd_per_m3']:.2f}",
                diesel=f"{r['diesel_usd_per_m3']:.2f}",
                co2=f"{r['co2_avoided_t_per_season']:.1f}",
            ),
            "due": None,
            "amount": {"value": r["pv_kwp"], "unit": "kWp"},
            "why": why(
                t(
                    "solar_sum",
                    lang,
                    kwp=r["pv_kwp"],
                    m3=r["peak_volume_m3_day"],
                    litres=f"{r['diesel_l_per_season']:,}",
                ),
                r["steps"],
                ["et0", "precip"],
                t("model_solar", lang),
                "solar-pump",
                0.5,
                t("solar_note", lang),
                [
                    t("solar_caveat_head", lang),
                    t("solar_caveat_costs", lang),
                    t("solar_caveat_well", lang),
                    t("solar_caveat_rice", lang),
                ],
                ["nasa_power"],
            ),
        }
    ]
