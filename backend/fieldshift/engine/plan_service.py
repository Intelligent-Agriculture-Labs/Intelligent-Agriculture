"""POST /api/rotations/plan — per-field multi-year rotation plan check, suggestions and optimisation."""

from __future__ import annotations

import datetime as dt
import threading
from typing import Any

import numpy as np

from ..data.sources import source_ref
from ..science import climate as climmod
from ..science import rotation as rot
from ..science import rotation_plan as rp
from ..science.cropmodel import crop, crops
from .context import build

_cache: dict[tuple[Any, ...], tuple[dict[str, dict[str, Any]], list[str]]] = {}
_lock = threading.Lock()
DEFAULT_PRI = {"water": 0.2, "soil": 0.2, "income": 0.25, "pests": 0.25, "risk": 0.1}


def _crop_stats(
    lat: float, lon: float, today: dt.date, irrigation: str, alloc: float | None, needed: set[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Simulate every crop (or the needed ones) over 15 seasons at this field; returns stats + climate-feasible main crops."""
    key = (round(lat, 3), round(lon, 3), today.isoformat(), irrigation, alloc)
    with _lock:
        hit = _cache.get(key)
    if hit and needed <= set(hit[0]):
        return hit
    ctx = build(lat, lon, today)
    w = ctx.weather
    pd_ = w.dates[: ctx.idx(today) + 1]
    normals = climmod.monthly_normals(pd_, w.tmax, w.tmin, w.rain, w.et0, 1991, 2020)
    onset = rot.rainy_onset(normals) if abs(lat) < 20 else None
    med = rot.is_mediterranean(normals, lat)
    irrigated = irrigation != "none"
    strategy = "allocation" if (irrigated and alloc) else ("full" if irrigated else "rainfed")
    last_full = today.year - 2
    years = list(range(last_full - 14, last_full + 1))
    stats: dict[str, dict[str, Any]] = dict(hit[0]) if hit else {}
    feasible: list[str] = list(hit[1]) if hit else []
    todo = [c for c in crops() if c not in stats] if not hit else [c for c in needed if c not in stats]
    for cid in todo:
        c = crop(cid)
        try:
            slot = rot.evaluate_slot(
                cid,
                w,
                years,
                lat,
                onset,
                ctx.taw_per_m,
                strategy,
                irrigation if irrigated else "sprinkler",
                alloc,
                None,
                None,
                med,
            )
        except Exception:  # a crop with incomplete parameters must not break the planner
            continue
        issue = None
        if slot.n < 0.6 * len(years):
            issue = "Not enough complete seasons in the weather record for this crop here."
        elif (
            c["type"] not in ("perennial", "cover")
            and slot.frost
            and np.mean([f > 0 for f in slot.frost]) > 0.3
        ):
            issue = f"Damaging frost during the season in {100 * np.mean([f > 0 for f in slot.frost]):.0f} % of the last {len(years)} years."
        elif (
            c["typical_yield_t_ha"] > 0
            and slot.yields
            and np.median(slot.yields) < 0.35 * c["typical_yield_t_ha"]
        ):
            issue = (
                "The local season is too short, cold or dry: simulated yields are below a third of normal."
            )
        stats[cid] = rp.slot_summary(slot, c, issue, cid)
        if issue is None and c["type"] != "cover":
            feasible.append(cid)
    with _lock:
        _cache[key] = (stats, sorted(set(feasible)))
        if len(_cache) > 16:
            _cache.pop(next(iter(_cache)))
    return stats, sorted(set(feasible))


def _field_rkls(req: dict[str, Any], first_crop: str) -> float | None:
    if not req.get("polygon"):
        return None
    try:
        from . import maps

        t = maps.terrain_api(
            {"lat": req["lat"], "lon": req["lon"], "crop": first_crop, "polygon": req.get("polygon")}
        )
        ero = next(lyr for lyr in t["layers"] if lyr["id"] == "erosion")
        c = crop(first_crop)
        cf = (
            0.02
            if c["type"] == "perennial"
            else (0.2 if first_crop in ("winter_wheat", "barley", "triticale_forage") else 0.38)
        )
        return float(ero["stats"]["mean"]) / cf
    except Exception:
        return None


SPECIALTY_FAMILIES = {
    "Solanaceae",
    "Cucurbitaceae",
    "Amaryllidaceae",
    "Apiaceae",
    "Convolvulaceae",
    "Dioscoreaceae",
}


def is_specialty(cid: str) -> bool:
    """Vegetables, roots & tubers: high-value but market-, labour- and machinery-dependent."""
    c = crop(cid)
    return (
        bool(c.get("fresh_factor"))
        or c.get("family") in SPECIALTY_FAMILIES
        or cid in {"cassava", "sugarcane", "cabbage", "lettuce"}
    )


def farm_type_filter(cands: list[str], own: list[str]) -> list[str]:
    """Only propose perennial forages / specialty crops if the farm already grows that kind of crop."""
    grows_perennial = any(crop(c)["type"] == "perennial" for c in own)
    grows_specialty = any(is_specialty(c) for c in own)
    return [
        c
        for c in cands
        if (crop(c)["type"] != "perennial" or grows_perennial)
        and (not is_specialty(c) or grows_specialty or c in own)
    ]


def plan_api(req: dict[str, Any]) -> dict[str, Any]:
    lat, lon = float(req["lat"]), float(req["lon"])
    today = dt.date.fromisoformat(req["as_of"]) if req.get("as_of") else dt.date.today()
    history = [h for h in (req.get("history") or []) if h.get("crop") in crops()]
    plan = [p for p in (req.get("plan") or []) if p.get("crop") in crops()]
    if not plan:
        raise ValueError("plan must contain at least one known crop")
    pri = {**DEFAULT_PRI, **(req.get("priorities") or {})}
    own = [x["crop"] for x in [*history, *plan]]
    irrigation = req.get("irrigation", "none")
    alloc = req.get("water_allocation_mm")
    needed = (
        {h["crop"] for h in history}
        | {p["crop"] for p in plan}
        | {p.get("cover_crop") for p in plan if p.get("cover_crop")}
    )
    stats, feasible = _crop_stats(lat, lon, today, irrigation, alloc, {n for n in needed if n})
    for n in needed:
        if n and n not in stats:
            stats2, _ = _crop_stats(lat, lon, today, irrigation, alloc, {n})
            stats.update(stats2)
    field = {
        "irrigated": irrigation != "none",
        "water_allocation_mm": alloc,
        "r_k_ls": _field_rkls(req, plan[0]["crop"]),
    }
    years, summary = rp.evaluate_plan(history, plan, stats, field, pri)

    # single-change suggestions for years with issues
    base = summary["score"]
    sugg: list[dict[str, Any]] = []
    ranked_candidates = sorted(
        farm_type_filter(feasible, own),
        key=lambda c: -stats[c]["yield_median"] * float(crop(c).get("price_usd_t", 0)),
    )[:20]
    for idx, y in enumerate(years):
        if y["verdict"] == "good":
            continue
        best: tuple[float, str] | None = None
        for alt in ranked_candidates:
            if alt == y["crop"]:
                continue
            trial = [dict(p) for p in plan]
            trial[idx] = {**trial[idx], "crop": alt}
            _, s2 = rp.evaluate_plan(history, trial, stats, field, pri)
            if best is None or s2["score"] > best[0]:
                best = (s2["score"], alt)
        if best and best[0] > base + 1:
            trial = [dict(p) for p in plan]
            trial[idx] = {**trial[idx], "crop": best[1]}
            fixed = [i["title"] for i in y["issues"] if i["severity"] != "info"][:2]
            sugg.append(
                {
                    "title": f"{y['year']}: grow {crop(best[1])['name']} instead of {crop(y['crop'])['name']}",
                    "explanation": ("This avoids: " + "; ".join(fixed) + ".")
                    if fixed
                    else "Better fit for this field.",
                    "plan": trial,
                    "score": round(best[0], 1),
                    "score_gain": round(best[0] - base, 1),
                }
            )
        if any(i["id"] == "bare_soil" for i in y["issues"]) and not plan[idx].get("cover_crop"):
            nxt = plan[idx + 1]["crop"] if idx + 1 < len(plan) else None
            cov = rp.best_cover(y["crop"], nxt, {c for c in rp.COVER_CANDIDATES if c in crops()})
            if cov:
                trial = [dict(p) for p in plan]
                trial[idx] = {**trial[idx], "cover_crop": cov}
                _, s2 = rp.evaluate_plan(history, trial, stats, field, pri)
                sugg.append(
                    {
                        "title": f"{y['year']}: sow {crop(cov)['name']} after harvest",
                        "explanation": "Keeps the soil covered over the bare period, adds organic matter and (legume mixes) nitrogen.",
                        "plan": trial,
                        "score": round(s2["score"], 1),
                        "score_gain": round(s2["score"] - base, 1),
                    }
                )
    sugg = sorted([s for s in sugg if s["score_gain"] > 0], key=lambda s: -s["score_gain"])[:4]

    optimized = None
    if req.get("optimize", True):
        cands = sorted(
            feasible,
            key=lambda c: (
                -(
                    stats[c]["yield_median"] * float(crop(c).get("price_usd_t", 0))
                    - float(crop(c).get("cost_usd_ha", 0))
                )
            ),
        )[:16]
        # always allow the farmer's own crops as candidates
        cands = list(dict.fromkeys([*[p["crop"] for p in plan], *cands]))
        # respect the farm type: perennial forage / specialty crops only if the farm already grows that kind (market, machinery, livestock)
        cands = farm_type_filter(cands, own)
        best_plan, best_score = rp.optimize(
            history, len(plan), int(plan[0]["year"]), cands, stats, field, pri
        )
        if best_score > base + 0.5:
            changed = [
                f"{p['year']}: {crop(p['crop'])['name']}"
                for p, q in zip(best_plan, plan, strict=True)
                if p["crop"] != q["crop"]
            ]
            optimized = {
                "plan": best_plan,
                "score": round(best_score, 1),
                "explanation": "Searched thousands of crop sequences that fit this field's climate, scoring each year for disease breaks, "
                "nitrogen, soil cover, water and income with your priorities. Changes: "
                + (", ".join(changed) or "cover crops only")
                + ".",
            }

    n_prob = sum(y["verdict"] == "problem" for y in years)
    n_caut = sum(y["verdict"] == "caution" for y in years)
    if n_prob:
        headline = f"{n_prob} year(s) need a change — see the red years."
    elif n_caut:
        headline = f"Workable plan — {n_caut} year(s) could be better."
    else:
        headline = "Good plan — no biological or water problems found."
    if optimized and optimized["score"] - base >= 5:
        headline += f" The optimised plan scores {optimized['score']:.0f} vs {base:.0f}."
    summary["headline"] = headline
    return {
        "years": years,
        "summary": summary,
        "suggestions": sugg,
        "optimized": optimized,
        "crops_available": feasible,
        "sources": [
            source_ref("nasa_power", "live"),
            source_ref("srtm", "live"),
            source_ref("soilgrids", "live"),
        ],
        "disclaimer": "Rotation rules come from published agronomic research (see Rotation science); yields and water use are simulated with NASA "
        "weather at your field. Local conditions, varieties and markets differ — check with your adviser before big changes.",
    }
