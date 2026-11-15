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
from ..science.economics import econ_for
from .context import build
from .messages import crop_name, t

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
                lon,
            )
        except Exception:  # a crop with incomplete parameters must not break the planner
            continue
        issue = (
            None  # message key (config/messages/rotation_plan.yaml), translated when the plan is evaluated
        )
        issue_kw: dict[str, Any] = {}
        if slot.n < 0.6 * len(years):
            issue = "rp_feas_few_seasons"
        elif (
            c["type"] not in ("perennial", "cover")
            and slot.frost
            and np.mean([f > 0 for f in slot.frost]) > 0.3
        ):
            issue = "rp_feas_frost"
            issue_kw = {"pct": 100 * float(np.mean([f > 0 for f in slot.frost])), "n": len(years)}
        elif (
            c["typical_yield_t_ha"] > 0
            and slot.yields
            and np.median(slot.yields) < 0.35 * c["typical_yield_t_ha"] * w.yield_factor(cid, irrigated)
        ):
            issue = "rp_feas_unfit"
        stats[cid] = rp.slot_summary(slot, c, issue, cid, issue_kw)
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

        ter = maps.terrain_api(
            {"lat": req["lat"], "lon": req["lon"], "crop": first_crop, "polygon": req.get("polygon")}
        )
        ero = next(lyr for lyr in ter["layers"] if lyr["id"] == "erosion")
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


def cropping_system(lat: float, med: bool, annual_p: float, irrigated: bool) -> str:
    if abs(lat) < 23.5:
        return "tropical"
    if med:
        return "mediterranean"
    if annual_p < 350:
        return "arid_irrigated"
    return "temperate"


def regional_filter(cands: list[str], own: list[str], system: str) -> list[str]:
    allowed = set(rot.rotation_config().get("cropping_systems", {}).get(system, [])) | set(own)
    return [c for c in cands if c in allowed] if allowed else cands


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


CO2E_PER_KG_N = (
    0.01 * 44 / 28 * 273
)  # IPCC 2019 EF1 direct N2O × GWP100 (AR6) = 4.29 kg CO2e per kg N not applied


def _area_ha(poly: list[list[float]] | None) -> float | None:
    if not poly or len(poly) < 3:
        return None
    lat0 = np.radians(np.mean([p[1] for p in poly]))
    xs = [np.radians(p[0]) * 6371000 * np.cos(lat0) for p in poly]
    ys = [np.radians(p[1]) * 6371000 for p in poly]
    a = 0.5 * abs(sum(xs[i] * ys[(i + 1) % len(xs)] - xs[(i + 1) % len(xs)] * ys[i] for i in range(len(xs))))
    return float(a / 10000)


