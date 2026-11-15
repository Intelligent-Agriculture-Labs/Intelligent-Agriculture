"""Hourly weather for heat-stress advice: temperature, humidity, wind and solar radiation.

Chain (each step degrades gracefully to the next):
  1. live / historic hours with all four variables
       * forecast mode: Open-Meteo hourly forecast (temperature, RH, 10 m wind, GHI, direct radiation)
       * as-of / replay mode: NASA POWER hourly (T2M, RH2M, WS2M, ALLSKY_SFC_SW_DWN)
  2. hours already in the field context (temperature + RH only) with wind and radiation from the
     NASA POWER daily climatology for the same days of year (WS2M, ALLSKY_SFC_SW_DWN spread over the
     day in proportion to the cosine of the solar zenith angle).
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..science import heatstress as hs
from .http import DataUnavailable, get_json

log = logging.getLogger("fieldshift.heatwx")
POWER_HOURLY_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
FAO56_U10_TO_U2 = 4.87 / np.log(67.8 * 10.0 - 5.42)  # FAO-56 eq. 47 (≈ 0.748)


@dataclass
class HourlyHeatWeather:
    times: list[dt.datetime]
    t: list[float]
    rh: list[float]
    wind2: list[float]
    ghi: list[float]
    direct: list[float] | None
    utc_offset_h: float
    origin: str  # "forecast" | "power_hourly" | "context+climatology"
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _f(v: Any) -> float:
    return float("nan") if v is None or (isinstance(v, (int, float)) and v <= -998) else float(v)


def forecast_hourly(lat: float, lon: float, days: int = 7) -> HourlyHeatWeather:
    params = {
        "latitude": round(lat, 3),
        "longitude": round(lon, 3),
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,direct_radiation",
        "forecast_days": days,
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }
    f = get_json("https://api.open-meteo.com/v1/forecast", params, ttl_s=3 * 3600, timeout_s=15, retries=1)
    h = f.data["hourly"]
    times = [dt.datetime.fromisoformat(x) for x in h["time"]]
    u10 = [_f(v) for v in h["wind_speed_10m"]]
    return HourlyHeatWeather(
        times,
        [_f(v) for v in h["temperature_2m"]],
        [_f(v) for v in h["relative_humidity_2m"]],
        [u * FAO56_U10_TO_U2 for u in u10],
        [_f(v) for v in h["shortwave_radiation"]],
        [_f(v) for v in h["direct_radiation"]],
        float(f.data.get("utc_offset_seconds", round(lon / 15) * 3600)) / 3600.0,
        "forecast",
        ["openmeteo_forecast"],
    )


def power_hourly(lat: float, lon: float, start: dt.date, end: dt.date) -> HourlyHeatWeather:
    params = {
        "parameters": "T2M,RH2M,WS2M,ALLSKY_SFC_SW_DWN",
        "community": "AG",
        "latitude": round(lat, 3),
        "longitude": round(lon, 3),
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": "UTC",
    }
    f = get_json(POWER_HOURLY_URL, params, ttl_s=365 * 86400, timeout_s=60, retries=1)
    p = f.data["properties"]["parameter"]
    keys = sorted(p.get("T2M", {}))
    off = float(round(lon / 15.0))  # nominal time zone; shown hours are approximate local time
    units = str(f.data.get("parameters", {}).get("ALLSKY_SFC_SW_DWN", {}).get("units", "MJ/hr"))
    to_wm2 = 1e6 / 3600.0 if "MJ" in units else 1.0  # POWER hourly irradiance is MJ m-2 per hour
    times = [
        dt.datetime(int(k[:4]), int(k[4:6]), int(k[6:8]), int(k[8:10])) + dt.timedelta(hours=off + 1)
        for k in keys
    ]  # POWER hourly stamps mark the start of the hour; we use hour-ending stamps like Open-Meteo
    return HourlyHeatWeather(
        times,
        [_f(p["T2M"][k]) for k in keys],
        [_f(p["RH2M"].get(k)) for k in keys],
        [_f(p["WS2M"].get(k)) for k in keys],
        [_f(p["ALLSKY_SFC_SW_DWN"].get(k)) * to_wm2 for k in keys],  # W/m² (hourly mean irradiance)
        None,
        off,
        "power_hourly",
        ["nasa_power"],
    )


def _doy_clim(power: Any, var: str, day: dt.date, years: int = 10, halfwin: int = 7) -> float | None:
    """Mean of a POWER daily variable within ±halfwin days of `day`'s day of year over recent years."""
    if power is None or var not in power.vars:
        return None
    arr = power[var]
    vals: list[float] = []
    for y in range(day.year - years, day.year + 1):
        try:
            centre = day.replace(year=y)
        except ValueError:
            centre = day.replace(year=y, day=28)
        i = power.index_of(centre)
        if i is None:
            continue
        seg = arr[max(0, i - halfwin) : i + halfwin + 1]
        vals.extend(float(v) for v in seg if np.isfinite(v))
    return float(np.mean(vals)) if vals else None


def from_context(ctx: Any, start: dt.date, end: dt.date) -> HourlyHeatWeather | None:
    """T/RH hours already in the field context + POWER climatological wind and radiation."""
    h = ctx.hourly or {}
    if not h.get("time"):
        return None
    times, t, rh = [], [], []
    for k, s in enumerate(h["time"]):
        tm = dt.datetime.fromisoformat(s)
        if start <= tm.date() <= end:
            times.append(tm)
            t.append(_f(h["temperature_2m"][k]))
            rh.append(_f(h["relative_humidity_2m"][k]))
    if not times:
        return None
    off = float(round(ctx.lon / 15.0))
    wind: list[float] = []
    ghi: list[float] = []
    by_day: dict[dt.date, list[int]] = {}
    for k, tm in enumerate(times):
        by_day.setdefault(tm.date(), []).append(k)
    for day, ks in by_day.items():
        u = _doy_clim(ctx.power, "WS2M", day) or 2.0
        h_mj = _doy_clim(ctx.power, "ALLSKY_SFC_SW_DWN", day)
        czas = [
            max(
                0.0,
                hs.cos_zenith(ctx.lat, ctx.lon, day, hs.solar_hour(day, times[k].hour - 0.5, ctx.lon, off)),
            )
            for k in ks
        ]
        tot = sum(czas)
        for cz in czas:
            wind.append(u)
            # MJ m-2 day-1 -> W m-2 for the hour, shaped by sun height (approximation of the daily cycle)
            ghi.append((h_mj * 1e6 / 3600.0) * cz / tot if (h_mj and tot > 0) else 0.0)
    return HourlyHeatWeather(
        times,
        t,
        rh,
        wind,
        ghi,
        None,
        off,
        "context+climatology",
        ["nasa_power"] + (["openmeteo_forecast"] if ctx.statuses.get("openmeteo_forecast") else []),
        [
            "Wind and sunshine for these hours are NASA POWER climatological averages for this time of year "
            "(the hourly forecast with wind and radiation was unavailable)."
        ],
    )


def hourly_heat_weather(ctx: Any, start: dt.date, end: dt.date) -> HourlyHeatWeather | None:
    is_historic = (dt.date.today() - ctx.today).days > 30
    try:
        if is_historic:
            return power_hourly(ctx.lat, ctx.lon, start - dt.timedelta(days=1), end + dt.timedelta(days=1))
        return forecast_hourly(ctx.lat, ctx.lon, days=min(16, (end - dt.date.today()).days + 1))
    except (DataUnavailable, KeyError, ValueError, TypeError) as e:
        log.info("hourly heat weather unavailable (%s); falling back to context + climatology", e)
    return from_context(ctx, start, end)
