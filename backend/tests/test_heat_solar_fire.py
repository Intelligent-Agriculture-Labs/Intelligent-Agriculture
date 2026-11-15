"""Heat stress (WBGT/THI), solar irrigation pump sizing and NASA FIRMS fire / residue-burning advice."""

import datetime as dt
import math
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from fieldshift.data import firms, sources
from fieldshift.engine import fire_cards as fc
from fieldshift.engine import heat_cards
from fieldshift.engine.service import _why
from fieldshift.main import app
from fieldshift.science import heatstress as hs
from fieldshift.science import solarpump as sp

client = TestClient(app)

# --------------------------------------------------------------------------- WBGT physics
# Reference WBGT (°C) from ECMWF thermofeel 2.3.0 `liljegren.wbgt` — an independent implementation of
# Liljegren et al. (2008) — for (T °C, RH %, 2 m wind m/s, GHI W/m², cos zenith, pressure hPa).
THERMOFEEL_REF = [
    ((35, 40, 2.0, 900, 0.9, 1013.25), 31.66),
    ((30, 70, 1.0, 800, 0.8, 1013.25), 32.45),
    ((25, 50, 2.0, 0, 0.0, 1013.25), 19.71),
    ((40, 20, 3.0, 950, 0.95, 950.0), 30.94),
    ((28, 85, 0.5, 300, 0.4, 1000.0), 30.47),
    ((45, 10, 4.0, 1000, 0.97, 980.0), 31.30),
]


@pytest.mark.parametrize("args,ref", THERMOFEEL_REF)
def test_wbgt_matches_independent_liljegren_implementation(args, ref):
    t, rh, u, g, cz, p = args
    assert hs.wbgt_liljegren(t, rh, u, g, cz, p).wbgt == pytest.approx(ref, abs=0.05)


def _psychrometer_tw(t, rh, p=1013.25):
    """Thermodynamic wet bulb from the ventilated (Assmann) psychrometer equation, γ = 6.62e-4 K⁻¹."""
    from scipy.optimize import brentq

    def es(x):
        return 6.112 * math.exp(17.62 * x / (243.12 + x))

    e = rh / 100 * es(t)
    return brentq(lambda x: es(x) - 6.62e-4 * p * (t - x) - e, -40, t)


def test_psychrometric_wet_bulb_reference_cases():
    # Stull (2011) gives Tw = 13.7 °C at 20 °C / 50 %
    assert hs.wet_bulb_stull(20, 50) == pytest.approx(13.7, abs=0.05)
    for t in (10, 20, 30, 40):
        for rh in (20, 50, 80):
            ours = hs.wet_bulb_temperature(t, rh, 1013.25, 1.0, 0, 0, 0, natural=False)
            ref = _psychrometer_tw(t, rh)
            # Liljegren's mass-transfer form sits 0.1–0.7 °C below the Assmann equation (largest hot & dry)
            assert -0.75 <= ours - ref <= 0.05, (t, rh, ours, ref)
            assert ours == pytest.approx(hs.wet_bulb_stull(t, rh), abs=1.2)


def test_wbgt_limit_cases():
    # saturated, no sun, windy: wet bulb = globe = air -> WBGT = air temperature
    w = hs.wbgt_liljegren(30, 100, 5.0, 0, 0)
    assert w.wbgt == pytest.approx(30, abs=0.6)
    # sun raises the globe well above air temperature and WBGT rises with radiation and humidity
    assert hs.wbgt_liljegren(35, 40, 2, 900, 0.9).tg > 45
    assert hs.wbgt_liljegren(35, 40, 2, 900, 0.9).wbgt > hs.wbgt_liljegren(35, 40, 2, 0, 0).wbgt + 2
    assert hs.wbgt_liljegren(35, 70, 2, 600, 0.7).wbgt > hs.wbgt_liljegren(35, 30, 2, 600, 0.7).wbgt
    # more wind cools the globe
    assert hs.wbgt_liljegren(35, 40, 5, 900, 0.9).tg < hs.wbgt_liljegren(35, 40, 0.5, 900, 0.9).tg


def test_niosh_limits_and_work_rest():
    # NIOSH 2016 REL = 56.7 - 11.5 log10(M); ISO 7243 reference values ≈ 33 (rest), 28 (moderate), 26 (high)
    assert hs.rel_wbgt(115) == pytest.approx(33.0, abs=0.1)
    assert hs.rel_wbgt(300) == pytest.approx(28.2, abs=0.1)
    assert hs.rel_wbgt(415) == pytest.approx(26.6, abs=0.1)
    assert hs.rel_wbgt(300, acclimatized=False) == pytest.approx(25.0, abs=0.1)
    assert hs.max_work_fraction(25.0) == 1.0 and hs.max_work_fraction(34.0) == 0.0
    f = hs.max_work_fraction(30.0)
    m = f * 300 + (1 - f) * 115
    assert 0 < f < 1 and hs.rel_wbgt(m) == pytest.approx(30.0, abs=0.01)
    fracs = [hs.max_work_fraction(x) for x in np.arange(27, 34, 0.25)]
    assert all(a >= b for a, b in zip(fracs, fracs[1:], strict=False))
    assert [hs.worker_level(x) for x in (26, 28.5, 30, 32.5)] == ["low", "moderate", "high", "severe"]


