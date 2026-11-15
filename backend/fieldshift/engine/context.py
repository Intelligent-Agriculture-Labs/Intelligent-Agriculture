"""Assemble everything known about a location into one FieldContext (cached in-process).

Weather record = NASA POWER daily (1984 → latest available) + Open-Meteo recent past days to bridge the
POWER latency gap + 16-day forecast. Each day carries a provenance flag so the UI can show what is
observed (POWER), recent-model (bridge) or forecast.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..data import sources
from ..data.http import DataUnavailable
from ..science import et0 as et0mod
from ..science.cropmodel import Weather

log = logging.getLogger("fieldshift.context")
HIST_START = dt.date(1984, 1, 1)


@dataclass
class FieldContext:
    lat: float
    lon: float
    today: dt.date
    weather: Weather
    provenance: np.ndarray  # 0 = POWER, 1 = bridge (recent model analysis), 2 = forecast
    rh: np.ndarray
    hourly: dict[str, Any]
    power_last: dt.date | None
    elevation_m: float | None
    slope_pct: float | None
    soil: dict[str, Any] | None
    statuses: dict[str, str] = field(default_factory=dict)
    enrich: dict[str, list[tuple[dt.date, float]]] = field(default_factory=dict)
    forecast_et0: np.ndarray | None = None
    power: Any = None  # raw NASA POWER Daily (radiation, wind, humidity climatology for heat/solar advice)

    @property
    def taw_per_m(self) -> float:
        return float(self.soil["taw_mm_per_m"]) if self.soil else 140.0

    def idx(self, d: dt.date) -> int:
        return self.weather.index(d)

    def forecast_window(self, days: int = 7) -> slice:
        i = self.idx(self.today)
        return slice(i + 1, min(len(self.weather.dates), i + 1 + days))


_ctx_cache: dict[tuple[float, float, str], tuple[float, FieldContext]] = {}
_lock = threading.Lock()
_io_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ctx-io")


def _key(lat: float, lon: float, today: dt.date) -> tuple[float, float, str]:
    return (round(lat, 3), round(lon, 3), today.isoformat())


def build(lat: float, lon: float, today: dt.date | None = None, *, enrich: bool = False) -> FieldContext:
    today = today or dt.date.today()
    k = _key(lat, lon, today)
    with _lock:
        hit = _ctx_cache.get(k)
        if hit and (not enrich or hit[1].enrich):
            return hit[1]
    ctx = _build(lat, lon, today, enrich)
    with _lock:
        _ctx_cache[k] = (0.0, ctx)
        if len(_ctx_cache) > 64:
            _ctx_cache.pop(next(iter(_ctx_cache)))
    return ctx


def _build(lat: float, lon: float, today: dt.date, enrich: bool) -> FieldContext:
    statuses: dict[str, str] = {}
    is_historic = (dt.date.today() - today).days > 30  # back-testing / demo date in the past
    power_end = min(today + dt.timedelta(days=200), dt.date.today()) if is_historic else dt.date.today()
    # independent sources are fetched concurrently (cold start for a new field: ~40 s -> bounded by the slowest source)
    f_elev = _io_pool.submit(sources.elevation, lat, lon)
    f_soil = _io_pool.submit(sources.soil, lat, lon)
    f_fc = None if is_historic else _io_pool.submit(sources.forecast, lat, lon, 14, 16)
    power = sources.power_daily(lat, lon, HIST_START, power_end)
    elev, slope, st = f_elev.result()
    statuses["srtm"] = st
    soil = f_soil.result()
    statuses["soilgrids"] = soil["status"] if soil else "unavailable"
    statuses["nasa_power"] = power.status
    elev_used = elev if elev is not None else (power.meta.get("power_elevation_m") or 0.0)

    # last day with complete POWER meteorology
    ok = np.isfinite(power["T2M_MAX"]) & np.isfinite(power["PRECTOTCORR"])
    power_last = power.dates[int(np.where(ok)[0][-1])] if ok.any() else None

    doy = np.array([d.timetuple().tm_yday for d in power.dates])
    rs = power["ALLSKY_SFC_SW_DWN"].copy()
    et0 = et0mod.et0_pm(
        power["T2M_MAX"], power["T2M_MIN"], rs, power["WS2M"], lat, elev_used, doy, tdew=power["T2MDEW"]
    )
    hs = et0mod.et0_hargreaves(power["T2M_MAX"], power["T2M_MIN"], lat, doy)
    et0 = np.where(np.isfinite(et0), et0, hs)  # radiation often lags a few days -> Hargreaves fallback

    dates = list(power.dates)
    tmax = power["T2M_MAX"].copy()
    tmin = power["T2M_MIN"].copy()
    rain = power["PRECTOTCORR"].copy()
    rh = power["RH2M"].copy()
    prov = np.zeros(len(dates), dtype=np.int8)
    hourly: dict[str, Any] = {}
    fet0 = None

    if not is_historic:
        try:
            assert f_fc is not None
            fc, hourly = f_fc.result()
            statuses["openmeteo_forecast"] = fc.status
            fmap = {d: i for i, d in enumerate(fc.dates)}
            # bridge: overwrite missing/latest POWER days with Open-Meteo past days
            for i, d in enumerate(dates):
                if d in fmap and (
                    not np.isfinite(tmax[i]) or not np.isfinite(rain[i]) or d > (power_last or d)
                ):
                    j = fmap[d]
                    tmax[i], tmin[i], rain[i], rh[i] = (
                        fc["T2M_MAX"][j],
                        fc["T2M_MIN"][j],
                        fc["PRECTOTCORR"][j],
                        fc["RH2M"][j],
                    )
                    et0[i] = fc["ET0_OM"][j]
                    prov[i] = 1
            for j, d in enumerate(fc.dates):
                if d > dates[-1]:
                    dates.append(d)
                    tmax = np.append(tmax, fc["T2M_MAX"][j])
                    tmin = np.append(tmin, fc["T2M_MIN"][j])
                    rain = np.append(rain, fc["PRECTOTCORR"][j])
                    rh = np.append(rh, fc["RH2M"][j])
                    et0 = np.append(et0, fc["ET0_OM"][j])
                    prov = np.append(prov, 2 if d > today else 1)
            fet0 = fc["ET0_OM"]
        except DataUnavailable as e:
            log.warning("forecast unavailable: %s", e)
            statuses["openmeteo_forecast"] = "unavailable"
    else:
        # historic "as-of" mode: days after as_of are treated as a perfect forecast (for back-tests)
        for i, d in enumerate(dates):
            if d > today:
                prov[i] = 2
        try:
            hourly = sources.power_hourly(
                lat, lon, today - dt.timedelta(days=14), today + dt.timedelta(days=16)
            )
            statuses["nasa_power_hourly"] = "live"
        except (DataUnavailable, KeyError) as e:
            log.warning("POWER hourly unavailable: %s", e)

    # extend with climatology for long simulations beyond the forecast horizon (marked provenance 3)
    w = Weather(dates, tmax, tmin, np.where(np.isfinite(rain), rain, 0.0), et0)
    ctx = FieldContext(
        lat, lon, today, w, prov, rh, hourly, power_last, elev, slope, soil, statuses, forecast_et0=fet0, power=power
    )
    if enrich:
        ctx.enrich = enrichment(lat, lon, today)
        for sid in ("modis_ndvi", "mod16", "smap_l3e", "modis_lst"):
            ctx.statuses[sid] = "live" if ctx.enrich.get(sid) else "unavailable"
    return ctx


def enrichment(lat: float, lon: float, today: dt.date) -> dict[str, list[tuple[dt.date, float]]]:
    """NASA satellite layers from ORNL DAAC (best effort; served from cache for demo sites)."""
    out: dict[str, list[tuple[dt.date, float]]] = {}
    spans = {
        "modis_ndvi": (dt.date(2001, 1, 1), 40),  # 16-day composites, full record for anomalies
        "mod16": (today - dt.timedelta(days=3 * 365), 12),
        "smap_l3e": (today - dt.timedelta(days=120), 12),
        "modis_lst": (today - dt.timedelta(days=365), 5),
    }
    for sid, (start, max_req) in spans.items():
        try:
            out[sid] = sources.ornl_series(sid, lat, lon, start, today, max_requests=max_req)
        except DataUnavailable as e:
            log.info("enrichment %s unavailable: %s", sid, e)
            out[sid] = []
    return out
