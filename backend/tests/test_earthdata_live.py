"""Earthdata live layers: parsers, credential handling, cache fallback, IMERG Late fill, and the SMAP / ECOSTRESS /
GRACE-DA wiring in the advice. No network: requests are faked or served from a temporary cache."""

import datetime as dt

import numpy as np
import pytest
import yaml
from fastapi.testclient import TestClient

from fieldshift.data import earthdata, http
from fieldshift.data.http import DataUnavailable
from fieldshift.engine import context, live_layers, service
from fieldshift.engine.context import _fill_nrt
from fieldshift.main import app

client = TestClient(app)
FALLON = {"lat": 39.44087, "lon": -118.83012, "crop": "alfalfa", "planting_date": "2024-03-15"}
AMES = {"lat": 42.01239, "lon": -93.72204, "crop": "maize"}

GIOVANNI_CSV = """prod_name,GPM_3IMERGDL.07
param_short_name,precipitation
unit,mm/day
undef,-9999.9
lat,39.45
lon,-118.75

Timestamp (UTC),Data
2026-09-01 00:00,0
2026-09-02 00:00,3.5
2026-09-03 00:00,-9999.9
"""


def test_parse_giovanni_csv_drops_fill_values():
    d = earthdata.parse_giovanni_csv(GIOVANNI_CSV)
    assert d["meta"]["unit"] == "mm/day"
    assert d["rows"] == [["2026-09-01", 0.0], ["2026-09-02", 3.5], ["2026-09-03", None]]
    with pytest.raises(DataUnavailable):
        earthdata.parse_giovanni_csv('{"code": "401", "message": "Failed validating user token"}')


def test_parse_dap_ascii():
    txt = (
        "Dataset: SMAP_L4_SM_gph_20261110T013000_Vv8013_001.h5\n"
        "/Geophysical_Data/sm_rootzone[0], 0.0298674\n"
        "/Geophysical_Data/sm_rootzone_pctl[0], -9999\n"
    )
    v = earthdata.parse_dap_ascii(txt)
    assert v["/Geophysical_Data/sm_rootzone"] == pytest.approx(0.0298674)
    assert v["/Geophysical_Data/sm_rootzone_pctl"] is None


def test_ease2_m09_grid():
    # equator / prime meridian sits on the grid centre (1624 rows × 3856 columns)
    assert earthdata.ease2_m09(0.001, 0.001) == (811, 1928)
    assert earthdata.ease2_m09(-0.001, -0.001) == (812, 1927)
    # Fallon demo cell (checked against SPL4SMGP.008 values via OPeNDAP on the data box)
    assert earthdata.ease2_m09(39.472, -118.777) == (295, 655)
    r_n, _ = earthdata.ease2_m09(84.9, 0)
    r_s, _ = earthdata.ease2_m09(-84.9, 0)
    assert 0 <= r_n < 5 and 1619 <= r_s <= 1623