def test_livestock_thi():
    # NRC/Mader: 0.8*30 + 0.6*(30-14.4) + 46.4 = 79.76
    assert hs.thi_nrc(30, 60) == pytest.approx(79.76, abs=0.01)
    assert hs.livestock_class("dairy_cattle", 30, 60)[1] == "danger"  # 9.76 above 70
    assert hs.livestock_class("poultry_broilers", 30, 60)[1] == "alert"
    assert hs.livestock_class("beef_cattle", 20, 50)[1] == "none"
    assert hs.livestock_class("dairy_cattle", 38, 50)[1] == "emergency"
    # Marai et al. 2007: 30 - (0.31 - 0.155)*15.6 = 27.58 -> extreme
    v, cls = hs.livestock_class("sheep_goats", 30, 50)
    assert v == pytest.approx(27.582, abs=0.01) and cls == "emergency"
    assert hs.livestock_class("sheep_goats", 20, 50)[1] == "none"


def test_solar_geometry():
    eq = dt.date(2024, 3, 20)
    assert hs.cos_zenith(0, 0, eq, 12.0) == pytest.approx(1.0, abs=0.01)
    assert hs.cos_zenith(0, 0, eq, 6.0) == pytest.approx(0.0, abs=0.03)
    assert hs.cos_zenith(60, 0, dt.date(2024, 12, 21), 12.0) == pytest.approx(
        math.cos(math.radians(83.4)), abs=0.01
    )
    assert hs.pressure_hpa(0) == pytest.approx(1013, abs=0.5) and hs.pressure_hpa(1500) < 860


def _hot_ctx(today, t_day=41.0, rh_day=35.0, t_night=27.0):
    """Fake context: hot dry afternoons, POWER climatology with strong sun and light wind."""
    times, temp, rh = [], [], []
    for k in range(10):
        d = today + dt.timedelta(days=k)
        for h in range(24):
            times.append(f"{d.isoformat()}T{h:02d}:00")
            x = max(0.0, math.sin(math.pi * (h - 6) / 14)) if 6 <= h <= 20 else 0.0
            temp.append(t_night + (t_day - t_night) * x)
            rh.append(70 - (70 - rh_day) * x)
    start = today - dt.timedelta(days=4000)
    n = 4100
    power = sources.Daily(
        [start + dt.timedelta(days=i) for i in range(n)],
        {"WS2M": np.full(n, 1.5), "ALLSKY_SFC_SW_DWN": np.full(n, 26.0)},
    )
    return SimpleNamespace(
        lat=28.0,
        lon=77.0,
        today=today,
        hourly={"time": times, "temperature_2m": temp, "relative_humidity_2m": rh},
        power=power,
        elevation_m=220.0,
        statuses={},
    )


def test_heat_stress_card_from_context_fallback():
    today = dt.date(2026, 6, 1)
    series = []
    cards = heat_cards.heat_stress_cards(_hot_ctx(today), today, "en", series, _why)
    assert len(cards) == 1
    c = cards[0]
    assert c["id"] == "heat_stress" and c["risk"] in ("high", "severe")
    assert "heat stress" in c["title"] and "animals" in c["title"]
    assert any("Liljegren" in s for s in c["why"]["steps"]) and any("NIOSH" in s for s in c["why"]["steps"])
    assert any("climatological" in cv for cv in c["why"]["caveats"])
    assert {"wbgt_max", "thi_cattle"} <= {s["id"] for s in series}
    # all 6 languages give a title
    for lang in ("es", "fr", "sw", "hi", "de"):
        assert heat_cards.heat_stress_cards(_hot_ctx(today), today, lang, [], _why)[0]["title"] != c["title"]


def test_no_heat_card_in_mild_weather():
    today = dt.date(2026, 4, 1)
    ctx = _hot_ctx(today, t_day=22.0, rh_day=50.0, t_night=10.0)
    assert heat_cards.heat_stress_cards(ctx, today, "en", [], _why) == []


