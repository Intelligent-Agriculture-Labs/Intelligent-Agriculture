"""Data-source adapters. Each returns plain numpy-backed structures plus a SourceRef-like dict.

Backbone (always tried, no auth):
  * NASA POWER daily agroclimatology (weather, radiation) ............ power_daily
  * Open-Meteo forecast (16-day) + recent past days ................... forecast
  * OpenTopoData SRTM 30 m (NASA/USGS SRTM GL1) ....................... elevation
  * ISRIC SoilGrids 250 m ............................................. soil
Enrichment (NASA products via ORNL DAAC Global Subsets REST API, no auth, can be slow):
  * MODIS MOD13Q1 NDVI 250 m, MOD16A2GF ET 500 m, MOD11A2 LST 1 km, SMAP SPL3SMP_E 9 km
"""

from __future__ import annotations

import datetime as dt
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .http import DataUnavailable, Fetched, get_json

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMS = ["T2M_MAX", "T2M_MIN", "T2M", "RH2M", "T2MDEW", "WS2M", "ALLSKY_SFC_SW_DWN", "PRECTOTCORR"]
ORNL = "https://modis.ornl.gov/rst/api/v1"
# interactive requests give up fast; the precompute job (scripts/build_demo_cache.py) raises this
ORNL_RETRIES = int(__import__("os").environ.get("FIELDSHIFT_ORNL_RETRIES", "1"))

SOURCES: dict[str, dict[str, Any]] = {
    "nasa_power": dict(
        name="NASA POWER daily agroclimatology",
        provider="NASA Langley Research Center",
        url="https://power.larc.nasa.gov/",
        resolution="0.5° × 0.625° (~50 km) meteorology, 1° solar",
        latency="~2–5 days",
        is_nasa=True,
    ),
    "openmeteo_forecast": dict(
        name="Open-Meteo forecast (ECMWF IFS / GFS / ICON blend)",
        provider="Open-Meteo.com (CC BY 4.0)",
        url="https://open-meteo.com/",
        resolution="~9–25 km",
        latency="hourly updates",
        is_nasa=False,
    ),
    "srtm": dict(
        name="SRTM GL1 30 m elevation (via OpenTopoData)",
        provider="NASA/USGS SRTM; OpenTopoData",
        url="https://www.earthdata.nasa.gov/data/instruments/srtm",
        resolution="30 m",
        latency="static (2000)",
        is_nasa=True,
    ),
    "soilgrids": dict(
        name="SoilGrids 2.0",
        provider="ISRIC – World Soil Information (CC BY 4.0)",
        url="https://soilgrids.org/",
        resolution="250 m",
        latency="static",
        is_nasa=False,
    ),
    "modis_ndvi": dict(
        name="MODIS Terra MOD13Q1 NDVI (via ORNL DAAC subsets)",
        provider="NASA LP DAAC / ORNL DAAC",
        url="https://lpdaac.usgs.gov/products/mod13q1v061/",
        resolution="250 m, 16-day",
        latency="~2–4 weeks",
        is_nasa=True,
    ),
    "mod16": dict(
        name="MODIS MOD16A2GF evapotranspiration (via ORNL DAAC subsets)",
        provider="NASA LP DAAC / ORNL DAAC",
        url="https://lpdaac.usgs.gov/products/mod16a2gfv061/",
        resolution="500 m, 8-day",
        latency="yearly gap-filled",
        is_nasa=True,
    ),
    "modis_lst": dict(
        name="MODIS Terra MOD11A2 land-surface temperature",
        provider="NASA LP DAAC / ORNL DAAC",
        url="https://lpdaac.usgs.gov/products/mod11a2v061/",
        resolution="1 km, 8-day",
        latency="~2 weeks",
        is_nasa=True,
    ),
    "smap_l3e": dict(
        name="SMAP Enhanced L3 radiometer soil moisture SPL3SMP_E",
        provider="NASA NSIDC DAAC / ORNL DAAC",
        url="https://nsidc.org/data/spl3smp_e",
        resolution="9 km, daily (2–3 day revisit)",
        latency="~2 days",
        is_nasa=True,
    ),
    "era5_land": dict(
        name="ERA5 / ERA5-Land reanalysis soil moisture (via Open-Meteo archive)",
        provider="Copernicus C3S / ECMWF",
        url="https://cds.climate.copernicus.eu/",
        resolution="~9–25 km, hourly",
        latency="~5 days",
        is_nasa=False,
    ),
}