def plan_impact(
    cur: list[dict[str, Any]],
    new: list[dict[str, Any]],
    poly: list[list[float]] | None,
    label: str,
    lang: str = "en",
    econ: Any | None = None,
) -> dict[str, Any]:
    """Current plan vs. improved plan over the planning horizon (per hectare and, with an outline, for the field)."""
    n = max(1, len(cur))

    def tot(ys: list[dict[str, Any]], key: str) -> float:
        return float(sum((y["sim"].get(key) or 0.0) for y in ys))

    water = (tot(cur, "irrigation_mm") - tot(new, "irrigation_mm")) / n
    n_saved = sum(max(0.0, y["sim"]["n_balance_kg_ha"]) for y in new) - sum(
        max(0.0, y["sim"]["n_balance_kg_ha"]) for y in cur
    )
    soil = tot(cur, "erosion_t_ha") - tot(new, "erosion_t_ha")
    margin = tot(new, "margin_usd_ha") - tot(cur, "margin_usd_ha")
    bare = (tot(cur, "bare_days") - tot(new, "bare_days")) / n
    area = _area_ha(poly)
    per_ha = {
        "water_saved_mm_per_yr": round(water),
        "water_saved_m3_per_ha_per_yr": round(water * 10),
        "n_fertiliser_saved_kg_ha": round(n_saved),
        "co2e_avoided_kg_ha": round(n_saved * CO2E_PER_KG_N),
        "soil_kept_t_ha": round(soil, 1),
        "margin_gain_usd_ha": round(margin),
        "margin_gain_local_ha": round(econ.local(margin)) if econ is not None else round(margin),
        "bare_days_fewer_per_yr": round(bare),
    }
    cur_code = econ.currency["code"] if econ is not None else "USD"
    field_total: dict[str, int] | None = None
    if area:
        field_total = {
            "water_saved_m3_per_yr": round(water * 10 * area),
            "n_fertiliser_saved_kg": round(n_saved * area),
            "co2e_avoided_kg": round(n_saved * CO2E_PER_KG_N * area),
            "soil_kept_t": round(soil * area),
            "margin_gain_usd": round(margin * area),
            "margin_gain_local": round((econ.local(margin) if econ is not None else margin) * area),
        }
    gains: list[str] = []
    costs: list[str] = []
    if water > 5:
        gains.append(t("plan_gain_water", lang, v=water))
    elif water < -5:
        costs.append(t("plan_cost_water", lang, v=-water))
    if n_saved > 5:
        gains.append(t("plan_gain_n", lang, v=n_saved, co2=n_saved * CO2E_PER_KG_N))
    elif n_saved < -5:
        costs.append(t("plan_cost_n", lang, v=-n_saved))
    if soil > 0.5:
        gains.append(t("plan_gain_soil", lang, v=soil))
    elif soil < -0.5:
        costs.append(t("plan_cost_soil", lang, v=-soil))
    m_local = econ.local(margin) if econ is not None else margin
    if margin > 20:
        gains.append(t("plan_gain_margin", lang, v=m_local, cur=cur_code))
    elif margin < -20:
        costs.append(t("plan_cost_margin", lang, v=-m_local, cur=cur_code))
    headline = (
        t("plan_headline_gains", lang, label=label, gains="; ".join(gains))
        if gains
        else t("plan_headline_pests", lang)
    )
    if costs:
        headline += t("plan_tradeoff", lang, costs="; ".join(costs))
    return {
        "vs": label,
        "years": len(cur),
        "per_ha": per_ha,
        "field_area_ha": round(area, 2) if area else None,
        "field_total": field_total,
        "headline": headline,
        "currency": cur_code,
        "method": t("plan_impact_method", lang),
    }


