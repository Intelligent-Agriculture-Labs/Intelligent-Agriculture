"""IMERG + GRACE wiring in the API: drought status, groundwater card, rotation weighting, sources, translations."""

import datetime as dt

import numpy as np
import yaml
from fastapi.testclient import TestClient

from fieldshift.data import sources
from fieldshift.engine import context, service
from fieldshift.main import app

client = TestClient(app)
FALLON = {"lat": 39.44087, "lon": -118.83012, "crop": "alfalfa", "planting_date": "2024-03-15"}


def test_irrigated_field_with_falling_storage_gets_water_reserves_card():
    a = client.post("/api/advice", json={**FALLON, "irrigation": "flood"}).json()
    g = a["drought"]["groundwater"]
    assert g is not None and g["status"] in ("declining", "likely_declining")
    assert g["slope_cm_yr"] < 0 and 0 <= g["p_value"] < 0.2 and g["resolution_km"] == 300
    card = next(c for c in a["cards"] if c["id"] == "groundwater_trend")
    assert card["category"] == "planning" and "grace_fo" in card["why"]["sources"]
    assert any("~300 km" in cv for cv in card["why"]["caveats"])  # coarse-resolution caveat
    assert any("p = " in s for s in card["why"]["steps"])  # trend significance is stated
    assert {"grace_tws", "grace_trend"} <= {s["id"] for s in a["series"]}
    assert any(s["id"] == "grace_fo" and s["last_date"] for s in a["sources"])
    assert "grace_fo" in a["drought"]["why"]["sources"]


def test_rainfed_field_gets_no_groundwater_card_but_status_context():
    a = client.post("/api/advice", json={**FALLON, "irrigation": "none"}).json()
    assert a["drought"]["groundwater"] is not None
    assert not any(c["id"] == "groundwater_trend" for c in a["cards"])
    assert a["drought"]["rain_source"]["method"] == "power"  # conftest: IMERG unavailable -> POWER only


def test_groundwater_card_translated():
    titles = {
        lang: next(
            c["title"]
            for c in client.post("/api/advice", json={**FALLON, "irrigation": "flood", "lang": lang}).json()[
                "cards"
            ]
            if c["id"] == "groundwater_trend"
        )
        for lang in ("en", "es", "fr", "sw", "hi", "de")
    }
    assert len(set(titles.values())) == 6 and "2003" in titles["de"]
    msgs = yaml.safe_load((service.CONFIG / "messages.yaml").read_text())
    for key in ("groundwater_title", "groundwater_detail"):
        assert set(msgs[key]) == {"en", "es", "fr", "sw", "hi", "de"}


def test_imerg_blend_credited_in_why(monkeypatch):
    def fake_imerg(lat, lon, start, end):
        n = (end - start).days + 1
        a = np.full(n, 1.0)
        a[: max(0, (dt.date(1998, 1, 1) - start).days)] = np.nan
        a[-70:] = np.nan
        return a, "live"

    monkeypatch.setattr(sources, "imerg_daily", fake_imerg)
    context._ctx_cache.clear()
    a = client.post("/api/advice", json={**FALLON, "irrigation": "flood"}).json()
    assert a["drought"]["rain_source"]["imerg_used"] is True
    assert "gpm_imerg" in a["drought"]["why"]["sources"]
    assert any("GPM IMERG" in s for s in a["drought"]["why"]["steps"])
    precip = next(s for s in a["series"] if s["id"] == "precip")
    assert precip["source"] == "gpm_imerg"
    assert any(s["id"] == "gpm_imerg" for s in a["sources"])
    context._ctx_cache.clear()


def test_rotations_weight_water_where_storage_falls():
    j = client.post(
        "/api/rotations",
        json={
            "lat": FALLON["lat"],
            "lon": FALLON["lon"],
            "current_rotation": ["alfalfa"] * 4,
            "irrigation": "flood",
        },
    ).json()
    assert j["groundwater_note"] and "GRACE" in j["groundwater_note"]
    assert all("grace_fo" in s["sources"] for s in j["strategies"])
    j2 = client.post(
        "/api/rotations",
        json={
            "lat": FALLON["lat"],
            "lon": FALLON["lon"],
            "current_rotation": ["alfalfa"] * 4,
            "irrigation": "none",
        },
    ).json()
    assert j2["groundwater_note"] is None
