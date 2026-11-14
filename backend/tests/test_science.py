import datetime as dt

import numpy as np
import pytest

from fieldshift.science import climate, disease, drought, pests, soil
from fieldshift.science.cropmodel import Weather, crop, gdd, kc_at, simulate


def make_weather(days=800, tmax=30.0, tmin=15.0, rain=0.0, et0=6.0, start=dt.date(2020, 1, 1)):
    dates = [start + dt.timedelta(days=i) for i in range(days)]
    return Weather(dates, np.full(days, tmax), np.full(days, tmin), np.full(days, rain), np.full(days, et0))


def test_texture_and_taw():
    assert soil.texture_class(40, 20) == "loam"
    assert soil.texture_class(92, 3) == "sand"
    assert soil.texture_class(20, 50) == "clay"
    assert soil.texture_class(10, 10) == "silt"
    assert soil.texture_class(25, 15) == "silt loam"
    assert soil.taw_mm_per_m("loam") == 145


def test_gdd_cutoffs():
    assert gdd(np.array([35.0]), np.array([5.0]), 10.0)[0] == pytest.approx(10.0)  # (30+10)/2-10


def test_kc_curve_fao56_shape():
    c = crop("maize")
    assert kc_at(c, 0.0)[0] == pytest.approx(0.30)
    assert kc_at(c, 0.5)[0] == pytest.approx(1.20)
    assert kc_at(c, 1.0)[0] == pytest.approx(0.35)


def test_water_balance_mass_closure():
    w = make_weather(rain=1.0)
    r = simulate(
        "maize",
        w,
        dt.date(2020, 5, 1),
        strategy="full",
        method="drip",
        gdd_req=1500,
        record_daily=True,
        initial_depletion_frac=0.0,
    )
    net_irr = r.irrigation_mm * 0.9
    # Dr_end = Dr_0 - P - I + ET + DP  (FAO-56 eq. 85 summed over the season, Dr_0 = 0)
    assert r.final_depletion_mm == pytest.approx(-r.rain_mm - net_irr + r.et_mm + r.deep_perc_mm, abs=1.0)


def test_full_irrigation_no_stress_and_rainfed_stress():
    w = make_weather(rain=0.0)
    full = simulate("maize", w, dt.date(2020, 5, 1), strategy="full", gdd_req=1500)
    dry = simulate("maize", w, dt.date(2020, 5, 1), strategy="rainfed", gdd_req=1500)
    assert full.et_mm == pytest.approx(full.etm_mm, rel=0.02)
    assert full.yield_t_ha == pytest.approx(crop("maize")["typical_yield_t_ha"], rel=0.05)
    assert dry.yield_t_ha < 0.3 * full.yield_t_ha
    assert dry.stress_days > 50


def test_deficit_uses_less_water():
    w = make_weather(rain=0.0)
    full = simulate("maize", w, dt.date(2020, 5, 1), strategy="full", gdd_req=1500)
    d50 = simulate("maize", w, dt.date(2020, 5, 1), strategy="deficit_50", gdd_req=1500)
    assert d50.irrigation_mm < full.irrigation_mm
    assert d50.yield_t_ha <= full.yield_t_ha


def test_alfalfa_cuts_follow_thermal_time():
    w = make_weather(tmax=28, tmin=12, rain=0.0)  # 15 °C·d/day above 5 °C -> a cut every 40 days
    r = simulate("alfalfa", w, dt.date(2020, 3, 15), strategy="full")
    assert 8.5 <= r.cuts <= 9.5  # 15 °C·d/day × 365 / 600


def test_warming_shortens_season():
    w = make_weather(tmax=26, tmin=12)
    base = simulate("maize", w, dt.date(2020, 5, 1), strategy="full", gdd_req=1500)
    warm = simulate("maize", w.perturbed(3.0), dt.date(2020, 5, 1), strategy="full", gdd_req=1500)
    assert (warm.end - warm.start).days < (base.end - base.start).days