# --------------------------------------------------------------------------- solar pump physics
def test_solar_pump_physics():
    assert sp.hydraulic_kwh(1000, 10) == pytest.approx(27.25, abs=0.01)  # ρgHV/3.6e6
    assert sp.effective_rain_mm(100) == pytest.approx(84.0)
    assert sp.effective_rain_mm(300) == pytest.approx(155.0)
    assert sp.effective_rain_mm(0) == 0
    assert sp.pv_kwp(10, 5, 0.5, 0.8) == pytest.approx(5.0)
    assert sp.crf(0.08, 20) == pytest.approx(0.10185, abs=1e-4)
    assert sp.pv_temperature_factor(25, g_wm2=0) == pytest.approx(1.0)
    assert sp.pv_temperature_factor(35) == pytest.approx(1 - 0.004 * (35 + 24 - 25))


def test_size_system_hand_calculation():
    # one month (July, 31 d): ET0 6 mm/d, Kc 1.0, no rain, 5 kWh/m²/d, Tmax 25 °C (PR = 0.904*0.88)
    d = sp.size_system([(7, 6.0, 1.0, 0.0, 5.0, 25.0)], area_ha=1.0, head_m=20.0, efficiency=0.9, eta_mp=0.5)
    vol = 6.0 / 0.9 * 10  # 66.7 m³/day
    assert d.months[0].volume_m3_day == pytest.approx(vol, rel=1e-6)
    eh = 0.0027250 * 20 * vol
    pr = (1 - 0.004 * (25 + 24 - 25)) * 0.88
    assert d.kwp == pytest.approx(eh / (5.0 * 0.5 * pr), rel=1e-3)
    assert d.annual_m3 == pytest.approx(vol * 31, rel=1e-6)
    assert d.diesel_l_m3 == pytest.approx(0.0027250 * 20 / (0.15 * 9.96), rel=1e-3)
    assert d.co2_t_year == pytest.approx(d.diesel_l_m3 * d.annual_m3 * 2.68 / 1000, rel=1e-6)
    assert d.hyd_kwh_m3 == pytest.approx(0.0545, abs=1e-4)
    # sizing month = the month that needs the biggest array: same need, cloudier month wins
    d2 = sp.size_system([(6, 6.0, 1.0, 0, 6.0, 25), (7, 6.0, 1.0, 0, 4.0, 25)], 1.0, 20.0, 0.9)
    assert d2.design_month == 7
    # doubling the head doubles the energy and the array
    d3 = sp.size_system([(7, 6.0, 1.0, 0.0, 5.0, 25.0)], area_ha=1.0, head_m=40.0, efficiency=0.9, eta_mp=0.5)
    assert d3.kwp == pytest.approx(2 * d.kwp, rel=1e-6)


def test_solar_pump_endpoint_and_card():
    req = {"lat": 39.47, "lon": -118.78, "crop": "maize", "planting_date": "2024-05-01", "irrigation": "drip"}
    r = client.post("/api/solar-pump", json={**req, "area_ha": 2.0, "static_head_m": 20}).json()
    assert r["pv_kwp"] > 0 and r["head_m"] == pytest.approx((20 + 10) * 1.1)
    assert r["area_ha"] == 2.0 and 1 <= r["design_month"] <= 12 and r["monthly"]
    assert r["solar_usd_per_m3"] > 0 and r["diesel_usd_per_m3"] > 0 and r["co2_avoided_t_per_season"] > 0
    assert r["hydraulic_kwh_per_m3"] == pytest.approx(0.002725 * r["head_m"], rel=1e-3)
    assert r["sources"] and r["steps"]
    r2 = client.post("/api/solar-pump", json={**req, "area_ha": 4.0, "static_head_m": 20}).json()
    assert r2["pv_kwp"] == pytest.approx(2 * r["pv_kwp"], rel=0.01)
    assert client.post("/api/solar-pump", json={**req, "crop": "nope"}).status_code == 422
    a = client.post(
        "/api/advice", json={**req, "planting_date": (dt.date.today() - dt.timedelta(days=40)).isoformat()}
    ).json()
    card = next(c for c in a["cards"] if c["id"] == "solar_pump")
    assert card["risk"] == "low" and card["amount"]["unit"] == "kWp" and card["why"]["sources"]
    rainfed = client.post("/api/advice", json={**req, "irrigation": "none"}).json()
    assert not any(c["id"] == "solar_pump" for c in rainfed["cards"])


