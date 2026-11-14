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
