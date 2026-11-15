"""GPM IMERG rain: POWER-API parsing and the POWER/IMERG blend (science/rainblend.py)."""

import datetime as dt

import numpy as np
import pytest

from fieldshift.data import sources
from fieldshift.data.http import Fetched
from fieldshift.engine import context
from fieldshift.science import rainblend as rb

REAL_IMERG = sources.imerg_daily  # captured before conftest patches it out


def _dates(n, start=dt.date(2000, 1, 1)):
    return [start + dt.timedelta(days=i) for i in range(n)]


def test_imerg_parsing_utc_fill_values_and_alignment(monkeypatch):
    seen = {}

    def fake_get_json(url, params, **kw):
        seen.update(params)
        return Fetched(
            {
                "properties": {
                    "parameter": {"IMERG_PRECTOT": {"19980101": 1.5, "19980102": -999.0, "19980104": 0.0}}
                }
            },
            "live",
            0.0,
        )

    monkeypatch.setattr(sources, "get_json", fake_get_json)
    out = REAL_IMERG(1.0, 37.0, dt.date(1997, 12, 30), dt.date(1998, 1, 5))
    assert out is not None
    arr, status = out
    assert status == "live"
    assert seen["time-standard"] == "UTC"  # POWER serves IMERG only on UTC days
    assert seen["start"] == "19980101"  # clipped to the start of the IMERG record
    assert len(arr) == 7
    assert np.isnan(arr[0]) and np.isnan(arr[1])  # before 1998
    assert arr[2] == 1.5 and np.isnan(arr[3]) and arr[5] == 0.0 and np.isnan(arr[6])


def test_imerg_unavailable_returns_none(monkeypatch):
    def boom(*a, **k):
        raise sources.DataUnavailable("offline")

    monkeypatch.setattr(sources, "get_json", boom)
    assert REAL_IMERG(1.0, 37.0, dt.date(2020, 1, 1), dt.date(2020, 2, 1)) is None
    assert REAL_IMERG(1.0, 37.0, dt.date(1990, 1, 1), dt.date(1995, 1, 1)) is None  # before IMERG


def test_blend_daily_and_missing_imerg():
    p = np.array([0.0, 10.0, 4.0])
    i = np.array([2.0, 0.0, np.nan])
    np.testing.assert_allclose(rb.blend_daily(p, i, 0.5), [1.0, 5.0, 4.0])


def test_climatological_ratio_and_bridge_factor():
    d = _dates(3 * 365)
    p = np.full(len(d), 2.0)
    i = np.full(len(d), 3.0)
    r = rb.climatological_ratio(p, i, d)
    np.testing.assert_allclose(r, 1.5)
    np.testing.assert_allclose(rb.bridge_factor(r), 1.25)
    # extreme ratios are capped
    r2 = rb.climatological_ratio(p, p * 100, d)
    assert r2.max() == rb.RATIO_CAP[1]


def test_monthly_rescale_matches_imerg_monthly_totals_keeps_power_timing():
    d = _dates(60)
    p = np.zeros(60)
    p[[3, 40]] = 10.0
    i = np.zeros(60)
    i[[5, 6, 45]] = [5.0, 5.0, 30.0]
    out = rb.monthly_rescale(p, i, d)
    jan = slice(0, 31)
    assert out[jan].sum() == pytest.approx(i[jan].sum())
    assert out[3] > 0 and out[5] == 0  # POWER's wet day keeps the rain


def test_blend_for_location_policy():
    d = _dates(4 * 365)
    rng = np.random.default_rng(1)
    p = rng.gamma(0.5, 6, len(d))
    i = rng.gamma(0.5, 8, len(d))
    i[-60:] = np.nan  # IMERG latency at the end of the record
    out, meta = rb.blend_for_location(-1.5, d, p, i)
    assert meta["imerg_used"] and meta["method"] == "blend_50_50" and meta["zone"] == "tropics"
    np.testing.assert_allclose(out[:100], 0.5 * (p[:100] + i[:100]))
    mon = np.array([x.month - 1 for x in d])
    clim = rb.climatological_ratio(p, i, d)
    np.testing.assert_allclose(out[-60:], p[-60:] * rb.bridge_factor(clim)[mon[-60:]])
    # outside the validated band and without IMERG: POWER unchanged
    out2, meta2 = rb.blend_for_location(55.0, d, p, i)
    assert not meta2["imerg_used"] and meta2["reason"] == "outside_validated_band"
    np.testing.assert_array_equal(out2, p)
    out3, meta3 = rb.blend_for_location(10.0, d, p, None)
    assert not meta3["imerg_used"] and out3 is p


def test_summarise_counts_wins():
    def m(v):
        return {
            "daily_r": v,
            "wet_day_csi": v,
            "monthly_r": v,
            "monthly_kge": v,
            "anom3_r": v,
            "monthly_bias_pct": 5,
        }

    rows = [
        {"site": "a", "zone": "tropics", "metrics": {"P_lst": m(0.4), "B50": m(0.5)}},
        {"site": "b", "zone": "extratropics", "metrics": {"P_lst": m(0.6), "B50": m(0.5)}},
    ]
    s = rb.summarise(rows, ["P_lst", "B50"])
    assert s["all"]["B50"]["daily_r_wins"] == "1/2"
    assert s["tropics"]["B50"]["monthly_kge_wins"] == "1/1"


def test_context_uses_blended_rain(monkeypatch):
    def fake_imerg(lat, lon, start, end):
        n = (end - start).days + 1
        a = np.full(n, 4.0)
        a[: (dt.date(1998, 1, 1) - start).days] = np.nan
        return a, "live"

    monkeypatch.setattr(sources, "imerg_daily", fake_imerg)
    context._ctx_cache.clear()
    ctx = context.build(-1.57, 37.2, dt.date.today())
    assert ctx.rain_meta["imerg_used"]
    assert ctx.statuses["gpm_imerg"] == "live"
    k = ctx.weather.dates.index(dt.date(2010, 6, 1))
    raw = sources.power_daily(-1.57, 37.2, context.HIST_START, dt.date.today())
    assert ctx.weather.rain[k] == pytest.approx(0.5 * raw["PRECTOTCORR"][k] + 2.0)
    context._ctx_cache.clear()


def test_power_only_rain_kept_for_models_trained_on_power(monkeypatch):
    def fake_imerg(lat, lon, start, end):
        n = (end - start).days + 1
        a = np.full(n, 9.0)
        a[: (dt.date(1998, 1, 1) - start).days] = np.nan
        return a, "live"

    monkeypatch.setattr(sources, "imerg_daily", fake_imerg)
    context._ctx_cache.clear()
    ctx = context.build(-1.57, 37.2, dt.date.today())
    raw = sources.power_daily(-1.57, 37.2, context.HIST_START, dt.date.today())["PRECTOTCORR"]
    k = ctx.weather.dates.index(dt.date(2012, 3, 1))
    assert ctx.rain_power is not None and ctx.rain_power[k] == pytest.approx(raw[k])
    assert ctx.weather.rain[k] != pytest.approx(raw[k])
    context._ctx_cache.clear()
