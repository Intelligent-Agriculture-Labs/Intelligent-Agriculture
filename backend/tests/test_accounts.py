import pytest
from fastapi.testclient import TestClient

from fieldshift.engine import accounts, farms
from fieldshift.main import app


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(farms, "DB_PATH", tmp_path / "farms.sqlite")
    accounts._fails.clear()


def test_register_login_sync_two_devices():
    c = TestClient(app)
    field = {
        "id": "f1",
        "name": "North",
        "lat": 1,
        "lon": 2,
        "crop": "maize",
        "planting_date": "2026-05-01",
        "irrigation": "none",
        "current_rotation": ["maize"],
        "updated_at": "2026-11-14T10:00:00Z",
    }
    r = c.post(
        "/api/auth/register",
        json={"email": "Farmer@Example.org", "password": "correct horse", "name": "Ana", "fields": [field]},
    )
    assert r.status_code == 200
    tok = r.json()["token"]
    assert (
        r.json()["user"]["email"] == "farmer@example.org" and r.json()["farm"]["fields"][0]["name"] == "North"
    )
    assert (
        c.post(
            "/api/auth/register", json={"email": "farmer@example.org", "password": "another one"}
        ).status_code
        == 409
    )
    # second device logs in and adds a field
    tok2 = c.post(
        "/api/auth/login", json={"email": "farmer@example.org", "password": "correct horse"}
    ).json()["token"]
    f2 = {**field, "id": "f2", "name": "South", "updated_at": "2026-11-14T11:00:00Z"}
    r = c.put("/api/me/farm", json={"fields": [f2]}, headers={"Authorization": f"Bearer {tok2}"})
    assert {f["id"] for f in r.json()["fields"]} == {"f1", "f2"}
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert len(me["farm"]["fields"]) == 2
    # wrong password, logout, protected route
    assert (
        c.post("/api/auth/login", json={"email": "farmer@example.org", "password": "nope"}).status_code == 401
    )
    c.post("/api/auth/logout", headers={"Authorization": f"Bearer {tok}"})
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    assert c.get("/api/me/farm").status_code == 401


def test_validation_and_password_change_and_delete():
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"email": "bad", "password": "longenough"}).status_code == 422
    assert c.post("/api/auth/register", json={"email": "a@b.co", "password": "short"}).status_code == 422
    tok = c.post("/api/auth/register", json={"email": "a@b.co", "password": "longenough"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert (
        c.post(
            "/api/auth/password", json={"old_password": "wrong", "new_password": "newpassword"}, headers=h
        ).status_code
        == 401
    )
    assert (
        c.post(
            "/api/auth/password",
            json={"old_password": "longenough", "new_password": "newpassword"},
            headers=h,
        ).status_code
        == 200
    )
    assert c.post("/api/auth/login", json={"email": "a@b.co", "password": "newpassword"}).status_code == 200
    assert c.request("DELETE", "/api/auth/me", json={"password": "newpassword"}, headers=h).status_code == 200
    assert c.post("/api/auth/login", json={"email": "a@b.co", "password": "newpassword"}).status_code == 401


def test_rate_limit():
    c = TestClient(app)
    c.post("/api/auth/register", json={"email": "r@b.co", "password": "longenough"})
    codes = [
        c.post("/api/auth/login", json={"email": "r@b.co", "password": "x"}).status_code for _ in range(9)
    ]
    assert codes[-1] == 429
