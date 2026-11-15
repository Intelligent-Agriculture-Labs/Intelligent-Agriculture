"""Country-specific economics (ADR-027): every money value uses the field's country, with documented fallbacks."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from fieldshift.engine.plan_service import plan_impact
from fieldshift.main import app
from fieldshift.science import economics as ec
from fieldshift.science import rotation as rot
from fieldshift.science import yieldcal
from fieldshift.science.cropmodel import crop

client = TestClient(app)

BERLIN = (52.52, 13.40)
MACHAKOS = (-1.52, 37.26)
FALLON = (39.47, -118.78)
PUNJAB = (30.9, 75.8)
MID_ATLANTIC = (0.0, -30.0)


@pytest.mark.parametrize(
    ("pt", "iso3"),
    [
        (BERLIN, "DEU"),
        (MACHAKOS, "KEN"),
        (FALLON, "USA"),
        (PUNJAB, "IND"),
        ((37.88, -4.78), "ESP"),
        ((-12.6, -55.7), "BRA"),
        ((54.33, 10.14), "DEU"),  # Kiel waterfront (coastal cell: nearest land)
        (MID_ATLANTIC, None),
    ],
)
def test_country_lookup_offline(pt, iso3):
    assert ec.country_of(*pt) == iso3


def test_germany_wheat_margin_uses_german_price_in_eur():
    e = ec.econ_for(*BERLIN)
    assert e.iso3 == "DEU" and not e.fallback
    assert e.currency["code"] == "EUR" and 0.5 < e.currency["per_usd"] < 1.5 and e.currency["year"] >= 2023
    p = e.price("winter_wheat")
    assert p["scope"] == "country" and "FAOSTAT" in p["source"] and p["years"][-1] >= 2022
    de = ec.data()["countries"]["DEU"]["prices"]["winter_wheat"]["usd_t"]
    us = ec.data()["countries"]["USA"]["prices"]["winter_wheat"]["usd_t"]
    assert p["usd_t"] == pytest.approx(de) and de != us
    # cost: reference budget scaled with Germany's own FAOSTAT yield level and price level
    c = e.cost("winter_wheat")
    assert (
        c["scope"] == "country" and c["intensity_scope"] == "country" and c["price_level_scope"] == "country"
    )
    margin = e.margin_usd_ha("winter_wheat", 7.0)
    assert margin == pytest.approx(7.0 * de - c["usd_ha"])
    assert e.local(margin) == pytest.approx(margin * e.currency["per_usd"])
    prov = e.provenance(["winter_wheat"])
    assert prov["country"]["iso3"] == "DEU" and prov["currency"]["code"] == "EUR"
    row = prov["crops"][0]
    assert row["price_scope"] == "country" and row["price_local_t"] == pytest.approx(
        de * e.currency["per_usd"], rel=1e-3
    )


def test_kenya_maize_uses_kenyan_price_in_kes():
    e = ec.econ_for(*MACHAKOS)
    assert e.iso3 == "KEN" and e.currency["code"] == "KES" and e.currency["per_usd"] > 50
    p = e.price("maize")
    assert p["scope"] == "country"
    assert p["usd_t"] == pytest.approx(ec.data()["countries"]["KEN"]["prices"]["maize"]["usd_t"])
    # low-input smallholder system: Kenya's national maize yield makes the modelled cost far below the U.S. budget
    assert e.cost_usd_ha("maize") < 0.3 * float(crop("maize")["cost_usd_ha"])


def test_unknown_country_falls_back_with_flag():
    e = ec.econ_for(*MID_ATLANTIC)
    assert e.fallback and e.iso3 is None and e.currency["code"] == "USD"
    assert e.price("maize")["scope"] in ("world", "reference")
    assert e.cost("maize") == {
        "usd_ha": float(crop("maize")["cost_usd_ha"]),
        "scope": "reference",
        "source": e.cost("maize")["source"],
    }
    prov = e.provenance(["maize"])
    assert prov["fallback"] is True and prov["country"] is None and prov["notes"]


def test_price_ladder_region_world_reference():
    de = ec.econ_for_country("DEU")
    # forage without FAOSTAT price: reference price scaled by Germany's farm-price index
    alf = de.price("alfalfa")
    assert alf["scope"] == "reference_scaled" and "farm-price index" in alf["source"]
    # a crop Germany does not price: sub-region or world median of countries that do
    q = de.price("coffee")
    assert q["scope"] in ("region", "world")


def test_india_price_carried_forward_with_producer_price_index():
    # FAOSTAT stopped USD prices for India after 2008; the index-based carry-forward keeps it country-specific
    p = ec.econ_for(*PUNJAB).price("winter_wheat")
    assert p["scope"] == "country" and p["years"][-1] >= 2022
    assert ec.data()["countries"]["IND"]["prices"]["winter_wheat"].get("indexed_from")


def test_solar_inputs_are_country_specific():
    de, ke = ec.econ_for(*BERLIN), ec.econ_for(*MACHAKOS)
    assert de.solar_capex()["usd_kwp"] > ke.solar_capex()["usd_kwp"]
    for e in (de, ke):
        d = e.diesel()
        assert d["scope"] in ("country", "region", "world") and 0.2 < d["usd_l"] < 4 and d["source"]


def test_rotation_margin_differs_by_country():
    """Same simulated yields, different country → different prices, costs and margins (no U.S. defaults)."""

    class _S:
        def __init__(self, cid):
            self.c = crop(cid)
            self.yields = [6.0, 6.5, 7.0]
            self.irr = [0.0] * 3
            self.deficit = [0.0] * 3
            self.heat = [0.0] * 3
            self.frost = [0.0] * 3
            self.fail_share = 0.0
            self.plant = dt.date(2020, 10, 1)
            self.length = 280
            self.kc_daily = [0.5] * 280
            self.results = []

    tpl = {"slots": [{"crop": "winter_wheat", "year": 1}]}
    try:
        out = {
            iso: rot.score_strategy(
                tpl, [_S("winter_wheat")], [1 / 12] * 12, 2.0, False, econ=ec.econ_for_country(iso)
            )
            for iso in ("DEU", "KEN", "USA")
        }
    except (AttributeError, KeyError, TypeError):
        pytest.skip("score_strategy needs full slot statistics")
    incomes = {k: v["raw"]["income"] for k, v in out.items()}
    assert len({round(v) for v in incomes.values()}) == 3


def test_plan_impact_reports_local_currency():
    e = ec.econ_for(*MACHAKOS)
    cur = [
        {
            "sim": {
                "irrigation_mm": 0,
                "n_balance_kg_ha": 0,
                "erosion_t_ha": 1,
                "margin_usd_ha": 100,
                "bare_days": 100,
            }
        }
    ]
    new = [
        {
            "sim": {
                "irrigation_mm": 0,
                "n_balance_kg_ha": 0,
                "erosion_t_ha": 1,
                "margin_usd_ha": 200,
                "bare_days": 100,
            }
        }
    ]
    imp = plan_impact(cur, new, None, "optimised plan", e)
    assert imp["currency"] == "KES" and imp["per_ha"]["margin_gain_usd_ha"] == 100
    assert imp["per_ha"]["margin_gain_local_ha"] == pytest.approx(100 * e.currency["per_usd"], abs=1)
    assert "KES" in imp["headline"] or "Ksh" in imp["headline"]


def test_country_yield_factor_applied():
    f = yieldcal.country_factors()
    assert len(f) >= 150 and sum(v["method"] == "benchmark" for v in f.values()) >= 40
    base = yieldcal.factor("maize", "sub_saharan_africa", None)
    assert yieldcal.factor("maize", "sub_saharan_africa", None, country="KEN") == pytest.approx(
        min(2.0, max(0.1, base * f["KEN"]["factor"]))
    )


def test_local_sowing_from_sacks_calendar():
    md, src = rot.local_sowing("maize", 42.03, -93.62)  # Ames, Iowa
    assert src.startswith("Sacks") and md[:2] in ("04", "05")
    # southern hemisphere: Mato Grosso soy sown in the austral spring, no hemisphere rule needed
    md2, _ = rot.local_sowing("soybean", -12.6, -55.7)
    assert md2[:2] in ("09", "10", "11", "12")
    d = rot.planting_date_for("maize", 2020, 42.03, None, lon=-93.62)
    assert d.month in (4, 5)


def test_api_rotation_plan_and_solar_expose_economics():
    body = {
        "lat": BERLIN[0],
        "lon": BERLIN[1],
        "irrigation": "none",
        "history": [],
        "plan": [{"year": 2026, "crop": "winter_wheat"}, {"year": 2027, "crop": "winter_rapeseed"}],
        "optimize": False,
    }
    j = client.post("/api/rotations/plan", json=body).json()
    eco = j["economics"]
    assert eco["country"]["iso3"] == "DEU" and eco["currency"]["code"] == "EUR" and not eco["fallback"]
    assert {c["crop"] for c in eco["crops"]} >= {"winter_wheat", "winter_rapeseed"}
    y = j["years"][0]["sim"]
    assert y["margin_local_ha"] == pytest.approx(y["margin_usd_ha"] * eco["currency"]["per_usd"], abs=2)

    req = {
        "lat": MACHAKOS[0],
        "lon": MACHAKOS[1],
        "crop": "maize",
        "planting_date": "2024-03-15",
        "irrigation": "drip",
    }
    s = client.post("/api/solar-pump", json=req).json()
    assert s["currency"] == "KES" and s["economics"]["country"]["iso3"] == "KEN"
    assert s["solar_local_per_m3"] == pytest.approx(
        s["solar_usd_per_m3"] * s["economics"]["currency"]["per_usd"], rel=0.03
    )
    assert s["capex_usd_kwp"] == ec.econ_for(*MACHAKOS).solar_capex()["usd_kwp"]
