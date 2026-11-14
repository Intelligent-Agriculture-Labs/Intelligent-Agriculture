import datetime as dt

from fastapi.testclient import TestClient

from fieldshift.main import app

client = TestClient(app)
FIELD = {
    "lat": 39.47,
    "lon": -118.78,
    "crop": "alfalfa",
    "planting_date": "2024-03-15",
    "irrigation": "flood",
}


def test_health_crops_presets():
    assert client.get("/api/health").json()["status"] == "ok"
    crops = client.get("/api/crops").json()
    assert any(c["id"] == "alfalfa" for c in crops) and len(crops) >= 15
    assert len(client.get("/api/presets").json()) >= 3


def test_advice_contract_and_why():
    r = client.post("/api/advice", json={**FIELD, "as_of": None})
    assert r.status_code == 200
    a = r.json()
    assert a["cards"], "at least one card"
    for c in a["cards"]:
        assert c["risk"] in ("low", "moderate", "high", "severe")
        assert c["why"]["steps"] and c["why"]["sources"] and 0 <= c["why"]["confidence"] <= 1
    assert [c["priority"] for c in a["cards"]] == list(range(1, len(a["cards"]) + 1))
    assert a["mock"] is False
    ids = {s["id"] for s in a["series"]}
    assert {"precip", "et0", "soil_depletion"} <= ids


def test_advice_irrigation_card_in_hot_dry_summer():
    # synthetic forecast is hot and dry -> irrigated field must get an irrigation recommendation within the window
    a = client.post(
        "/api/advice",
        json={
            **FIELD,
            "crop": "maize",
            "planting_date": (dt.date.today() - dt.timedelta(days=60)).isoformat(),
            "irrigation": "drip",
        },
    ).json()
    water = a["water"]
    assert water["taw_mm"] > 0
    card = next(c for c in a["cards"] if c["id"] == "irrigate")
    assert card["title"]


def test_advice_translations():
    a = client.post("/api/advice", json={**FIELD, "lang": "es"}).json()
    b = client.post("/api/advice", json={**FIELD, "lang": "en"}).json()
    assert a["cards"][0]["title"] != b["cards"][0]["title"] or a["cards"][0]["id"] not in ("irrigate",)


def test_unknown_crop_422():
    assert client.post("/api/advice", json={**FIELD, "crop": "unobtainium"}).status_code == 422


def test_simulate_scenarios():
    base = client.post(
        "/api/simulate",
        json={
            "lat": 39.47,
            "lon": -118.78,
            "crop": "maize",
            "planting_date": "2020-05-01",
            "irrigation_strategy": "full",
            "years": 10,
        },
    ).json()
    hot = client.post(
        "/api/simulate",
        json={
            "lat": 39.47,
            "lon": -118.78,
            "crop": "maize",
            "planting_date": "2020-05-01",
            "irrigation_strategy": "deficit_50",
            "delta_t_c": 2,
            "years": 10,
        },
    ).json()
    assert len(base["years"]) == 10
    assert hot["summary"]["irrigation_median_mm"] < base["summary"]["irrigation_median_mm"]
    assert hot["baseline"]["yield_median"] == base["summary"]["yield_median"]


def test_rotations_at_least_three_with_explanations():
    r = client.post(
        "/api/rotations",
        json={"lat": 39.47, "lon": -118.78, "current_rotation": ["alfalfa"] * 4, "irrigation": "flood"},
    )
    assert r.status_code == 200
    j = r.json()
    assert len(j["strategies"]) >= 3
    assert j["strategies"][0]["is_current"]
    for s in j["strategies"]:
        assert s["evidence"] and s["info_gaps"] and s["risks_local_review"]
        assert len(s["calendar"]) == 12 * max(sl["year"] for sl in s["slots"])
        assert {m["id"] for m in s["metrics"]} >= {"water", "income", "soil", "pests", "risk"}
    assert "not replace" in j["disclaimer"]


def test_climate_and_exports():
    c = client.get("/api/climate", params={"lat": 39.47, "lon": -118.78}).json()
    assert c["years"][0] == 1984 and c["metrics"] and c["monthly_normals"]
    csv = client.get(
        "/api/export/advice.csv",
        params={"lat": 39.47, "lon": -118.78, "crop": "alfalfa", "planting_date": "2024-03-15"},
    )
    assert csv.status_code == 200 and csv.text.startswith("date,series,value")
    gj = client.get(
        "/api/export/field.geojson",
        params={"lat": 39.47, "lon": -118.78, "crop": "alfalfa", "planting_date": "2024-03-15"},
    ).json()
    assert gj["type"] == "FeatureCollection"


def test_rotations_respect_climate_zone():
    r = client.post(
        "/api/rotations",
        json={"lat": -1.5, "lon": 37.3, "current_rotation": ["maize"] * 3, "irrigation": "none"},
    ).json()
    ids = {s["id"] for s in r["strategies"]}
    assert "alfalfa_teff_wheat" not in ids and "split_season_alfalfa" not in ids