def source_ref(sid: str, status: str = "live", last_date: str | None = None) -> dict[str, Any]:
    return {"id": sid, **SOURCES[sid], "status": status, "last_date": last_date}


@dataclass
class Daily:
    """Daily series aligned on `dates` (python dates); vars are float arrays with NaN for missing."""

    dates: list[dt.date]
    vars: dict[str, np.ndarray]
    status: str = "live"
    meta: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, k: str) -> np.ndarray:
        return self.vars[k]

    def index_of(self, d: dt.date) -> int | None:
        if not self.dates or d < self.dates[0] or d > self.dates[-1]:
            return None
        return (d - self.dates[0]).days

    def slice(self, start: dt.date, end: dt.date) -> Daily:
        i0 = max(0, (start - self.dates[0]).days)
        i1 = min(len(self.dates), (end - self.dates[0]).days + 1)
        return Daily(self.dates[i0:i1], {k: v[i0:i1] for k, v in self.vars.items()}, self.status, self.meta)


def _r(x: float, n: int = 2) -> float:
    return round(float(x), n)


# --------------------------------------------------------------------------- NASA POWER
def power_daily(lat: float, lon: float, start: dt.date, end: dt.date) -> Daily:
    """NASA POWER daily point data (community=AG). Fill values (-999) -> NaN."""
    params = {
        "parameters": ",".join(POWER_PARAMS),
        "community": "AG",
        "latitude": _r(lat, 3),
        "longitude": _r(lon, 3),
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": "LST",
    }
    # long historical ranges never change -> cache for 30 days; recent windows 6 h
    ttl = 30 * 86400 if (dt.date.today() - end).days > 60 else 6 * 3600
    f: Fetched = get_json(POWER_URL, params, ttl_s=ttl, timeout_s=120)
    p = f.data["properties"]["parameter"]
    n = (end - start).days + 1
    dates = [start + dt.timedelta(days=i) for i in range(n)]
    out: dict[str, np.ndarray] = {}
    for k in POWER_PARAMS:
        arr = np.full(n, np.nan)
        for ds, v in p.get(k, {}).items():
            d = dt.date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
            i = (d - start).days
            if 0 <= i < n and v is not None and v > -998:
                arr[i] = float(v)
        out[k] = arr
    elev = f.data.get("geometry", {}).get("coordinates", [None, None, None])
    return Daily(dates, out, f.status, {"power_elevation_m": elev[2] if len(elev) > 2 else None})


# --------------------------------------------------------------------------- Open-Meteo forecast
def forecast(lat: float, lon: float, past_days: int = 14, days: int = 16) -> tuple[Daily, dict[str, Any]]:
    """Daily + hourly forecast incl. recent past days. Returns (daily, hourly-dict)."""
    params = {
        "latitude": _r(lat, 3),
        "longitude": _r(lon, 3),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration,"
        "shortwave_radiation_sum,wind_speed_10m_mean,relative_humidity_2m_mean,precipitation_probability_max",
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,dew_point_2m",
        "past_days": past_days,
        "forecast_days": days,
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }
    f = get_json("https://api.open-meteo.com/v1/forecast", params, ttl_s=3 * 3600)
    d = f.data["daily"]
    dates = [dt.date.fromisoformat(x) for x in d["time"]]

    def arr(k: str) -> np.ndarray:
        return np.array([np.nan if v is None else float(v) for v in d.get(k, [None] * len(dates))])

    daily = Daily(
        dates,
        {
            "T2M_MAX": arr("temperature_2m_max"),
            "T2M_MIN": arr("temperature_2m_min"),
            "PRECTOTCORR": arr("precipitation_sum"),
            "ET0_OM": arr("et0_fao_evapotranspiration"),
            "ALLSKY_SFC_SW_DWN": arr("shortwave_radiation_sum"),
            "WS10M": arr("wind_speed_10m_mean"),
            "RH2M": arr("relative_humidity_2m_mean"),
            "PRECIP_PROB": arr("precipitation_probability_max"),
        },
        f.status,
        {"timezone": f.data.get("timezone")},
    )
    return daily, f.data.get("hourly", {})


