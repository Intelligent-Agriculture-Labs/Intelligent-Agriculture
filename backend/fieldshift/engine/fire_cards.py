"""Active fires near the field (NASA FIRMS) and the 'don't burn crop residue' card for burning regions."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..data import firms
from ..science.cropmodel import crop
from .messages import crop_name, crop_short, has, month_name, t, word

CONFIG = Path(__file__).resolve().parents[1] / "config"
NEAR_KM = 10.0  # fire risk to the field
SMOKE_KM = 50.0  # smoke / air quality
COMPASS = {
    "en": {"N": "N", "NE": "NE", "E": "E", "SE": "SE", "S": "S", "SW": "SW", "W": "W", "NW": "NW"},
    "es": {"N": "N", "NE": "NE", "E": "E", "SE": "SE", "S": "S", "SW": "SO", "W": "O", "NW": "NO"},
    "fr": {"N": "N", "NE": "NE", "E": "E", "SE": "SE", "S": "S", "SW": "SO", "W": "O", "NW": "NO"},
    "de": {"N": "N", "NE": "NO", "E": "O", "SE": "SO", "S": "S", "SW": "SW", "W": "W", "NW": "NW"},
    "sw": {
        "N": "kaskazini",
        "NE": "kaskazini-mashariki",
        "E": "mashariki",
        "SE": "kusini-mashariki",
        "S": "kusini",
        "SW": "kusini-magharibi",
        "W": "magharibi",
        "NW": "kaskazini-magharibi",
    },
    "hi": {
        "N": "उत्तर",
        "NE": "उत्तर-पूर्व",
        "E": "पूर्व",
        "SE": "दक्षिण-पूर्व",
        "S": "दक्षिण",
        "SW": "दक्षिण-पश्चिम",
        "W": "पश्चिम",
        "NW": "उत्तर-पश्चिम",
    },
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


def _crop_word(cid: str, lang: str) -> str:
    w = crop_short(cid, lang)
    return w if lang == "de" else w.lower()


# English notes from data/firms.py -> message keys
_FIRMS_NOTES = {
    "Keyless FIRMS feed covers the last 24 h only; add a free MAP_KEY for 48 h and MODIS.": "fire_note_keyless",  # i18n: ok
    "Recorded FIRMS detections (demo data).": "fire_note_demo",  # i18n: ok
}


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
    src_note = f"NASA FIRMS ({fires_res.mode}, {fires_res.status})" if fires_res else "NASA FIRMS"  # i18n: ok
    caveats_f = [t("fire_caveat_pixel", lang), t("fire_caveat_ground", lang)]
    if fires_res and fires_res.note:
        caveats_f.append(
            t(_FIRMS_NOTES[fires_res.note], lang) if fires_res.note in _FIRMS_NOTES else fires_res.note
        )
    if fires and fires_res is not None:
        nearest = fires[0]
        km = NEAR_KM if near else SMOKE_KM
        n = len(near) if near else len(fires)
        risk = "high" if nearest.km <= 2 else "moderate" if (near or len(fires) >= 20) else "low"
        sats = sorted({f.satellite for f in fires})
        steps = [
            t(
                "fire_step_count",
                lang,
                src=src_note,
                n=len(fires),
                km=SMOKE_KM,
                start=fires_res.start.isoformat(),
                end=fires_res.end.isoformat(),
                sats=", ".join(sats),
            ),
            t(
                "fire_step_nearest",
                lang,
                n=len(near),
                km=NEAR_KM,
                d=nearest.km,
                dir=COMPASS.get(lang, COMPASS["en"])[firms.compass(nearest.bearing)],
                date=nearest.date.isoformat(),
                time=f"{nearest.time_utc[:2]}:{nearest.time_utc[2:]}",
                frp=nearest.frp_mw,
                conf=word("fire_conf", str(nearest.confidence), lang),
            ),
            t("fire_step_frp", lang, km=SMOKE_KM, mw=sum(f.frp_mw for f in fires)),
            t("fire_step_fuel", lang),
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
                    t("fire_sum", lang, n=len(fires), km=SMOKE_KM, d=nearest.km),
                    steps,
                    [],
                    t("model_fire", lang),
                    "fires",
                    0.7 if fires_res.status in ("live", "cache") else 0.5,
                    t("fire_note", lang),
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
    region = t(f"residue_region_{rid}", lang) if has(f"residue_region_{rid}") else r["name"]
    steps = [
        t(
            "res_step_region",
            lang,
            region=region,
            months=", ".join(month_name(m, lang) for m in months),
            ref=r["ref"],
        ),
        t(
            "res_step_amount",
            lang,
            crop=crop_name(cid, lang, c["name"]),
            y=c.get("typical_yield_t_ha"),
            rgr=residue_cfg()["residue"][cid]["rgr"],
            res=b["residue_t_ha"],
            c=b["c_t_ha"],
        ),
        t(
            "res_step_loss",
            lang,
            n=b["n_lost_kg_ha"],
            p=b["p_lost_kg_ha"],
            k=b["k_lost_kg_ha"],
            s=b["s_lost_kg_ha"],
            co2=b["co2_t_ha"],
        ),
        t("res_step_soc", lang, soc=b["soc_gain_t_ha"]),
        t("res_step_options", lang),
    ]
    if fires:
        steps.append(t("res_step_fires_now", lang, n=len(fires), km=SMOKE_KM))
    out.append(
        {
            "id": "residue_no_burn",
            "category": "planning",
            "risk": risk,
            "icon": "leaf-outline",
            "title": t("residue_title", lang, crop=_crop_word(cid, lang)),
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
                t("res_sum", lang, crop=_crop_word(cid, lang)),
                steps,
                [],
                t("model_residue", lang),
                "fires",
                0.55,
                t("res_note", lang),
                [t("res_caveat_yield", lang), t("res_caveat_bans", lang)],
                ["firms"] if fires else ["nasa_power"],
            ),
        }
    )
    return out
