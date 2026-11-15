"""Every supported language has every farmer-facing text (app locales + backend catalogs), no farmer-facing English
is hard-coded in backend Python or app .tsx, and the API answers in the requested language.

The checks themselves live in scripts/check_i18n.py (also runnable on its own)."""

import importlib.util
import string
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fieldshift.engine import messages as msg
from fieldshift.main import app

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_i18n", ROOT / "scripts" / "check_i18n.py")
assert _spec and _spec.loader
check = importlib.util.module_from_spec(_spec)
sys.modules["check_i18n"] = check
_spec.loader.exec_module(check)

client = TestClient(app)
LANGS = ["en", "es", "fr", "sw", "hi", "de"]
NON_EN = LANGS[1:]
FIELD = {
    "lat": 39.47,
    "lon": -118.78,
    "crop": "alfalfa",
    "planting_date": "2024-03-15",
    "irrigation": "flood",
}


def test_supported_languages_agree():
    assert list(msg.LANGS) == LANGS == list(check.LANGS)
    import typing

    from fieldshift.main import Lang

    assert sorted(typing.get_args(Lang)) == sorted(LANGS)
    assert sorted(p.stem for p in check.APP_LOCALES.glob("*.json")) == sorted(LANGS)


@pytest.mark.parametrize("name", list(check.CHECKS))
def test_checker_finds_nothing(name):
    errs = check.CHECKS[name]()
    assert errs == [], f"{len(errs)} i18n problem(s):\n" + "\n".join(errs[:40])


def _dummy_kwargs(tpl: str) -> dict[str, object]:
    kw: dict[str, object] = {}
    for _, field, spec, _ in string.Formatter().parse(tpl):
        if field:
            kw[field] = 1.5 if spec and spec[-1] in "fgde%" else "x"
    return kw


def test_every_template_formats_in_every_language():
    """Format specs ({x:.0f}) must stay valid in every translation (a broken one would crash an API call)."""
    bad = []
    for key, node in msg._messages().items():
        if not isinstance(node, dict) or "en" not in node or not isinstance(node["en"], str):
            continue
        kw = _dummy_kwargs(node["en"])
        for lg in LANGS:
            try:
                msg.t(key, lg, **kw)
            except (KeyError, ValueError, IndexError) as e:
                bad.append(f"{key}[{lg}]: {e!r}")
    assert bad == []


def test_crop_names_cover_every_crop_and_language():
    crops = client.get("/api/crops").json()
    for c in crops:
        assert set(c["names"]) == set(LANGS), c["id"]
        assert c["names"]["en"] == c["name"]
    assert crops[0]["names"]["de"] != crops[0]["names"]["en"] or crops[0]["id"] == "quinoa"


def test_satellite_results_are_localised_when_served():
    en = "Vigour differs by 0.12 NDVI between the best (40 % of the field) and the weakest zone (20 %)."
    de = msg.localize_text(en, "sat_", "de")
    assert de.startswith("Die Wüchsigkeit") and "0.12" in de and "40" in de
    assert msg.localize_text("unknown text", "sat_", "fr") == "unknown text"


def _texts(a: dict) -> list[str]:
    out = []
    for c in a["cards"]:
        out += [c["title"], c["detail"], c["why"]["summary"], *c["why"]["steps"], *c["why"]["caveats"]]
        out.append(c["why"]["model"])
    return out


@pytest.mark.parametrize("lang", NON_EN)
def test_advice_why_is_translated(lang):
    en = client.post("/api/advice", json={**FIELD, "lang": "en"}).json()
    other = client.post("/api/advice", json={**FIELD, "lang": lang}).json()
    assert [c["id"] for c in en["cards"]] == [c["id"] for c in other["cards"]]
    te, to = _texts(en), _texts(other)
    # numbers, ids and citations are shared; the sentences around them must not be
    same = [a for a, b in zip(te, to, strict=True) if a == b and len(a) > 25]
    assert not same, same[:5]
    assert other["drought"]["label"] != en["drought"]["label"]


@pytest.mark.parametrize("lang", NON_EN)
def test_rotations_climate_simulate_planner_translated(lang):
    rot = {
        "lat": 39.47,
        "lon": -118.78,
        "current_rotation": ["alfalfa", "alfalfa", "alfalfa"],
        "irrigation": "flood",
    }
    e = client.post("/api/rotations", json={**rot, "lang": "en"}).json()
    o = client.post("/api/rotations", json={**rot, "lang": lang}).json()
    assert e["disclaimer"] != o["disclaimer"]
    assert e["strategies"][0]["name"] != o["strategies"][0]["name"]
    assert e["strategies"][0]["metrics"][0]["label"] != o["strategies"][0]["metrics"][0]["label"]
    ce = client.get("/api/climate", params={"lat": 39.47, "lon": -118.78, "lang": "en"}).json()
    co = client.get("/api/climate", params={"lat": 39.47, "lon": -118.78, "lang": lang}).json()
    assert ce["metrics"][0]["label"] != co["metrics"][0]["label"]
    assert ce["metrics"][0]["unit"] == co["metrics"][0]["unit"]  # wire units stay language-neutral
    sim = {"lat": 39.47, "lon": -118.78, "crop": "maize", "planting_date": "2024-05-01", "years": 5}
    se = client.post("/api/simulate", json={**sim, "lang": "en"}).json()
    so = client.post("/api/simulate", json={**sim, "lang": lang}).json()
    assert se["why"]["summary"] != so["why"]["summary"]
    pl = {
        "lat": 39.47,
        "lon": -118.78,
        "crop": "maize",
        "planting_date": "2024-05-01",
        "irrigation": "sprinkler",
    }
    pe = client.post("/api/planner", json={**pl, "lang": "en"}).json()
    po = client.post("/api/planner", json={**pl, "lang": lang}).json()
    assert pe["why"] != po["why"] and pe["operations"][0]["label"] != po["operations"][0]["label"]


@pytest.mark.parametrize("lang", NON_EN)
def test_rotation_plan_translated(lang):
    body = {
        "lat": 39.47,
        "lon": -118.78,
        "irrigation": "flood",
        "history": [{"year": 2023, "crop": "potato"}],
        "plan": [{"year": 2024, "crop": "potato"}, {"year": 2025, "crop": "winter_wheat"}],
        "optimize": False,
    }
    e = client.post("/api/rotations/plan", json={**body, "lang": "en"}).json()
    o = client.post("/api/rotations/plan", json={**body, "lang": lang}).json()
    assert e["summary"]["headline"] != o["summary"]["headline"]
    assert e["disclaimer"] != o["disclaimer"]
    ie = [i["title"] for y in e["years"] for i in y["issues"]]
    io = [i["title"] for y in o["years"] for i in y["issues"]]
    assert ie and len(ie) == len(io) and all(a != b for a, b in zip(ie, io, strict=True))
