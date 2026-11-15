"""Unit tests for leaf wetness and the global pest & disease risk models (synthetic, network-free)."""

import datetime as dt
import math

import numpy as np
import pytest

from fieldshift.engine import risk_cards
from fieldshift.science import disease, leafwet
from fieldshift.science import globalrisk as gr

D0 = dt.date(2026, 6, 1)


def _hourly(days, t, rh, rain=None, start=D0):
    out = {"time": [], "temperature_2m": [], "relative_humidity_2m": []}
    if rain is not None:
        out["precipitation"] = []
    for d in range(days):
        day = start + dt.timedelta(days=d)
        for h in range(24):
            out["time"].append(f"{day.isoformat()}T{h:02d}:00")
            out["temperature_2m"].append(t[h] if isinstance(t, list) else t)
            out["relative_humidity_2m"].append(rh[h] if isinstance(rh, list) else rh)
            if rain is not None:
                out["precipitation"].append(rain[h] if isinstance(rain, list) else rain)
    return leafwet.from_dict(out)


def _input(h, tmean=22.0, rain=0.0, n=60, lat=10.0, lon=20.0):
    dates = [h.dates[0] - dt.timedelta(days=n - 30) + dt.timedelta(days=i) for i in range(n)]
    return gr.RiskInput(
        lat=lat,
        lon=lon,
        today=h.dates[0],
        dates=dates,
        tmax=np.full(n, tmean + 5),
        tmin=np.full(n, tmean - 5),
        rain=np.full(n, rain),
        hourly=h,
    )


# ---------------------------------------------------------------- leaf wetness
def test_rh90_and_rain_wetness():
    h = _hourly(1, 20.0, [95] * 6 + [70] * 18, rain=[0] * 10 + [1.0] * 2 + [0] * 12)
    wet = h.wet("rh90")
    assert wet.sum() == 8  # 6 humid hours + 2 rainy hours


def test_dew_point_and_dpd_hysteresis():
    assert leafwet.dew_point(np.array([20.0]), np.array([100.0]))[0] == pytest.approx(20.0, abs=0.05)
    assert leafwet.dew_point(np.array([20.0]), np.array([50.0]))[0] == pytest.approx(9.3, abs=0.2)
    # DPD: 1.5 °C (wet on) -> 2.0 °C (stays wet, < 2.2) -> 3 °C (dries off) -> 2.0 °C (no restart, > 1.8)
    t = np.array([20.0, 20.0, 20.0, 20.0])
    dew = np.array([18.5, 18.0, 17.0, 18.0])
    wet = leafwet.wet_mask(t, np.full(4, 80.0), dew=dew, method="dpd")
    assert wet.tolist() == [True, True, False, False]


def test_wet_periods_with_gap():
    h = _hourly(1, 20.0, [95] * 4 + [60] * 2 + [95] * 4 + [60] * 14)
    wet = h.wet()
    assert [p.hours for p in leafwet.wet_periods(h, wet, 0)] == [4, 4]
    assert [p.hours for p in leafwet.wet_periods(h, wet, 2)] == [8]


# ---------------------------------------------------------------- generic infection curve
def test_magarey_curve():
    p = {"tmin": 10.0, "topt": 20.0, "tmax": 30.0, "wmin": 6.0, "wmax": 24.0}
    assert gr.magarey_f(20, 10, 20, 30) == pytest.approx(1.0)
    assert gr.magarey_f(10, 10, 20, 30) == 0.0
    assert gr.magarey_w(20, p) == pytest.approx(6.0)
    assert gr.magarey_w(15, p) == pytest.approx(8.0)  # f(15) = 1.5 x 0.5 = 0.75
    assert math.isinf(gr.magarey_w(11, p))  # requirement above wmax -> infection impossible


# ---------------------------------------------------------------- per-model behaviour
def _night_wet(hours, t_wet, t_dry=None):
    t_dry = t_wet if t_dry is None else t_dry
    return [t_wet] * hours + [t_dry] * (24 - hours), [97] * hours + [60] * (24 - hours)