def test_spi_median_near_zero_and_drought_levels():
    rng = np.random.default_rng(1)
    days = 40 * 365
    dates = [dt.date(1984, 1, 1) + dt.timedelta(days=i) for i in range(days)]
    p = rng.gamma(0.5, 4.0, days) * (rng.random(days) < 0.4)
    spi = drought.spi_at(p, dates, dates[-1], 90)
    assert spi is not None and -3 < spi < 3
    dry = p.copy()
    dry[-90:] = 0
    spi_dry = drought.spi_at(dry, dates, dates[-1], 90)
    assert spi_dry is not None and spi_dry < -2
    assert drought.level_from_spi(-1.4) == 3
    assert drought.level_from_spi(0.2) == 0
    lvl, parts = drought.combined_level(-1.4, -1.7, -1.5, 8, 25)
    assert lvl >= 3 and len(parts) == 5


def _hourly(days, t, rh):
    out = {"time": [], "temperature_2m": [], "relative_humidity_2m": []}
    for d in range(days):
        for h in range(24):
            out["time"].append(f"2026-06-{d + 1:02d}T{h:02d}:00")
            out["temperature_2m"].append(t[h] if isinstance(t, list) else t)
            out["relative_humidity_2m"].append(rh[h] if isinstance(rh, list) else rh)
    return out


def test_hutton_late_blight():
    rh = [95] * 8 + [70] * 16  # 8 h ≥ 90 %
    hourly = _hourly(3, 14.0, rh)
    s = disease.daily_scores(disease.hourly_by_day(hourly))["late_blight"]
    assert s[dt.date(2026, 6, 2)] == 1.0  # two consecutive Hutton days
    dry = disease.daily_scores(disease.hourly_by_day(_hourly(3, 14.0, 60)))["late_blight"]
    assert max(dry.values()) == 0.0
    assert disease.risk_label(1.0) == "severe"


def test_pest_degree_days():
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(200)]
    tmax = np.full(200, 25.0)
    tmin = np.full(200, 9.0)  # mean 17 -> 8 °C·d/day above 9 °C
    st = pests.status("alfalfa_weevil", dates, tmax, tmin, dt.date(2026, 1, 15), 39.0)
    assert st["dd_today"] == 120  # 15 days * 8
    assert st["next_event"]["dd"] == 156
    assert st["days_until_next"] == 5


def test_climate_trend_detects_warming():
    years = list(range(1985, 2025))
    vals = [20 + 0.05 * (y - 1985) for y in years]
    slope, p = climate.trend(years, vals)
    assert slope == pytest.approx(0.5, abs=1e-6) and p < 0.01


def test_mediterranean_detection_requires_mild_winter():
    from fieldshift.science.rotation import is_mediterranean

    med = [
        {"month": m, "precip": 70 if m in (1, 2, 3, 10, 11, 12) else 10, "tmin": 5 if m in (1, 2, 12) else 12}
        for m in range(1, 13)
    ]
    basin = [{**n, "tmin": -8 if n["month"] in (1, 2, 12) else 5} for n in med]
    assert is_mediterranean(med, 37.9)
    assert not is_mediterranean(basin, 39.5)


def test_winter_hardy_wheat_survives_cold_winter():
    w = make_weather(days=800, tmax=-5, tmin=-25, start=dt.date(2020, 1, 1))
    # warm spring/summer from day 150 onwards
    w.tmax[150:] = 25
    w.tmin[150:] = 10
    r = simulate("winter_wheat", w, dt.date(2020, 1, 2), strategy="full", gdd_req=2000)
    assert r.frost_events == 0


def test_satellite_kc_fusion_scales_water_use():
    w = make_weather(rain=0.0)
    base = simulate("maize", w, dt.date(2020, 5, 1), strategy="full", gdd_req=1500)
    thin = simulate("maize", w, dt.date(2020, 5, 1), strategy="full", gdd_req=1500, kc_scale=0.5, kc_scale_from=dt.date(2020, 6, 15))
    assert thin.etm_mm < base.etm_mm and thin.irrigation_mm < base.irrigation_mm