def era5_soil_moisture(lat: float, lon: float, start: dt.date, end: dt.date) -> Daily:
    """ERA5-Land soil moisture (daily mean of hourly), m3/m3, layers 0-7, 7-28, 28-100 cm."""
    params = {
        "latitude": _r(lat, 3),
        "longitude": _r(lon, 3),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,soil_moisture_28_to_100cm",
        "timezone": "auto",
    }
    f = get_json("https://archive-api.open-meteo.com/v1/archive", params, ttl_s=7 * 86400, timeout_s=120)
    h = f.data["hourly"]
    n = (end - start).days + 1
    dates = [start + dt.timedelta(days=i) for i in range(n)]
    out = {}
    for k, name in [
        ("soil_moisture_0_to_7cm", "SM_0_7"),
        ("soil_moisture_7_to_28cm", "SM_7_28"),
        ("soil_moisture_28_to_100cm", "SM_28_100"),
    ]:
        vals = np.array([np.nan if v is None else v for v in h.get(k, [])], dtype=float)
        vals = vals[: n * 24]
        if len(vals) < n * 24:
            vals = np.concatenate([vals, np.full(n * 24 - len(vals), np.nan)])
        with np.errstate(all="ignore"):
            out[name] = np.nanmean(vals.reshape(n, 24), axis=1)
    return Daily(dates, out, f.status)


# --------------------------------------------------------------------------- terrain & soil
def elevation(lat: float, lon: float) -> tuple[float | None, float | None, str]:
    """Elevation (m) and slope (%) from SRTM 30 m: centre + 4 neighbours at ±60 m."""
    dlat = 60 / 111_320
    dlon = 60 / (111_320 * max(0.1, math.cos(math.radians(lat))))
    pts = [(lat, lon), (lat + dlat, lon), (lat - dlat, lon), (lat, lon + dlon), (lat, lon - dlon)]
    locs = "|".join(f"{a:.5f},{b:.5f}" for a, b in pts)
    try:
        f = get_json("https://api.opentopodata.org/v1/srtm30m", {"locations": locs}, ttl_s=365 * 86400)
        z = [r.get("elevation") for r in f.data["results"]]
        if any(v is None for v in z):
            return (z[0], None, f.status)
        dzdy = (z[1] - z[2]) / 120
        dzdx = (z[3] - z[4]) / 120
        return float(z[0]), float(round(100 * math.hypot(dzdx, dzdy), 2)), f.status
    except (DataUnavailable, KeyError):
        return None, None, "unavailable"


def soil(lat: float, lon: float) -> dict[str, Any] | None:
    """SoilGrids 0–30 cm clay/sand/SOC means -> texture class + total available water."""
    params = [("lon", _r(lon, 4)), ("lat", _r(lat, 4)), ("value", "mean")]
    for p in ("clay", "sand", "soc"):
        params.append(("property", p))
    for depth in ("0-5cm", "5-15cm", "15-30cm"):
        params.append(("depth", depth))
    # httpx accepts list of tuples; cache key needs a dict -> encode in URL
    from urllib.parse import urlencode

    url = "https://rest.isric.org/soilgrids/v2.0/properties/query?" + urlencode(params)
    try:
        f = get_json(url, None, ttl_s=365 * 86400, timeout_s=60, retries=2)
    except DataUnavailable:
        return None
    vals: dict[str, float] = {}
    for layer in f.data.get("properties", {}).get("layers", []):
        name = layer["name"]
        d_factor = layer.get("unit_measure", {}).get("d_factor", 10)
        ms = [d["values"].get("mean") for d in layer["depths"] if d["values"].get("mean") is not None]
        if ms:
            vals[name] = float(np.mean(ms)) / d_factor
    if "clay" not in vals or "sand" not in vals:
        return None
    from ..science.soil import taw_mm_per_m, texture_class

    tex = texture_class(vals["sand"], vals["clay"])
    return {
        "texture": tex,
        "clay_pct": round(vals["clay"], 1),
        "sand_pct": round(vals["sand"], 1),
        "soc_g_kg": round(vals.get("soc", float("nan")), 1) if "soc" in vals else None,
        "taw_mm_per_m": taw_mm_per_m(tex),
        "source": "soilgrids",
        "status": f.status,
    }