@pytest.mark.parametrize(
    "mid,t_wet,hours",
    [
        ("rice_blast", 22.0, 14),
        ("wheat_leaf_rust", 22.0, 10),
        ("wheat_stem_rust", 18.0, 12),
        ("coffee_leaf_rust", 23.0, 14),
        ("black_sigatoka", 26.5, 18),
    ],
)
def test_infection_models_wet_vs_dry(mid, t_wet, hours):
    t, rh = _night_wet(hours, t_wet)
    wet = gr.MODELS[mid].fn(_input(_hourly(3, t, rh), tmean=22.0))
    dry = gr.MODELS[mid].fn(_input(_hourly(3, t_wet, 55.0), tmean=22.0))
    assert max(wet.scores.values()) >= 0.85, wet.scores
    assert max(dry.scores.values()) == 0.0
    assert wet.evidence  # explanation for the Why panel


def test_infection_models_too_cold():
    t, rh = _night_wet(16, 3.0)
    # (rice blast excluded: BLASTAM classes any >= 10 h wet period as quasi-favourable, pattern 3)
    for mid in ("coffee_leaf_rust", "black_sigatoka", "wheat_stem_rust", "wheat_leaf_rust"):
        assert max(gr.MODELS[mid].fn(_input(_hourly(2, t, rh), tmean=22)).scores.values()) == 0.0


def test_rice_blast_blastam():
    assert gr.blastam_required(15.2) == 17
    assert gr.blastam_required(23.0) == 10
    assert math.isinf(gr.blastam_required(27.0))
    t, rh = _night_wet(14, 22.0)
    assert max(gr.rice_blast(_input(_hourly(2, t, rh), tmean=22.0)).scores.values()) == 1.0
    # 5-day mean 30 °C: BLASTAM quasi-favourable pattern 2 -> 0.5
    assert max(gr.rice_blast(_input(_hourly(2, t, rh), tmean=30.0)).scores.values()) == 0.5
    # 8 wet hours at 22 °C (needs 10): pattern 4 scaled
    t8, rh8 = _night_wet(8, 22.0)
    assert max(gr.rice_blast(_input(_hourly(2, t8, rh8), tmean=22.0)).scores.values()) == pytest.approx(0.4)


def test_gray_leaf_spot_index():
    # warm humid nights: 12 h at RH >= 90 % from 20:00, 26 °C all day -> both predictors at the epidemic level
    rh = [95] * 8 + [60] * 12 + [95] * 4
    hot_humid = gr.gray_leaf_spot(_input(_hourly(16, 26.0, rh)))
    cool_dry = gr.gray_leaf_spot(_input(_hourly(16, 15.0, 60.0)))
    assert max(hot_humid.scores.values()) == 1.0
    assert max(cool_dry.scores.values()) == 0.0
    assert len(hot_humid.scores) >= 6  # needs >= 10 days of hourly history


def test_coffee_rust_amplitude_band():
    t, rh = _night_wet(14, 23.0)
    inside = gr.coffee_leaf_rust(_input(_hourly(2, t, rh), tmean=22.0))  # Tmax 27
    outside = gr.coffee_leaf_rust(_input(_hourly(2, t, rh), tmean=26.0))  # Tmax 31
    assert max(inside.scores.values()) == 2 * max(outside.scores.values())


def test_wallin_severity_values():
    assert gr.wallin_sv(9, 20) == 0
    assert gr.wallin_sv(10, 20) == 1
    assert gr.wallin_sv(19, 20) == 4
    assert gr.wallin_sv(16, 9) == 1
    assert gr.wallin_sv(25, 9) == 4
    assert gr.wallin_sv(24, 28) == 0  # too hot
    assert gr.wallin_sv(24, 5) == 0  # too cold


def test_tropical_late_blight_cool_highland_nights_count():
    # highland: 9 °C humid nights (Hutton's Tmin >= 10 °C never met), 18 h at RH >= 90 %
    t = [9.0] * 18 + [16.0] * 6
    rh = [96] * 18 + [70] * 6
    h = _hourly(3, t, rh)
    trop = gr.tropical_late_blight(_input(h))
    assert max(trop.scores.values()) >= 0.25
    raw = {
        "time": [x.isoformat(timespec="minutes") for x in h.time],
        "temperature_2m": list(h.t),
        "relative_humidity_2m": list(h.rh),
    }
    hutton = disease.daily_scores(disease.hourly_by_day(raw))["late_blight"]
    assert max(hutton.values()) == 0.0
    assert "sv7" in trop.extra