def test_credentials_order_and_off_switch(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELDSHIFT_EARTHDATA", "auto")
    monkeypatch.setenv("EARTHDATA_USER", "u")
    monkeypatch.setenv("EARTHDATA_PASS", "p")
    assert earthdata.credentials() == ("u", "p")
    monkeypatch.delenv("EARTHDATA_USER")
    f = tmp_path / "edl"
    f.write_text("fileuser:filepass\n")
    monkeypatch.setenv("FIELDSHIFT_EARTHDATA_FILE", str(f))
    assert earthdata.credentials() == ("fileuser", "filepass")
    monkeypatch.setenv("FIELDSHIFT_EARTHDATA", "off")
    assert earthdata.credentials() is None and not earthdata.available()


@pytest.fixture
def tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(http, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(http, "DEMO_DIR", tmp_path / "demo")
    http._host_down.clear()
    return tmp_path


def test_giovanni_series_live_then_cached_without_credentials(monkeypatch, tmp_cache):
    class Resp:
        status_code = 200
        text = GIOVANNI_CSV

    class FakeClient:
        def get(self, url, params=None, headers=None, timeout=None):
            assert headers == {"authorizationtoken": "tok"}  # token only in the header, never in params
            return Resp()

    monkeypatch.setattr(earthdata, "_client", lambda: FakeClient())
    monkeypatch.setattr(earthdata, "_giovanni_token", lambda: "tok")
    s, st, meta = earthdata.giovanni_series(
        earthdata.IMERG_LATE, 39.44, -118.83, dt.date(2026, 9, 1), dt.date(2026, 9, 3)
    )
    assert st == "live" and s == [(dt.date(2026, 9, 1), 0.0), (dt.date(2026, 9, 2), 3.5)]
    cached = list((tmp_cache / "cache").glob("*.json.gz"))
    assert cached and all(b"tok" not in __import__("gzip").open(p).read() for p in cached)

    # credentials gone: the same request is served from the cache once its TTL has passed
    def no_net():
        raise DataUnavailable("no Earthdata Login configured")

    monkeypatch.setattr(earthdata, "_giovanni_token", no_net)
    s2, st2, _ = earthdata.giovanni_series(
        earthdata.IMERG_LATE, 39.44, -118.83, dt.date(2026, 9, 1), dt.date(2026, 9, 3), ttl_s=0
    )
    assert st2 == "cache" and s2 == s


def test_cached_call_without_anything_raises(tmp_cache):
    def fail():
        raise DataUnavailable("no Earthdata Login configured")

    with pytest.raises(DataUnavailable):
        http.cached_call("https://api.giovanni.earthdata.nasa.gov/timeseries", {"data": "x"}, fail, ttl_s=1)


def test_imerg_late_fills_days_after_final():
    dates = [dt.date(2026, 9, 1) + dt.timedelta(days=k) for k in range(60)]
    final = np.full(60, 1.0)
    final[30:] = np.nan  # Final ends 30 Sep
    late = np.full(40, 5.0)  # Late from 21 Sep (overlaps Final, must not overwrite it)
    late[-2:] = np.nan
    info = _fill_nrt(dates, final, (late, "live", {"start": dt.date(2026, 9, 21), "late_last": "x"}))
    assert info is not None and info["imerg_final_last"] == "2026-09-30"
    assert info["imerg_nrt_first"] == "2026-10-01" and info["imerg_nrt_days"] == 28
    assert np.all(final[:30] == 1.0) and np.all(final[30:58] == 5.0) and np.isnan(final[58:]).all()


def _live(today: dt.date, *, smap_pctl: float, gws: float, eco: float) -> dict:
    days = [today - dt.timedelta(days=k) for k in (9, 6, 3)]
    return {
        "smap_l4": [(d, 0.08) for d in days],
        "smap_l4_surface": [(d, 0.05) for d in days],
        "smap_l4_pctl": [(d, smap_pctl) for d in days],
        "ecostress": [(today - dt.timedelta(days=k), eco) for k in (20, 12, 4)],
        "grace_da_gws": [(today - dt.timedelta(days=80 + 7 * k), gws) for k in range(10, -1, -1)],
        "grace_da_rtzsm": [(today - dt.timedelta(days=80 + 7 * k), 30.0) for k in range(10, -1, -1)],
        "_status": {"smap_l4": "live", "ecostress": "live", "grace_da": "live"},
    }


def test_advice_shows_live_smap_grace_da_and_ecostress(monkeypatch):
    today = dt.date.today()
    monkeypatch.setattr(
        live_layers, "fetch", lambda lat, lon, t, **k: _live(t, smap_pctl=50.0, gws=4.0, eco=1.0)
    )
    context._ctx_cache.clear()
    a = client.post(
        "/api/advice",
        json={**FALLON, "irrigation": "flood", "planting_date": (today - dt.timedelta(days=200)).isoformat()},
    ).json()
    sat = a["water"]["satellite"]
    assert sat["smap"]["rootzone_m3m3"] == pytest.approx(0.08) and sat["smap"]["rootzone_pctl"] == 50.0
    assert sat["smap"]["agreement"] in ("agree", "satellite_drier", "satellite_wetter")
    assert not any(c["id"] == "smap_check" for c in a["cards"])  # irrigated: SMAP shown for context only
    assert sat["et"]["last_et_mm"] == pytest.approx(1.0) and sat["et"]["recent_overpasses"] >= 2
    assert not any(c["id"] == "et_low" for c in a["cards"])  # evidence only (VALIDATION V6), never a card
    assert sat["et"]["recent_ratio"] is not None and any("V6" in st for st in sat["et"]["why"]["steps"])
    g = a["drought"]["grace_da"]
    assert g["groundwater_pct"] == 4.0 and g["groundwater_class"] == "extremely_dry"
    assert any(c["id"] == "groundwater_low" for c in a["cards"])
    assert a["drought"]["sm_percentile"] == 50.0
    ids = {s["id"] for s in a["sources"]}
    assert {"grace_da", "smap_l4", "ecostress"} <= ids
    assert {"smap_rootzone", "grace_da_gws", "eta_model"} <= {s["id"] for s in a["series"]}
    context._ctx_cache.clear()


def test_rainfed_field_gets_smap_disagreement_card(monkeypatch):
    today = dt.date.today()
    monkeypatch.setattr(
        live_layers, "fetch", lambda lat, lon, t, **k: _live(t, smap_pctl=3.0, gws=50.0, eco=4.0)
    )
    context._ctx_cache.clear()
    a = client.post(
        "/api/advice",
        json={**AMES, "irrigation": "none", "planting_date": (today - dt.timedelta(days=10)).isoformat()},
    ).json()
    sm = a["water"]["satellite"]["smap"]
    assert sm["rootzone_pctl"] == 3.0
    if sm["model_pct_left"] >= 70:  # synthetic weather decides the model side; the card follows the rule
        card = next(c for c in a["cards"] if c["id"] == "smap_check")
        assert "smap_l4" in card["why"]["sources"] and card["risk"] == "low"
    assert not any(
        c["id"] in ("groundwater_low", "et_low") for c in a["cards"]
    )  # rain-fed, normal groundwater
    context._ctx_cache.clear()


def test_advice_without_live_layers_is_unchanged():
    a = client.post("/api/advice", json={**FALLON, "irrigation": "flood"}).json()
    assert a["drought"].get("grace_da") is None
    assert not any(c["id"] in ("smap_check", "et_low", "groundwater_low") for c in a["cards"])
    assert not any(s["id"] in ("grace_da", "gpm_imerg_nrt") for s in a["sources"])


def test_new_message_keys_in_all_languages():
    msgs = yaml.safe_load((service.CONFIG / "messages.yaml").read_text())
    for key in (
        "groundwater_low_title",
        "groundwater_low_detail",
        "smap_drier_title",
        "smap_drier_detail",
        "smap_wetter_title",
        "smap_wetter_detail",
    ):
        assert set(msgs[key]) == {"en", "es", "fr", "sw", "hi", "de"}, key