# --------------------------------------------------------------------------- ORNL DAAC subsets
ORNL_PRODUCTS = {
    "modis_ndvi": ("MOD13Q1", "250m_16_days_NDVI", 0.0001, (-0.2, 1.0)),
    "mod16": ("MOD16A2GF", "ET_500m", 0.1, (0, 3000)),  # kg/m2 per 8 days (=mm/8d)
    "modis_lst": ("MOD11A2", "LST_Day_1km", 0.02, (200, 350)),  # K
    "smap_l3e": ("SPL3SMP_E", "soil_moisture", 1.0, (0.0, 0.7)),  # m3/m3
}


def _ornl_dates(product: str, lat: float, lon: float) -> list[tuple[str, str]]:
    f = get_json(
        f"{ORNL}/{product}/dates",
        {"latitude": _r(lat, 4), "longitude": _r(lon, 4)},
        ttl_s=3 * 86400,
        timeout_s=60,
        retries=ORNL_RETRIES,
    )
    if not isinstance(f.data, dict):
        raise DataUnavailable(str(f.data)[:200])
    return [(x["modis_date"], x["calendar_date"]) for x in f.data["dates"]]


def ornl_series(
    sid: str, lat: float, lon: float, start: dt.date, end: dt.date, max_requests: int = 60
) -> list[tuple[dt.date, float]]:
    """Point time series from ORNL's subset API (chunks of <=10 dates per request, as the API requires)."""
    product, band, scale, (lo, hi) = ORNL_PRODUCTS[sid]
    dates = [(m, dt.date.fromisoformat(c)) for m, c in _ornl_dates(product, lat, lon)]
    dates = [(m, c) for m, c in dates if start <= c <= end]
    chunks = [dates[i : i + 10] for i in range(0, len(dates), 10)][-max_requests:]

    def fetch(chunk: list[tuple[str, dt.date]]) -> list[tuple[dt.date, float]]:
        params = {
            "latitude": _r(lat, 4),
            "longitude": _r(lon, 4),
            "startDate": chunk[0][0],
            "endDate": chunk[-1][0],
            "kmAboveBelow": 0,
            "kmLeftRight": 0,
            "band": band,
        }
        ttl = 365 * 86400 if (dt.date.today() - chunk[-1][1]).days > 90 else 86400
        try:
            f = get_json(f"{ORNL}/{product}/subset", params, ttl_s=ttl, timeout_s=120, retries=ORNL_RETRIES)
        except DataUnavailable:
            return []
        out = []
        if isinstance(f.data, dict):
            for s in f.data.get("subset", []):
                v = s["data"][0] if s.get("data") else None
                if v is None:
                    continue
                val = float(v) * scale
                if lo <= val <= hi:
                    out.append((dt.date.fromisoformat(s["calendar_date"]), val))
        return out

    res: list[tuple[dt.date, float]] = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for part in ex.map(fetch, chunks):
            res.extend(part)
    return sorted(res)


def power_hourly(lat: float, lon: float, start: dt.date, end: dt.date) -> dict[str, list[Any]]:
    """NASA POWER hourly T2M/RH2M in Open-Meteo-like hourly dict form (used for replay/back-tests)."""
    params = {
        "parameters": "T2M,RH2M",
        "community": "AG",
        "latitude": _r(lat, 3),
        "longitude": _r(lon, 3),
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": "LST",
    }
    f = get_json(
        "https://power.larc.nasa.gov/api/temporal/hourly/point", params, ttl_s=365 * 86400, timeout_s=120
    )
    p = f.data["properties"]["parameter"]
    keys = sorted(p.get("T2M", {}))
    return {
        "time": [f"{k[:4]}-{k[4:6]}-{k[6:8]}T{k[8:10]}:00" for k in keys],
        "temperature_2m": [p["T2M"][k] if p["T2M"][k] > -998 else None for k in keys],
        "relative_humidity_2m": [p["RH2M"][k] if p["RH2M"].get(k, -999) > -998 else None for k in keys],
    }