# --------------------------------------------------------------------------- FIRMS / residue burning
VIIRS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
30.95,75.90,334.5,0.5,0.6,2026-11-12,0812,N20,nominal,2.0NRT,298.3,4.9,D
30.91,75.86,340.1,0.5,0.6,2026-11-12,0812,N20,low,2.0NRT,298.3,1.1,D
"""
MODIS_CSV = """latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,confidence,version,bright_t31,frp,daynight
31.20,76.20,320.1,1.2,1.1,2026-11-11,515,T,85,6.1NRT,295.9,12.3,D
"""


def test_firms_parsing_and_geometry():
    f = firms.parse_csv(VIIRS_CSV) + firms.parse_csv(MODIS_CSV)
    assert [x.confidence for x in f] == ["nominal", "low", "high"]
    assert f[2].time_utc == "0515" and f[2].frp_mw == 12.3
    assert firms.haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.1)
    assert firms.compass(firms.bearing_deg(30, 75, 31, 75)) == "N"
    assert firms.compass(firms.bearing_deg(30, 75, 30, 74)) == "W"


def test_firms_api_key_never_in_cache_tag(monkeypatch):
    seen = []

    def fake_get(url, tag, ttl_s, timeout_s=30.0):
        seen.append((url, tag))
        return VIIRS_CSV, "live"

    monkeypatch.setattr(firms, "_get_csv", fake_get)
    monkeypatch.setenv("FIELDSHIFT_FIRMS", "auto")
    monkeypatch.setenv("FIELDSHIFT_FIRMS_MAP_KEY", "SECRETKEY123")
    res = firms.nearby_fires(30.90, 75.85, dt.date(2026, 11, 12), 50)
    assert res.mode == "api" and res.status == "live"
    assert all("SECRETKEY123" in u and "SECRETKEY123" not in t for u, t in seen)
    assert all(f.confidence != "low" for f in res.fires) and res.fires[0].km < 10


def test_firms_demo_and_off(monkeypatch):
    monkeypatch.setenv("FIELDSHIFT_FIRMS", "demo")
    res = firms.nearby_fires(30.90, 75.85, dt.date(2026, 11, 9), 50)
    assert res.status == "demo" and len(res.fires) > 5
    assert all(r.km <= 50 for r in res.fires) and res.fires == sorted(res.fires, key=lambda f: f.km)
    # outside the recorded box or dates -> unavailable, never an error
    assert firms.nearby_fires(-1.57, 37.2, dt.date(2026, 11, 9)).status == "unavailable"
    assert firms.nearby_fires(30.9, 75.85, dt.date(2025, 6, 1)).status == "unavailable"
    monkeypatch.setenv("FIELDSHIFT_FIRMS", "off")
    assert firms.nearby_fires(30.9, 75.85, dt.date(2026, 11, 9)).status == "off"


def test_fire_and_residue_cards_punjab(monkeypatch):
    monkeypatch.setenv("FIELDSHIFT_FIRMS", "demo")
    statuses = {}
    cards = fc.fire_cards(30.90, 75.85, "rice", dt.date(2026, 11, 9), "en", _why, None, statuses)
    ids = {c["id"]: c for c in cards}
    assert statuses["firms"] == "demo"
    assert "fire_nearby" in ids and "active fires" in ids["fire_nearby"]["title"]
    res = ids["residue_no_burn"]
    assert res["title"].startswith("Don't burn the rice residue")
    assert res["amount"]["unit"] == "kg N/ha" and res["amount"]["value"] > 20
    assert any("Happy Seeder" in s for s in res["why"]["steps"])
    for lang in ("es", "fr", "sw", "hi", "de"):
        t = fc.fire_cards(30.90, 75.85, "rice", dt.date(2026, 11, 9), lang, _why, None, {})
        assert {c["id"] for c in t} == set(ids)


def test_residue_card_only_in_burning_regions_and_seasons(monkeypatch):
    monkeypatch.setenv("FIELDSHIFT_FIRMS", "off")
    assert (
        fc.fire_cards(42.0, -93.7, "maize", dt.date(2026, 10, 15), "en", _why) == []
    )  # Iowa: not a burning region
    assert fc.fire_cards(30.9, 75.85, "rice", dt.date(2026, 7, 1), "en", _why) == []  # Punjab rice, monsoon
    assert fc.fire_cards(30.9, 75.85, "potato", dt.date(2026, 11, 1), "en", _why) == []
    b = fc.residue_benefits("rice", 6.5)
    assert b["residue_t_ha"] == pytest.approx(7.8)
    assert b["n_lost_kg_ha"] == pytest.approx(7.8 * 6.5 * 0.9)
    assert b["co2_t_ha"] == pytest.approx(7.8 * 0.40 * 0.9 * 44 / 12)


def test_advice_registers_new_cards_and_firms_source(monkeypatch):
    rec = firms.nearby_fires

    def fixed(lat, lon, today, radius_km=50.0, days=2):
        return rec(lat, lon, dt.date(2026, 11, 9), radius_km, days)

    monkeypatch.setattr(firms, "nearby_fires", fixed)
    a = client.post(
        "/api/advice",
        json={
            "lat": 30.90,
            "lon": 75.85,
            "crop": "rice",
            "planting_date": "2026-06-20",
            "irrigation": "flood",
        },
    ).json()
    ids = {c["id"] for c in a["cards"]}
    assert {"fire_nearby", "solar_pump"} <= ids
    assert any(s["id"] == "firms" and s["is_nasa"] for s in a["sources"])
    assert [c["priority"] for c in a["cards"]] == list(range(1, len(a["cards"]) + 1))