def test_cassava_whitefly_katono_bands():
    h = _hourly(1, 25.0, 60.0)
    d = h.dates[0]
    assert gr.cassava_whitefly(_input(h, tmean=29, rain=3.0)).scores[d] == pytest.approx(1.0)  # 90 mm / 30 d
    assert gr.cassava_whitefly(_input(h, tmean=29, rain=10.0)).scores[d] == 0.0  # 300 mm / 30 d washes out
    assert gr.cassava_whitefly(_input(h, tmean=22, rain=3.0)).scores[d] == 0.0  # too cool
    x = _input(h, tmean=29, rain=3.0)
    x.rh = np.full(len(x.dates), 92.0)  # very humid: outside 55–70 % (taper 15 %) -> 0
    assert gr.cassava_whitefly(x).scores[d] == 0.0


def test_desert_locust_rain_trigger():
    h = _hourly(1, 30.0, 30.0)
    dry = gr.desert_locust(_input(h, tmean=30, rain=0.0))
    assert max(dry.scores.values()) == 0.0
    x = _input(h, tmean=30, rain=0.0)
    x.rain[x.di(h.dates[0]) - 10] = 40.0  # one 40 mm storm 10 days ago
    s = gr.desert_locust(x).scores[h.dates[0]]
    assert s == pytest.approx(1.0)
    x.tmax[:] = 18.0
    x.tmin[:] = 8.0  # cold winter: eggs develop too slowly
    assert gr.desert_locust(x).scores[h.dates[0]] == 0.0


# ---------------------------------------------------------------- geography & season
def test_geographic_ranges():
    assert gr.in_locust_area(18.0, 52.0)  # Empty Quarter
    assert gr.in_locust_area(20.0, -10.0)  # Mauritania
    assert not gr.in_locust_area(48.0, 10.0)  # Germany
    assert not gr.in_locust_area(-1.5, 37.3)  # Machakos (invasion, not recession area)
    assert not gr.MODELS["late_blight_tropical"].in_range(42.0, -76.0)
    assert gr.MODELS["late_blight_tropical"].in_range(-0.4, -78.5)
    assert gr.MODELS["cassava_whitefly"].in_range(0.3, 32.6)  # Uganda
    assert not gr.MODELS["cassava_whitefly"].in_range(-10.0, -50.0)  # Brazil: no CMD
    assert not disease.in_range("late_blight", 0.0)  # Hutton only outside the tropics
    assert disease.in_range("late_blight", 52.0)


def test_season_windows():
    m = gr.MODELS["gray_leaf_spot"]
    p = dt.date(2026, 5, 1)
    assert not m.in_season(dt.date(2026, 5, 10), p, False)
    assert m.in_season(dt.date(2026, 7, 10), p, False)
    assert not m.in_season(dt.date(2026, 11, 10), p, False)


def test_texts_complete_in_six_languages():
    tx = risk_cards.texts()
    for mid in gr.MODELS:
        meta = tx["models"][mid]
        for lang in ("en", "es", "fr", "sw", "hi", "de"):
            assert meta["name"].get(lang), (mid, lang)
            assert meta["action"].get(lang), (mid, lang)
        assert meta["model"] and meta["summary"] and meta["references"]
    for lang in ("en", "es", "fr", "sw", "hi", "de"):
        title = risk_cards.tx("risk_title_disease", lang, risk="X", name="Y", day="Z")
        assert "Y" in title and "Z" in title
    for did in disease.DISEASES:
        assert risk_cards.legacy_name(did, "sw", "") != ""


def test_no_brand_or_product_advice():
    import re

    tx = risk_cards.texts()
    blob = str(tx).lower()
    for word in ("mancozeb", "tebuconazole", "azoxystrobin", "chlorpyrifos", "®", "™"):
        assert word not in blob
    assert not re.search(r"\bspray (with|using)\b", blob)
