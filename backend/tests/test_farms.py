import pytest
from fastapi.testclient import TestClient

from fieldshift.engine import farms
from fieldshift.main import app


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(farms, "DB_PATH", tmp_path / "farms.sqlite")


def F(fid, ts, name="A", deleted=False):
    return {
        "id": fid,
        "name": name,
        "lat": 1,
        "lon": 2,
        "crop": "maize",
        "planting_date": "2026-05-01",
        "irrigation": "none",
        "current_rotation": ["maize"],
        "updated_at": ts,
        "deleted": deleted,
    }


def test_merge_last_writer_wins_and_tombstones():
    server = [F("a", "2026-11-14T10:00:00Z", "old"), F("b", "2026-11-14T10:00:00Z")]
    incoming = [
        F("a", "2026-11-14T11:00:00Z", "new"),
        F("b", "2026-11-14T09:00:00Z", "stale"),
        F("c", "2026-11-14T12:00:00Z", deleted=True),
    ]
    m = {f["id"]: f for f in farms.merge_fields(server, incoming)}
    assert m["a"]["name"] == "new" and m["b"]["name"] == "A" and m["c"]["deleted"]


def test_sync_flow_two_devices():
    c = TestClient(app)
    phone = c.post(
        "/api/farms", json={"name": "Moyle farm", "fields": [F("f1", "2026-11-14T10:00:00Z", "North pivot")]}
    ).json()
    assert len(phone["sync_code"]) == 9 and phone["version"] == 1
    pc = c.post("/api/farms/join", json={"sync_code": phone["sync_code"].replace("-", "").lower()}).json()
    assert pc["farm_id"] == phone["farm_id"] and pc["fields"][0]["name"] == "North pivot"
    pc2 = c.put(
        f"/api/farms/{pc['farm_id']}",
        json={"fields": [F("f2", "2026-11-14T10:05:00Z", "South field")], "settings": {"units": "imperial"}},
    ).json()
    assert pc2["version"] == 2 and {f["id"] for f in pc2["fields"]} == {"f1", "f2"}
    again = c.get(f"/api/farms/{phone['farm_id']}").json()
    assert again["settings"]["units"] == "imperial" and len(again["fields"]) == 2
    assert c.get("/api/farms/doesnotexist").status_code == 404
    assert c.post("/api/farms/join", json={"sync_code": "ZZZZ-ZZZZ"}).status_code == 404
