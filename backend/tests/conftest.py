"""Network-free fixtures: deterministic SYNTHETIC weather (clearly test-only) patched into the data layer."""

import datetime as dt

import numpy as np
import pytest

from fieldshift.data import sources
from fieldshift.engine import context


def _synthetic_power(lat, lon, start, end):
    n = (end - start).days + 1
    dates = [start + dt.timedelta(days=i) for i in range(n)]
    doy = np.array([d.timetuple().tm_yday for d in dates])
    season = np.cos(2 * np.pi * (doy - 200) / 365)
    rng = np.random.default_rng(42)
    rain = rng.gamma(0.6, 6, n) * (rng.random(n) < 0.15)
    v = {
        "T2M_MAX": 20 + 12 * season,
        "T2M_MIN": 6 + 10 * season,
        "T2M": 13 + 11 * season,
        "RH2M": np.full(n, 45.0),
        "T2MDEW": np.full(n, 2.0),
        "WS2M": np.full(n, 2.5),
        "ALLSKY_SFC_SW_DWN": 18 + 9 * season,
        "PRECTOTCORR": rain,
    }
    return sources.Daily(dates, v, "live", {"power_elevation_m": 1200})


def _synthetic_forecast(lat, lon, past_days=14, days=16):
    today = dt.date.today()
    dates = [today - dt.timedelta(days=past_days) + dt.timedelta(days=i) for i in range(past_days + days)]
    n = len(dates)
    daily = sources.Daily(
        dates,
        {
            "T2M_MAX": np.full(n, 28.0),
            "T2M_MIN": np.full(n, 14.0),
            "PRECTOTCORR": np.zeros(n),
            "ET0_OM": np.full(n, 6.0),
            "ALLSKY_SFC_SW_DWN": np.full(n, 25.0),
            "WS10M": np.full(n, 3.0),
            "RH2M": np.full(n, 40.0),
            "PRECIP_PROB": np.zeros(n),
        },
        "live",
    )
    hourly = {"time": [], "temperature_2m": [], "relative_humidity_2m": []}
    for d in dates:
        for h in range(24):
            hourly["time"].append(f"{d.isoformat()}T{h:02d}:00")
            hourly["temperature_2m"].append(14.0 + (h > 8) * 8)
            hourly["relative_humidity_2m"].append(95.0 if h < 8 else 60.0)
    return daily, hourly


@pytest.fixture(autouse=True)
def offline_synthetic(monkeypatch):
    monkeypatch.setattr(sources, "power_daily", _synthetic_power)
    monkeypatch.setattr(sources, "forecast", _synthetic_forecast)
    monkeypatch.setattr(sources, "elevation", lambda lat, lon: (1200.0, 1.5, "live"))
    monkeypatch.setattr(
        sources,
        "soil",
        lambda lat, lon: {
            "texture": "loam",
            "clay_pct": 20,
            "sand_pct": 40,
            "soc_g_kg": 8,
            "taw_mm_per_m": 145.0,
            "source": "soilgrids",
            "status": "live",
        },
    )
    monkeypatch.setattr(context, "enrichment", lambda lat, lon, today: {})
    from fieldshift.engine import service

    monkeypatch.setattr(service, "enrichment", lambda lat, lon, today: {})
    context._ctx_cache.clear()
    yield
