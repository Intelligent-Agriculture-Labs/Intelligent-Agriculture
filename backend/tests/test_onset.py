"""Rainy-season onset / cessation / false starts on SYNTHETIC rain series with known answers."""

from __future__ import annotations

import dataclasses
import datetime as dt

import numpy as np
import pytest
from fastapi.testclient import TestClient

from fieldshift.data import sources
from fieldshift.engine import context
from fieldshift.engine.messages import t
from fieldshift.main import app
from fieldshift.science import onset as on

CRIT = on.Criteria()


def _series(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


def _season_rain(
    dates: list[dt.date],
    seasons: list[tuple[tuple[int, int], tuple[int, int]]],
    mm: float = 15.0,
    false_start_years: set[int] | None = None,
    false_md: tuple[int, int] = (5, 20),
) -> np.ndarray:
    """``mm`` every second day inside each (start month/day, end month/day) season; seasons may cross New Year.
    In ``false_start_years`` a single 25 mm storm falls on ``false_md``, followed by dry weather."""
    rain = np.zeros(len(dates))
    for i, d in enumerate(dates):
        for (m0, d0), (m1, d1) in seasons:
            s = dt.date(d.year, m0, d0)
            e = dt.date(d.year, m1, d1)
            inside = (s <= d <= e) if s <= e else (d >= s or d <= e)
            if inside:
                ref = s if d >= s else dt.date(d.year - 1, m0, d0)
                if (d - ref).days % 2 == 0:
                    rain[i] = mm
        if false_start_years and d.year in false_start_years and (d.month, d.day) == false_md:
            rain[i] = 25.0
    return rain


START, END = dt.date(1984, 1, 1), dt.date(2025, 12, 31)
DATES = _series(START, END)
ET0 = np.full(len(DATES), 5.0)


# --------------------------------------------------------------------------- building blocks
def test_forward_sum_and_trigger():
    x = np.array([0, 10, 0, 10, 0, 0], float)
    acc = on.forward_sum(x, 3)
    assert acc[:4].tolist() == [10, 20, 10, 10]
    assert np.isnan(acc[4]) and np.isnan(acc[5])
    assert on.is_trigger(x, acc, 1, CRIT)  # 10 + 0 + 10 = 20 mm, starts wet
    assert not on.is_trigger(x, acc, 0, CRIT)  # starts dry


def test_dry_spell_failure_counts_days_after_onset():
    r = np.zeros(40)
    r[0] = 25
    assert on.dry_spell_failure(r, 0, CRIT) == 8  # 8th dry day makes the spell longer than 7 days
    r[1:40:5] = 5  # rain every 5 days: never more than 4 dry days
    assert on.dry_spell_failure(r, 0, CRIT) is None
    r2 = np.zeros(40)
    r2[0] = 25
    assert on.dry_spell_failure(r2, 0, CRIT, last=5) is None  # not enough known days to tell yet


def test_cessation_water_balance_empties_store():
    r = np.zeros(60)
    r[0] = 100  # store full on day 0 (100 - 5 = 95 mm left)
    k, censored = on.cessation_index(r, np.full(60, 5.0), 0, 5, 59, CRIT)
    assert not censored and k == 19  # 95 mm / 5 mm per day -> empty on day 19
    k, censored = on.cessation_index(r, np.full(60, 1.0), 0, 5, 59, CRIT)
    assert censored and k == 59


# --------------------------------------------------------------------------- climatology
def test_unimodal_northern_season_onset_and_cessation():
    rain = _season_rain(DATES, [((6, 15), (9, 30))])
    site = on.site_climatology(DATES, rain, ET0, lat=12.0)
    assert site.applicable, site.reason
    assert site.info["regime"] == "unimodal" and len(site.seasons) == 1
    sc = site.seasons[0]
    assert sc.season.label in ("JJAS", "JJA", "JAS", "JJASO")
    onsets = [y.onset for y in sc.years if y.onset]
    assert len(onsets) >= 40
    assert all((o.month, o.day) == (6, 15) for o in onsets)
    # 15 mm every 2nd day vs 5 mm/day ET0: the store fills to 100 mm and empties ~20 days after the last rain
    ces = [y.cessation for y in sc.years if y.cessation]
    assert all(dt.date(c.year, 10, 15) <= c <= dt.date(c.year, 10, 25) for c in ces)
    assert sc.false_start_pct() == 0.0
    assert sc.failed_pct() == 0.0
    s = sc.summary(2025, 2005)
    assert s["onset"]["p50"] == "15 Jun"
    assert s["trend"]["onset_days_per_decade"] == 0.0


def test_southern_hemisphere_season_across_new_year():
    rain = _season_rain(DATES, [((11, 15), (3, 15))])
    site = on.site_climatology(DATES, rain, ET0, lat=-15.0)
    assert site.applicable and len(site.seasons) == 1
    sc = site.seasons[0]
    on_ = [y for y in sc.years if y.onset]
    assert all((y.onset.month, y.onset.day) == (11, 15) and y.onset.year == y.year for y in on_)
    assert all(y.cessation and y.cessation.year == y.year + 1 and y.cessation.month == 4 for y in on_)
    assert all(y.length and 140 <= y.length <= 160 for y in on_)


def test_bimodal_two_seasons_detected():
    rain = _season_rain(DATES, [((3, 15), (5, 20)), ((10, 15), (12, 20))])
    site = on.site_climatology(DATES, rain, ET0, lat=-1.5)
    assert site.info["regime"] == "bimodal"
    assert site.info["harmonic_ratio"] > 1.0
    labels = [s.season.label for s in site.seasons]
    assert labels[0].startswith("M") and labels[1].startswith("O"), labels
    for sc, md in zip(site.seasons, [(3, 15), (10, 15)], strict=True):
        assert all((y.onset.month, y.onset.day) == md for y in sc.years if y.onset)


def test_false_starts_counted_and_real_onset_after_dry_spell():
    fs_years = set(range(1984, 2026, 2))
    rain = _season_rain(DATES, [((6, 15), (9, 30))], false_start_years=fs_years, false_md=(5, 20))
    site = on.site_climatology(DATES, rain, ET0, lat=12.0)
    sc = site.seasons[0]
    for y in sc.years:
        assert y.onset == dt.date(y.year, 6, 15)  # the real onset, never the isolated May storm
        if y.year in fs_years:
            assert y.first_false and y.first_apparent == dt.date(y.year, 5, 20) and y.false_starts == 1
        else:
            assert not y.first_false
    assert 40 <= (sc.false_start_pct() or 0) <= 60


def test_failed_season_and_not_applicable_cases():
    rain = _season_rain(DATES, [((6, 15), (9, 30))], mm=6.0)  # 6 mm every 2nd day never gives 20 mm in 3 days
    site = on.site_climatology(DATES, rain, ET0, lat=12.0)
    assert site.seasons and site.seasons[0].failed_pct() == 100.0
    # same rain, but mid-latitude -> no advice
    assert not on.site_climatology(DATES, rain, ET0, lat=45.0).applicable
    # rain all year round -> no dry season -> no advice
    wet = np.where(np.arange(len(DATES)) % 2 == 0, 12.0, 0.0) + _season_rain(DATES, [((6, 1), (8, 31))])
    s2 = on.site_climatology(DATES, wet, np.full(len(DATES), 3.0), lat=5.0)
    assert not s2.applicable and "dry season" in s2.reason


def test_trend_detects_later_onsets():
    rain = np.zeros(len(DATES))
    for i, d in enumerate(DATES):
        s = dt.date(d.year, 6, 1) + dt.timedelta(days=(d.year - 1984) // 2)  # one day later every 2 years
        if s <= d <= dt.date(d.year, 9, 30) and (d - s).days % 2 == 0:
            rain[i] = 15.0
    sc = on.site_climatology(DATES, rain, ET0, lat=12.0).seasons[0]
    tr = sc.summary(2025, 2005)["trend"]
    assert 4.0 <= tr["onset_days_per_decade"] <= 6.0 and tr["onset_p"] < 0.01


def test_false_start_probability_is_conditional():
    ev = [on.Event(0, 5)] * 4 + [on.Event(0, 20)] * 2 + [on.Event(0, None)] * 4
    p0, n0 = on.false_start_probability(ev, 0, 0, 20, 1)
    assert n0 == 10 and p0 == pytest.approx(0.6)
    p10, n10 = on.false_start_probability(ev, 0, 10, 20, 1)  # 10 days already passed without a dry spell
    assert n10 == 6 and p10 == pytest.approx(2 / 6)
    p30, _ = on.false_start_probability(ev, 0, 30, 20, 1)
    assert p30 == 0.0


# --------------------------------------------------------------------------- live status
def _status_at(rain: np.ndarray, today: dt.date, horizon: int = 16) -> on.Status:
    i = DATES.index(today)
    hist = on.site_climatology(DATES, rain, ET0, lat=12.0, last=i)
    n = i + 1 + horizon
    st = on.season_status(DATES[:n], rain[:n], ET0[:n], i, hist)
    assert st is not None
    return st


def test_status_phases_through_a_season():
    fs_years = set(range(1984, 2026, 2))
    rain = _season_rain(DATES, [((6, 15), (9, 30))], false_start_years=fs_years, false_md=(5, 20))
    assert _status_at(rain, dt.date(2024, 3, 1)).phase == "before"
    st = _status_at(rain, dt.date(2025, 5, 10))
    assert st.phase == "not_started"
    st = _status_at(rain, dt.date(2024, 6, 5), horizon=0)  # 2024 had the May false start, dry since
    assert st.phase == "false_start" and st.last_false_start == dt.date(2024, 5, 20)
    st = _status_at(rain, dt.date(2025, 6, 5))  # onset on 15 Jun is inside the 16-day forecast
    assert st.phase == "forecast" and st.onset == dt.date(2025, 6, 15)
    st = _status_at(rain, dt.date(2025, 6, 20))
    assert st.phase == "started" and st.onset == dt.date(2025, 6, 15)
    assert st.false_pct is not None and st.false_pct <= 20  # historic real onsets on 15 Jun never failed
    st = _status_at(rain, dt.date(2025, 8, 1))
    assert st.phase == "established"
    st = _status_at(rain, dt.date(2025, 11, 1))  # after the usual end: the card looks at next year's season
    assert st.phase == "before" and st.year == 2026
    early_end = rain.copy()
    early_end[DATES.index(dt.date(2025, 9, 1)) :] = 0.0  # 2025 rains stop a month early
    st = _status_at(early_end, dt.date(2025, 10, 5))
    assert st.phase == "ended" and st.cessation is not None and st.cessation.month == 9


def test_status_started_with_high_false_start_odds():
    # every year: a 25 mm storm on 10 May followed by a month of dry weather, then the real season from 12 Jun
    rain = _season_rain(
        DATES, [((6, 12), (9, 30))], false_start_years=set(range(1984, 2026)), false_md=(5, 10)
    )
    st = _status_at(rain, dt.date(2025, 5, 12), horizon=0)  # no forecast: only 2 days known after the storm
    assert st.phase == "started" and st.onset == dt.date(2025, 5, 10)
    assert st.false_pct is not None and st.false_pct >= 80
    # the real onset of 12 Jun, a few days in, has low odds of a false start
    st = _status_at(rain, dt.date(2025, 6, 16), horizon=0)
    assert st.phase == "started" and st.onset == dt.date(2025, 6, 12)
    assert st.false_pct is not None and st.false_pct <= 20


def test_sowing_windows_fit_and_short_cycle():
    rain = _season_rain(DATES, [((6, 15), (9, 30))])
    sc = on.site_climatology(DATES, rain, ET0, lat=12.0).seasons[0]
    crops = [
        ("short", "Short crop", [15.0, 25.0, 30.0, 15.0]),
        ("long", "Long crop", [30.0, 50.0, 60.0, 30.0]),
    ]
    sw = on.sowing_windows(sc, 2026, dt.date(2026, 6, 15), crops, 0.8)
    short, long_ = sw["crops"]
    assert short["need_days"] == 70 and short["fits"] and short["fit_pct"] == 100
    end = dt.date.fromisoformat(sw["end_of_season"])
    assert dt.date.fromisoformat(short["sow_until"]) == end - dt.timedelta(days=70)
    assert long_["need_days"] == 140 and not long_["fits"] and long_["fit_pct"] == 0
    assert long_["max_variety_days"] < long_["cycle_days"]


# --------------------------------------------------------------------------- API + advice card
def _tropical_power(lat, lon, start, end):
    dates = _series(start, end)
    n = len(dates)
    rain = _season_rain(dates, [((6, 15), (9, 30))], false_start_years=set(range(1984, 2030, 3)))
    # year-to-year variety in amounts (≥ 21 mm per 3 days still) and < 1 mm traces keep the SPI gamma fits finite
    rng = np.random.default_rng(1)
    rain = rain * rng.uniform(0.7, 1.3, n) + rng.uniform(0.0, 0.9, n) * (rng.random(n) < 0.3)
    doy = np.array([d.timetuple().tm_yday for d in dates])
    season = np.cos(2 * np.pi * (doy - 120) / 365)
    v = {
        "T2M_MAX": 33 + 4 * season,
        "T2M_MIN": 21 + 3 * season,
        "T2M": 27 + 3 * season,
        "RH2M": np.full(n, 55.0),
        "T2MDEW": np.full(n, 17.0),
        "WS2M": np.full(n, 2.5),
        "ALLSKY_SFC_SW_DWN": np.full(n, 21.0),
        "PRECTOTCORR": rain,
    }
    return sources.Daily(dates, v, "live", {"power_elevation_m": 300})


@pytest.fixture
def tropical(monkeypatch):
    monkeypatch.setattr(sources, "power_daily", _tropical_power)
    context._ctx_cache.clear()
    yield
    context._ctx_cache.clear()


def test_rain_season_api_and_card(tropical):
    client = TestClient(app)
    r = client.get(
        "/api/rain-season", params={"lat": 12.0, "lon": 2.0, "crop": "sorghum", "as_of": "2024-06-25"}
    )
    assert r.status_code == 200
    a = r.json()
    assert a["applicable"] and a["regime"] == "unimodal"
    s = a["seasons"][0]
    assert s["onset"]["p50"] == "15 Jun" and s["n_years"] >= 30
    assert 25 <= s["false_start_pct"] <= 45  # a storm on 20 May every 3rd year
    assert a["status"]["phase"] in ("started", "established") and a["status"]["onset"] == "2024-06-15"
    assert any(c["crop"] == "sorghum" for c in a["sowing"]["crops"])
    card = a["card"]
    assert card["id"] == "rain_onset" and card["why"]["steps"] and card["why"]["model_doc"] == "rain-onset"
    # the advice for a rain-fed field carries the card, in every language
    field = {"lat": 12.0, "lon": 2.0, "crop": "sorghum", "planting_date": "2024-07-01", "irrigation": "none"}
    for lang in ("en", "es", "fr", "sw", "hi", "de"):
        adv = client.post("/api/advice", json={**field, "lang": lang, "as_of": "2024-06-25"}).json()
        c = next(c for c in adv["cards"] if c["id"] == "rain_onset")
        assert c["title"] and "{" not in c["title"] and "{" not in c["detail"]
    assert any(s["id"] == "rain_season_cum" for s in adv["series"])
    # irrigated fields don't get it
    adv = client.post("/api/advice", json={**field, "irrigation": "drip", "as_of": "2024-06-25"}).json()
    assert not any(c["id"] == "rain_onset" for c in adv["cards"])


def test_planner_respects_onset(tropical):
    client = TestClient(app)
    req = {
        "lat": 12.0,
        "lon": 2.0,
        "crop": "pearl_millet",
        "planting_date": "2025-05-01",
        "irrigation": "none",
    }
    r = client.post("/api/planner", json={**req, "as_of": "2025-01-10"})
    assert r.status_code == 200
    p = r.json()
    lim = p["rain_season"]
    assert lim and lim["onset_median"].endswith("06-15")
    assert all("onset_ok" in s for s in p["sowing_scan"])
    assert p["window"]["start"] >= lim["onset_median"]  # never sow before the rains in half of years
    assert any(s["date"] >= lim["onset_median"] for s in p["sowing_scan"])


def test_mid_latitude_api_not_applicable_and_no_card():
    client = TestClient(app)
    a = client.get("/api/rain-season", params={"lat": 39.47, "lon": -118.78}).json()
    assert a["applicable"] is False and a["reason"]
    adv = client.post(
        "/api/advice",
        json={
            "lat": 39.47,
            "lon": -118.78,
            "crop": "maize",
            "planting_date": "2024-05-01",
            "irrigation": "none",
        },
    ).json()
    assert not any(c["id"] == "rain_onset" for c in adv["cards"])


def test_all_onset_messages_have_six_languages():
    import yaml

    from fieldshift.engine.messages import CONFIG

    msgs = yaml.safe_load((CONFIG / "messages.yaml").read_text(encoding="utf-8"))
    keys = [k for k in msgs if k.startswith("onset_")]
    assert len(keys) >= 20
    for k in keys:
        assert set(msgs[k]) == {"en", "es", "fr", "sw", "hi", "de"}, k
    assert "OND" in t("onset_waiting_title", "sw", season="OND")


def test_criteria_from_config_matches_defaults():
    assert on.Criteria.from_config() == dataclasses.replace(CRIT)
