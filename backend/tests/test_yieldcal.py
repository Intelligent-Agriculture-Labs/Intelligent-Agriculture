"""Global yield calibration (ADR-021, VALIDATION V9): factors, regions, climate zones, model wiring."""

import datetime as dt
import math

import numpy as np
import pytest

from fieldshift.science import yieldcal
from fieldshift.science.cropmodel import Weather, crops, simulate


def seasonal_weather(
    t_mean: float, t_amp: float, rain_mm_yr: float, summer_share: float = 0.5, years: int = 4
):
    """Synthetic northern-hemisphere record: sinusoidal temperature, rain split summer/winter half-year."""
    start = dt.date(2001, 1, 1)
    dates = [start + dt.timedelta(days=i) for i in range(365 * years)]
    doy = np.array([d.timetuple().tm_yday for d in dates])
    t = t_mean - t_amp * np.cos(2 * np.pi * (doy - 15) / 365)
    summer = np.array([4 <= d.month <= 9 for d in dates])
    rain = np.where(summer, rain_mm_yr * summer_share / 183, rain_mm_yr * (1 - summer_share) / 182)
    return Weather(dates, t + 5, t - 5, rain, np.full(len(dates), 4.0))


@pytest.mark.parametrize(
    "t_mean,t_amp,rain,summer_share,zone",
    [
        (26, 1, 1800, 0.5, "tropical"),  # humid tropics: coldest month ≥ 18 °C
        (24, 8, 150, 0.5, "arid"),  # hot desert
        (12, 8, 900, 0.5, "temperate"),  # western Europe-like
        (8, 16, 700, 0.7, "continental"),  # cold winters (coldest month ≤ −3 °C), summer rain
        (17, 8, 300, 0.2, "arid"),  # winter-rain steppe below the Köppen threshold (P < 10·2·MAT = 340 mm)
        (17, 8, 650, 0.2, "temperate"),  # Mediterranean above the threshold
    ],
)
def test_climate_zone_koppen_main_groups(t_mean, t_amp, rain, summer_share, zone):
    w = seasonal_weather(t_mean, t_amp, rain, summer_share)
    assert yieldcal.climate_zone(w.dates, w.tmax, w.tmin, w.rain) == zone
    assert w.climate_zone() == zone


@pytest.mark.parametrize(
    "lat,lon,region",
    [
        (42.03, -93.62, "northern_america"),  # Ames IA
        (39.472, -118.777, "northern_america"),  # Fallon NV
        (-1.517, 37.263, "sub_saharan_africa"),  # Machakos KE
        (37.885, -4.779, "southern_europe"),  # Córdoba ES
        (48.85, 2.35, "western_europe"),
        (28.6, 77.2, "south_asia"),
        (-31.6, -60.7, "latin_america"),
        (-33.9, 147.0, "oceania"),
    ],
)
def test_region_lookup(lat, lon, region):
    assert yieldcal.region_of(lat, lon) == region


@pytest.mark.parametrize(
    "lat,lon,region",
    [
        (25.7, -100.3, "latin_america"),  # Monterrey, just south of the U.S. border
        (39.9, 32.9, "middle_east_north_africa"),  # Ankara
        (55.75, 37.6, "eastern_europe_central_asia"),  # Moscow
        (30.0, 31.2, "middle_east_north_africa"),  # Cairo
        (13.5, 2.1, "sub_saharan_africa"),  # Niamey
    ],
)
def test_region_lookup_near_borders(lat, lon, region):
    assert yieldcal.region_of(lat, lon) == region


def test_region_lookup_invalid_is_none():
    assert yieldcal.region_of(float("nan"), 10.0) is None


