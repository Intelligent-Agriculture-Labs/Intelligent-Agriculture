"""Active fires near the field (NASA FIRMS) and the 'don't burn crop residue' card for burning regions."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..data import firms
from ..science.cropmodel import crop
from .messages import t

CONFIG = Path(__file__).resolve().parents[1] / "config"
NEAR_KM = 10.0  # fire risk to the field
SMOKE_KM = 50.0  # smoke / air quality
COMPASS = {
    "en": {"N": "N", "NE": "NE", "E": "E", "SE": "SE", "S": "S", "SW": "SW", "W": "W", "NW": "NW"},
    "es": {"N": "N", "NE": "NE", "E": "E", "SE": "SE", "S": "S", "SW": "SO", "W": "O", "NW": "NO"},
    "fr": {"N": "N", "NE": "NE", "E": "E", "SE": "SE", "S": "S", "SW": "SO", "W": "O", "NW": "NO"},
    "de": {"N": "N", "NE": "NO", "E": "O", "SE": "SO", "S": "S", "SW": "SW", "W": "W", "NW": "NW"},
    "sw": {"N": "kaskazini", "NE": "kaskazini-mashariki", "E": "mashariki", "SE": "kusini-mashariki", "S": "kusini", "SW": "kusini-magharibi", "W": "magharibi", "NW": "kaskazini-magharibi"},
    "hi": {"N": "उत्तर", "NE": "उत्तर-पूर्व", "E": "पूर्व", "SE": "दक्षिण-पूर्व", "S": "दक्षिण", "SW": "दक्षिण-पश्चिम", "W": "पश्चिम", "NW": "उत्तर-पश्चिम"},
}


@lru_cache
def residue_cfg() -> dict[str, Any]:
    with open(CONFIG / "residue_burning.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def burning_region(lat: float, lon: float) -> tuple[str, dict[str, Any]] | None:
    for rid, r in residue_cfg()["regions"].items():
        w, s, e, n = r["bbox"]
        if s <= lat <= n and w <= lon <= e:
            return rid, r
    return None


def residue_benefits(cid: str, yield_t_ha: float) -> dict[str, float] | None:
    """Residue left after harvest and what burning it destroys (per ha)."""
    conf = residue_cfg()
    r = conf["residue"].get(cid)
    if r is None:
        return None
    res = r["rgr"] * yield_t_ha
    loss = conf["burn_loss"]
    c_t = res * r["c_frac"]
    return {
        "residue_t_ha": res,
        "n_lost_kg_ha": res * r["n_kg_t"] * loss["n"],
        "p_lost_kg_ha": res * r["p_kg_t"] * loss["p"],
        "k_lost_kg_ha": res * r["k_kg_t"] * loss["k"],
        "s_lost_kg_ha": res * r["s_kg_t"] * loss["s"],
        "c_t_ha": c_t,
        "c_lost_t_ha": c_t * loss["c"],
        "co2_t_ha": c_t * loss["c"] * 44.0 / 12.0,
        "soc_gain_t_ha": c_t * conf["humification"],
    }


def _crop_word(name: str, lang: str) -> str:
    w = name.split(" (")[0]
    return w if lang == "de" else w.lower()


def _months_near(today: dt.date, months: list[int], ahead: int = 1) -> bool:
    """True if `today` is in a burning month or up to `ahead` months before one."""
    cand = {((today.month - 1 + k) % 12) + 1 for k in range(ahead + 1)}
    return bool(cand & set(months))


def fire_cards(
    lat: float,
    lon: float,
    cid: str,
    today: dt.date,
    lang: str,
    why: Any,
    fires_res: firms.FireResult | None = None,
    statuses: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if fires_res is None:
        try:
            fires_res = firms.nearby_fires(lat, lon, today, SMOKE_KM)
        except Exception:  # optional layer must never break advice
            fires_res = None
    if statuses is not None and fires_res is not None and fires_res.status not in ("off",):
        statuses["firms"] = fires_res.status
    fires = fires_res.fires if fires_res else []
    near = [f for f in fires if f.km <= NEAR_KM]
    src_note = f"NASA FIRMS ({fires_res.mode}, {fires_res.status})" if fires_res else "NASA FIRMS"
    caveats_f = [
        "A detection is a 375 m (VIIRS) or 1 km (MODIS) pixel containing an active fire at satellite overpass; "
        "small or short fires and fires under thick cloud or smoke can be missed.",
        "Detections are not checked on the ground; low-confidence detections are excluded.",
    ]
    if fires_res and fires_res.note:
        caveats_f.append(fires_res.note)
    if fires and fires_res is not None:
        nearest = fires[0]
        km = NEAR_KM if near else SMOKE_KM
        n = len(near) if near else len(fires)
        risk = "high" if nearest.km <= 2 else "moderate" if (near or len(fires) >= 20) else "low"
        sats = sorted({f.satellite for f in fires})
        steps = [
            f"{src_note}: {len(fires)} active-fire detections within {SMOKE_KM:.0f} km between "
            f"{fires_res.start.isoformat()} and {fires_res.end.isoformat()} (satellites: {', '.join(sats)}).",
            f"{len(near)} within {NEAR_KM:.0f} km of the field; nearest {nearest.km:.1f} km {firms.compass(nearest.bearing)} "
            f"on {nearest.date.isoformat()} {nearest.time_utc[:2]}:{nearest.time_utc[2:]} UTC (fire radiative power {nearest.frp_mw:.1f} MW, {nearest.confidence} confidence).",
            f"Total fire radiative power within {SMOKE_KM:.0f} km: {sum(f.frp_mw for f in fires):.0f} MW — many fires upwind mean smoke and poor air (PM2.5).",
            "Risk to the field rises with dry fuel (stubble, dry grass, hay) and wind towards the field.",
        ]
        out.append(
            {
                "id": "fire_nearby",
                "category": "weather",
                "risk": risk,
                "icon": "flame-outline",
                "title": t(
                    "fire_near_title",
                    lang,
                    n=n,
                    km=round(km),
                    d=f"{nearest.km:.1f}",
                    dir=COMPASS.get(lang, COMPASS["en"])[firms.compass(nearest.bearing)],
                ),
                "detail": t("fire_near_detail", lang),
                "due": today.isoformat(),
                "amount": None,
                "why": why(
                    f"NASA satellites detected {len(fires)} active fires within {SMOKE_KM:.0f} km in the last 48 hours; the nearest is {nearest.km:.1f} km away.",
                    steps,
                    [],
                    "Distance to NASA FIRMS active-fire detections (VIIRS 375 m / MODIS 1 km, Schroeder et al. 2014; Giglio et al. 2016)",
                    "fires",
                    0.7 if fires_res.status in ("live", "cache") else 0.5,
                    "Satellite detections are reliable for flaming fires; they say nothing about wind direction at your field.",
                    caveats_f,
                    ["firms"],
                ),
            }
        )
    # ---- residue burning advice
    reg = burning_region(lat, lon)
    if reg is None:
        return out
    rid, r = reg
    months = r["crops"].get(cid)
    if months is None or not (_months_near(today, months) or near):
        return out
    c = crop(cid)
    b = residue_benefits(cid, float(c.get("typical_yield_t_ha") or 5.0))
    if b is None:
        return out
    risk = "high" if (near and _months_near(today, months, 0)) else "moderate"
    steps = [
        f"Your field is in a residue-burning region: {r['name']} (burning peaks in months {', '.join(str(m) for m in months)}; {r['ref']}).",
        f"Typical {c['name']} yield {c.get('typical_yield_t_ha')} t/ha × residue-to-grain ratio {residue_cfg()['residue'][cid]['rgr']} "
        f"→ ~{b['residue_t_ha']:.1f} t/ha of residue holding {b['c_t_ha']:.1f} t carbon.",
        f"Burning it loses ~{b['n_lost_kg_ha']:.0f} kg N, {b['p_lost_kg_ha']:.1f} kg P, {b['k_lost_kg_ha']:.0f} kg K and {b['s_lost_kg_ha']:.1f} kg S per ha "
        f"(≈90% of N, 25% of P, 20% of K; Dobermann & Fairhurst 2002) and releases ~{b['co2_t_ha']:.1f} t CO₂/ha plus smoke (PM2.5).",
        f"Kept as mulch or incorporated, ~{b['soc_gain_t_ha']:.2f} t C/ha is added to soil organic carbon in the first year (≈12% humification; Powlson et al. 2008), "
        "improving water infiltration and soil structure year on year.",
        "Options: sow the next crop directly into the standing stubble (Happy Seeder / Super Seeder; Sidhu et al. 2015), chop and spread the straw "
        "(Super-SMS on the combine), or incorporate with a mulcher + disc 2–3 weeks before sowing. Shyamsundar et al. (2019, Science) found Happy Seeder sowing the most profitable option.",
    ]
    if fires:
        steps.append(f"NASA FIRMS currently shows {len(fires)} fires within {SMOKE_KM:.0f} km — burning is happening around you now.")
    out.append(
        {
            "id": "residue_no_burn",
            "category": "planning",
            "risk": risk,
            "icon": "leaf-outline",
            "title": t("residue_title", lang, crop=_crop_word(c["name"], lang)),
            "detail": t(
                "residue_detail",
                lang,
                res=f"{b['residue_t_ha']:.1f}",
                n=round(b["n_lost_kg_ha"]),
                c=f"{b['c_lost_t_ha']:.1f}",
            ),
            "due": None,
            "amount": {"value": round(b["n_lost_kg_ha"]), "unit": "kg N/ha"},
            "why": why(
                f"Burning {c['name'].split(' (')[0].lower()} residue destroys nitrogen, sulphur and carbon your soil needs; mulching or incorporating keeps them.",
                steps,
                [],
                "Residue nutrient balance (residue-to-grain ratio × nutrient content × burning loss)",
                "residue-burning",
                0.55,
                "Residue amount scales with your actual yield; nutrient contents are literature averages.",
                [
                    "Uses a typical yield for the crop; enter your own yield for a sharper estimate.",
                    "Burning bans and machinery subsidies (e.g. CRM scheme in India) differ by state.",
                ],
                ["firms"] if fires else ["nasa_power"],
            ),
        }
    )
    return out