def plan_api(req: dict[str, Any]) -> dict[str, Any]:
    lat, lon = float(req["lat"]), float(req["lon"])
    today = dt.date.fromisoformat(req["as_of"]) if req.get("as_of") else dt.date.today()
    history = [h for h in (req.get("history") or []) if h.get("crop") in crops()]
    plan = [p for p in (req.get("plan") or []) if p.get("crop") in crops()]
    if not plan:
        raise ValueError("plan must contain at least one known crop")
    pri = {**DEFAULT_PRI, **(req.get("priorities") or {})}
    lang = req.get("lang") or "en"
    rp.set_lang(lang)
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
    ctx = build(lat, lon, today)
    n_hist = ctx.idx(today) + 1
    annual_p = float(np.nansum(ctx.weather.rain[:n_hist][-365 * 30 :]) / 30.0)
    normals = climmod.monthly_normals(
        ctx.weather.dates[:n_hist],
        ctx.weather.tmax,
        ctx.weather.tmin,
        ctx.weather.rain,
        ctx.weather.et0,
        1991,
        2020,
    )
    system = cropping_system(lat, rot.is_mediterranean(normals, lat), annual_p, irrigation != "none")
    from ..science.pests import region_of

    rp.set_region(region_of(lat, lon))
    econ = econ_for(lat, lon)
    from collections import Counter

    main_crop = Counter(own).most_common(1)[0][0] if own else None
    field = {
        "main_crop": main_crop,
        "system": system,
        "tropical": abs(lat) < 20,
        "irrigated": irrigation != "none",
        "water_allocation_mm": alloc,
        "r_k_ls": _field_rkls(req, plan[0]["crop"]),
        "econ": econ,
    }
    years, summary = rp.evaluate_plan(history, plan, stats, field, pri)

    # single-change suggestions for years with issues
    base = summary["score"]
    sugg: list[dict[str, Any]] = []
    ranked_candidates = sorted(
        regional_filter(farm_type_filter(feasible, own), own, system),
        key=lambda c: -stats[c]["yield_median"] * econ.price_usd_t(c),
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
                    "title": t(
                        "plan_sugg_swap_title",
                        lang,
                        year=y["year"],
                        new=crop_name(best[1], lang),
                        old=crop_name(y["crop"], lang),
                    ),
                    "explanation": t("plan_sugg_avoids", lang, items="; ".join(fixed))
                    if fixed
                    else t("plan_sugg_better", lang),
                    "plan": trial,
                    "score": round(best[0], 1),
                    "score_gain": round(best[0] - base, 1),
                }
            )
        if any(i["id"] == "bare_soil" for i in y["issues"]) and not plan[idx].get("cover_crop"):
            nxt = plan[idx + 1]["crop"] if idx + 1 < len(plan) else None
            cov = rp.best_cover(
                y["crop"], nxt, {c for c in rp.COVER_CANDIDATES if c in crops()}, bool(field.get("tropical"))
            )
            if cov:
                trial = [dict(p) for p in plan]
                trial[idx] = {**trial[idx], "cover_crop": cov}
                _, s2 = rp.evaluate_plan(history, trial, stats, field, pri)
                sugg.append(
                    {
                        "title": t("plan_sugg_cover_title", lang, year=y["year"], cover=crop_name(cov, lang)),
                        "explanation": t("plan_sugg_cover_expl", lang),
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
            key=lambda c: -(stats[c]["yield_median"] * econ.price_usd_t(c) - econ.cost_usd_ha(c)),
        )[:16]
        # always allow the farmer's own crops as candidates
        cands = list(dict.fromkeys([*[p["crop"] for p in plan], *cands]))
        # respect the farm type: perennial forage / specialty crops only if the farm already grows that kind (market, machinery, livestock)
        cands = regional_filter(farm_type_filter(cands, own), own, system)
        best_plan, best_score = rp.optimize(
            history, len(plan), int(plan[0]["year"]), cands, stats, field, pri
        )
        if best_score > base + 0.5:
            changed = [
                f"{p['year']}: {crop_name(p['crop'], lang)}"
                for p, q in zip(best_plan, plan, strict=True)
                if p["crop"] != q["crop"]
            ]
            optimized = {
                "plan": best_plan,
                "score": round(best_score, 1),
                "explanation": t(
                    "plan_opt_expl", lang, changes=", ".join(changed) or t("plan_opt_covers_only", lang)
                ),
            }

    n_prob = sum(y["verdict"] == "problem" for y in years)
    n_caut = sum(y["verdict"] == "caution" for y in years)
    if n_prob:
        headline = t("plan_headline_problem", lang, n=n_prob)
    elif n_caut:
        headline = t("plan_headline_caution", lang, n=n_caut)
    else:
        headline = t("plan_headline_good", lang)
    if optimized and optimized["score"] - base >= 5:
        headline += t("plan_headline_opt", lang, opt=optimized["score"], base=base)
    summary["headline"] = headline
    impact = None
    better: list[dict[str, Any]] | None = None
    if optimized:
        better = list(optimized["plan"])  # type: ignore[call-overload]
    elif sugg:
        better = list(sugg[0]["plan"])
    if better:
        y2, _ = rp.evaluate_plan(history, better, stats, field, pri)
        impact = plan_impact(
            years,
            y2,
            req.get("polygon"),
            t("plan_label_optimised" if optimized else "plan_label_suggested", lang),
            lang,
            econ,
        )
    return {
        "impact": impact,
        "years": years,
        "summary": summary,
        "suggestions": sugg,
        "optimized": optimized,
        "crops_available": feasible,
        "economics": econ.provenance(sorted({y["crop"] for y in years} | {c for c in own})),
        "sources": [
            source_ref("nasa_power", "live"),
            source_ref("srtm", "live"),
            source_ref("soilgrids", "live"),
        ],
        "disclaimer": t("plan_disclaimer", lang),
    }