def test_static_web_serving(tmp_path, monkeypatch):
    import importlib

    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "rotations.html").write_text("<html>rot</html>")
    monkeypatch.setenv("FIELDSHIFT_WEB_DIR", str(tmp_path))
    import fieldshift.main as m

    m2 = importlib.reload(m)
    c = TestClient(m2.app)
    assert c.get("/rotations").text == "<html>rot</html>"
    assert c.get("/some/deep/link").text == "<html>app</html>"
    assert c.get("/../../etc/passwd").text == "<html>app</html>"
    assert c.get("/api/health").json()["status"] == "ok"
    monkeypatch.delenv("FIELDSHIFT_WEB_DIR")
    importlib.reload(m)


def test_reported_last_irrigation_changes_state_and_confidence():
    base = {
        **FIELD,
        "crop": "maize",
        "planting_date": (dt.date.today() - dt.timedelta(days=70)).isoformat(),
        "irrigation": "drip",
    }
    a = client.post("/api/advice", json=base).json()
    last = (dt.date.today() - dt.timedelta(days=12)).isoformat()
    b = client.post(
        "/api/advice", json={**base, "last_irrigation_date": last, "last_irrigation_mm": 30}
    ).json()
    assert b["water"]["root_zone_depletion_mm"] != a["water"]["root_zone_depletion_mm"]
    wa = next(c for c in a["cards"] if c["category"] == "water")["why"]["confidence"]
    wb = next(c for c in b["cards"] if c["category"] == "water")["why"]["confidence"]
    assert wb > wa


def test_planner_contract():
    r = client.post(
        "/api/planner",
        json={
            "lat": 39.47,
            "lon": -118.78,
            "crop": "maize",
            "planting_date": "2020-05-01",
            "irrigation": "drip",
            "water_allocation_mm": 300,
        },
    )
    assert r.status_code == 200
    j = r.json()
    assert (
        j["sowing_scan"]
        and j["window"]
        and j["stages"]
        and j["operations"]
        and j["water_budget"]
        and j["risk_calendar"]
    )
    assert j["water"]["full_need_median_mm"] >= j["water"]["season_irrigation_median_mm"]
    assert j["water"]["coverage_pct"] is not None and j["water"]["coverage_pct"] <= 100


def test_planner_allocation_note_present_when_short():
    j = client.post(
        "/api/planner",
        json={
            "lat": 39.47,
            "lon": -118.78,
            "crop": "maize",
            "planting_date": "2020-05-01",
            "irrigation": "drip",
            "water_allocation_mm": 100,
        },
    ).json()
    assert j["water"]["note"] and "%" in j["water"]["note"]


def test_rotation_plan_flags_short_return_and_optimizes():
    body = {
        "lat": 39.47,
        "lon": -118.78,
        "irrigation": "drip",
        "history": [{"year": 2024, "crop": "maize"}, {"year": 2025, "crop": "maize"}],
        "plan": [
            {"year": 2026, "crop": "maize"},
            {"year": 2027, "crop": "soybean"},
            {"year": 2028, "crop": "maize"},
        ],
    }
    r = client.post("/api/rotations/plan", json=body)
    assert r.status_code == 200
    j = r.json()
    y26 = j["years"][0]
    assert y26["verdict"] == "problem" and any(
        i["id"] in ("return_interval", "rule:continuous_maize") for i in y26["issues"]
    )
    assert j["summary"]["headline"] and j["crops_available"]
    assert j["optimized"] is None or j["optimized"]["score"] >= j["summary"]["score"]
    assert all(c not in ("alfalfa",) for p in (j["optimized"] or {"plan": []})["plan"] for c in [p["crop"]])


def test_advice_text_is_short_and_translated():
    r = client.post("/api/advice/text", json={**FIELD, "lang": "sw"}, params={"name": "Shamba 1"}).json()
    assert r["chars"] <= 320 and r["text"].startswith("FieldShift - Shamba 1: Wiki hii")


def test_rotation_plan_reports_impact():
    body = {
        "lat": 39.47,
        "lon": -118.78,
        "irrigation": "drip",
        "history": [{"year": 2025, "crop": "maize"}],
        "plan": [
            {"year": 2026, "crop": "maize"},
            {"year": 2027, "crop": "maize"},
            {"year": 2028, "crop": "maize"},
        ],
    }
    j = client.post("/api/rotations/plan", json=body).json()
    assert j["impact"] is None or ("per_ha" in j["impact"] and j["impact"]["headline"])


def test_sms_parts_gsm7_and_ucs2():
    from fieldshift.main import _to_gsm, sms_parts

    assert sms_parts("a" * 160) == 1 and sms_parts("a" * 161) == 2 and sms_parts("a" * 306) == 2
    assert sms_parts("é" * 160) == 1  # é is in GSM-7
    assert sms_parts("ó" * 70) == 1 and sms_parts("ó" * 71) == 2  # ó is not -> UCS-2
    assert _to_gsm("Riego — 25 °C, días") == "Riego - 25 C, dias"
    assert _to_gsm("सिंचाई") == "सिंचाई"


def test_advice_text_fits_two_sms_for_latin_languages():
    for lang in ("en", "es", "fr", "sw", "de", "hi"):
        r = client.post("/api/advice/text", json={**FIELD, "lang": lang}).json()
        assert r["sms_parts"] <= 2, (lang, r)