def test_calibration_file_is_complete_and_bounded():
    cal = yieldcal.calibration()
    lo, hi = cal["bounds"]
    assert 0 < lo < 1 < hi
    assert cal["sources"] and cal["method"]
    known_regions = set(yieldcal._grid()[1])  # type: ignore[index]
    assert cal["crops"], "no calibrated crops"
    for cid, e in cal["crops"].items():
        assert cid in crops(), cid
        assert lo <= e["factor"] <= hi
        assert e["n_countries"] >= 1
    for rg, e in cal["regions"].items():
        assert rg in known_regions, rg
        assert lo <= e["factor"] <= hi
    for z, e in cal["zones"].items():
        assert z in yieldcal.ZONES
        assert lo <= e["factor"] <= hi
    # few factors (no per-country overfitting): a factor + gap sensitivity per crop, one per region/zone
    assert len(cal["crops"]) + len(cal["regions"]) + len(cal["zones"]) <= 40
    for e in cal["crops"].values():
        assert 0.0 < e.get("gap_sensitivity", 1.0) < 3.0
    # reference regions (where crops.yaml typical yields come from) carry no yield-gap term
    for rg in cal.get("reference_regions", []):
        assert cal["regions"][rg]["factor"] == 1.0


def test_demo_sites_stay_plausible():
    """Calibrated multipliers at the demo farms: high-input systems near 1, Kenyan smallholder maize low."""
    ames = yieldcal.factor("maize", yieldcal.region_of(42.03, -93.62), None)
    machakos = yieldcal.factor("maize", yieldcal.region_of(-1.517, 37.263), None)
    cordoba = yieldcal.factor("winter_wheat", yieldcal.region_of(37.885, -4.779), None)
    fallon = yieldcal.factor("alfalfa", yieldcal.region_of(39.472, -118.777), None)
    assert 0.8 <= ames <= 1.2
    assert 0.8 <= cordoba <= 1.2
    assert 0.1 <= machakos <= 0.5  # FAOSTAT Kenya maize 2000–2024: ~1.6 t/ha
    assert fallon == 1.0  # alfalfa: no FAOSTAT yields, uncalibrated


def test_factor_rules():
    cal = yieldcal.calibration()
    cid = next(iter(cal["crops"]))
    rg = next(iter(cal["regions"])) if cal["regions"] else "western_europe"
    assert yieldcal.factor(cid, None, None) == 1.0  # unknown location: uncalibrated
    # not benchmarked: annual crops get the regional gap only, perennials/covers nothing
    assert yieldcal.factor("tomato", rg, None) == pytest.approx(cal["regions"][rg]["factor"])
    assert yieldcal.factor("alfalfa", rg, None) == 1.0
    assert yieldcal.factor("cover_rye_vetch", rg, None) == 1.0
    e = cal["crops"][cid]
    expect = e["factor"] * cal["regions"].get(rg, {}).get("factor", 1.0) ** e.get("gap_sensitivity", 1.0)
    lo, hi = cal["bounds"]
    assert yieldcal.factor(cid, rg, None) == pytest.approx(min(hi, max(lo, expect)))


def test_simulate_applies_factor_and_scenarios_keep_it():
    base = seasonal_weather(14, 10, 700, 0.6, years=3)
    located = Weather(base.dates, base.tmax, base.tmin, base.rain, base.et0, region="sub_saharan_africa")
    f = located.yield_factor("maize")
    zone = located.climate_zone() if yieldcal.calibration()["zones"] else None
    assert f == pytest.approx(yieldcal.factor("maize", "sub_saharan_africa", zone))
    assert f != 1.0  # maize is calibrated
    p = dt.date(2001, 5, 1)
    r0 = simulate("maize", base, p, strategy="full", gdd_req=1500)
    r1 = simulate("maize", located, p, strategy="full", gdd_req=1500)
    assert r1.yield_t_ha == pytest.approx(r0.yield_t_ha * f, abs=0.011)
    assert r1.et_mm == r0.et_mm  # water use is not calibrated, only the yield level
    warm = located.perturbed(delta_t=2.0)
    assert warm.region == "sub_saharan_africa"
    assert warm.yield_factor("maize") == pytest.approx(f)
    assert not math.isnan(f)
