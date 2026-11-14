"""Per-field multi-year rotation plan: biological + agronomic checks and an optimizer.

Biology (config/rotation_knowledge.yaml; sources in docs/ROTATION_SCIENCE.md):
  * Return intervals (same crop) and family intervals.
  * Soil-/residue-borne pathogens & pests with host ranges: inoculum carried from earlier host years decays with the
    organism's survival time (exponential decay, half-life = survival_years / 3, i.e. ~95 % gone after `survival_years`).
    Pressure in a host year = Σ over earlier host years of exp(−Δt·ln2 / half_life). Levels: <0.25 low, <0.6 medium, else high.
  * Predecessor effects: good/poor predecessors, preceding-crop value, allelopathy notes, and rules with yield effects.
  * Nitrogen carry-over: n_effect_kg_ha of the previous main crop plus the cover crop's fixation.
Agronomy: each crop is simulated over 15 past seasons at the field (FieldShift season model: NASA POWER weather, soil,
irrigation method and allocation); rotation effects scale yield; bare-soil days from season lengths; RUSLE erosion with the
field's own LS·R·K and the crop's C factor (cover crops reduce C).
Score per year = priority-weighted mean of five 0–100 components (pests/disease, soil, water, income, climate risk).
The optimizer is a beam search over climate-feasible crops (+ automatic cover-crop choice) maximising the plan score.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import yaml

from .cropmodel import crop, crops

CONFIG = Path(__file__).resolve().parents[1] / "config"
SEVERITY_PENALTY = {"problem": 25.0, "caution": 10.0, "info": 0.0}
COVER_CANDIDATES = ("cover_rye_vetch", "phacelia_cover", "mustard_cover", "mung_bean", "cowpea")
TROPICAL_COVERS = ("mung_bean", "cowpea")  # quick legumes for the short dry-season gap
TEMPERATE_COVERS = ("cover_rye_vetch", "phacelia_cover", "mustard_cover")


@lru_cache
def knowledge() -> dict[str, Any]:
    p = CONFIG / "rotation_knowledge.yaml"
    if not p.exists():
        return {"pathogens": {}, "crops": {}, "rules": []}
    with open(p) as f:
        k = yaml.safe_load(f) or {}
    k.setdefault("pathogens", {})
    k.setdefault("crops", {})
    k.setdefault("rules", [])
    return k


def ck(cid: str) -> dict[str, Any]:
    """Rotation knowledge for a crop, with conservative defaults from the crop table when missing."""
    c = crop(cid)
    k = dict(knowledge()["crops"].get(cid) or {})
    k.setdefault("min_return_years", 1 if c["type"] in ("perennial", "cover") else 2)
    k.setdefault("self_tolerance", "medium")
    k.setdefault("family_return_years", 1)
    k.setdefault("n_effect_kg_ha", float(c.get("n_fix_kg_ha", 0)) * 0.5)
    k.setdefault("preceding_crop_value", "high" if c["family"] == "Fabaceae" else "medium")
    k.setdefault("good_predecessors", [])
    k.setdefault("poor_predecessors", [])
    k.setdefault("allelopathy", None)
    k.setdefault("sources", [])
    return k


def hosts_of(cid: str) -> list[tuple[str, dict[str, Any]]]:
    return [(pid, p) for pid, p in knowledge()["pathogens"].items() if cid in (p.get("hosts") or [])]


def rule(rid: str) -> dict[str, Any] | None:
    return next((r for r in knowledge()["rules"] if r.get("id") == rid), None)


def cname(cid: str) -> str:
    return str(crop(cid)["name"])


def _short(text: str, n: int = 90) -> str:
    t = text.split(":")[0].split(". ")[0].strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def apply_rules(seq: list[str], i: int) -> tuple[float, list[dict[str, Any]], list[str], set[str]]:
    """Cited sequence rules from the knowledge base (applies_to × after within window_years).
    Returns (yield effect fraction, issues, benefits, matched rule ids)."""
    cid = seq[i]
    eff = 0.0
    issues: list[dict[str, Any]] = []
    benefits: list[str] = []
    matched: set[str] = set()
    for r in knowledge()["rules"]:
        apps, aft = r.get("applies_to"), r.get("after")
        if not apps or not aft or cid not in apps or r.get("yield_effect_pct") in (None, 0):
            continue
        win = int(r.get("window_years") or 1)
        prev = [seq[j] for j in range(max(0, i - win), i)]
        hit = next((p for p in reversed(prev) if p in aft), None)
        if hit is None:
            continue
        pct = float(r["yield_effect_pct"])
        eff += pct / 100.0
        matched.add(r["id"])
        conf = " (estimate)" if r.get("low_confidence") else ""
        if pct < 0:
            issues.append(
                {
                    "id": f"rule:{r['id']}",
                    "severity": "problem" if pct <= -15 else "caution",
                    "title": f"{cname(cid)} after {cname(hit)}: about {pct:.0f} % yield{conf}",
                    "explanation": str(r.get("text", "")),
                    "suggestion": f"Put a crop from another family between {cname(hit)} and {cname(cid)}.",
                    "sources": (r.get("sources") or [])[:2],
                }
            )
        else:
            benefits.append(
                f"{cname(hit)} before {cname(cid)}: about +{pct:.0f} % yield{conf} — {_short(str(r.get('text', '')), 140)}"
            )
    return eff, issues, benefits, matched


# Organisms rotation cannot control (very wide host range or migratory) — excluded from rotation pressure; wireworms are
# handled by the cited "after grass/ley" rule instead of their host list. See docs/ROTATION_SCIENCE.md.
NOT_ROTATION_CONTROLLED = {"rhizoctonia", "pythium", "root_knot_nematode", "fall_armyworm", "wireworms"}
# Geographic ranges for organisms that are absent from large regions (continent codes from pests.region_of).
PATHOGEN_REGIONS = {
    "striga": {"africa", "asia"},
    "corn_rootworm": {"north_america", "europe"},
    "broomrape": {"europe", "africa", "asia"},
    "cereal_stem_borers": {"africa", "asia"},
    "blackgrass": {"europe"},
}
_REGION: dict[str, str] = {"value": ""}


def set_region(region: str) -> None:
    _REGION["value"] = region


def rotation_relevant(p: dict[str, Any], pid: str = "") -> bool:
    if pid in NOT_ROTATION_CONTROLLED or not (p.get("hosts") or []):
        return False
    reg = PATHOGEN_REGIONS.get(pid)
    return not (reg and _REGION["value"] and _REGION["value"] not in reg)


def pathogen_pressure(seq: list[str], i: int, pid: str, p: dict[str, Any]) -> tuple[float, list[int]]:
    """Risk from earlier host years relative to the published host-free break (break_years):
    high (1.0)  = a host grew last year, or ≥ 2 host years within the break window;
    medium (0.5) = one host year within the break window;
    low (0.2/0) = hosts only longer ago (but within survival_years) / none."""
    hosts = set(p.get("hosts") or [])
    brk = max(1, int(float(p.get("break_years", 2) or 2)))
    years = [j for j in range(i) if seq[j] in hosts]
    if not years:
        return 0.0, []
    gap = i - years[-1]
    in_window = [j for j in years if i - j <= brk]
    if gap == 1 or len(in_window) >= 2:
        return 1.0, years
    if gap <= brk:
        return 0.5, years
    surv = max(brk, int(float(p.get("survival_years", brk) or brk)))
    return (0.2 if gap <= surv else 0.0), years


def pressure_level(x: float) -> str:
    return "low" if x < 0.4 else ("medium" if x < 0.9 else "high")


def check_year(
    seq: list[str],
    covers: list[str | None],
    i: int,
    years: list[int],
    stats: dict[str, dict[str, Any]],
    field: dict[str, Any],
    priorities: dict[str, float],
) -> dict[str, Any]:
    """Evaluate the main crop at index i of the full sequence (history + plan)."""
    cid = seq[i]
    c = crop(cid)
    k = ck(cid)
    issues: list[dict[str, Any]] = []
    benefits: list[str] = []
    effect = 0.0  # rotation yield effect (fraction)
    pests_pen = 0.0
    continuing_stand = c["type"] == "perennial" and i > 0 and seq[i - 1] == cid
    r_eff, r_issues, r_benefits, matched = (0.0, [], [], set()) if continuing_stand else apply_rules(seq, i)
    neg_rule = any(x["severity"] != "info" for x in r_issues)
    pos_rule = bool(r_benefits)
    effect += r_eff
    issues.extend(r_issues)
    benefits.extend(r_benefits)
    pests_pen += sum(15 if x["severity"] == "problem" else 8 for x in r_issues)

    # 1. return interval (same crop)
    prev_same = [j for j in range(i) if seq[j] == cid]
    if prev_same and c["type"] != "perennial":
        gap = i - prev_same[-1]
        need = int(k["min_return_years"])
        if gap < need:
            sev = "problem" if gap <= max(1, need // 2) else "caution"
            tol = k["self_tolerance"]
            issues.append(
                {
                    "id": "return_interval",
                    "severity": sev if tol != "high" else "caution",
                    "title": f"{cname(cid)} again too soon",
                    "explanation": f"{cname(cid)} was grown {gap} year(s) earlier ({years[prev_same[-1]]}). Research recommends waiting at least {need} "
                    f"years before growing it again on the same field, so its soil-borne pests and diseases die out.",
                    "suggestion": f"Grow a crop from another family here and keep {cname(cid)} for {years[prev_same[-1]] + need} or later.",
                    "sources": k["sources"][:2],
                }
            )
            if (
                not neg_rule
            ):  # cited sequence rules already carry the yield effect; otherwise use a generic −10 %
                effect -= 0.10
            pests_pen += 30 if sev == "problem" else 15
    # perennial stands: autotoxicity / max years in a row handled by min_return after the stand ends
    if c["type"] == "perennial" and prev_same:
        run = 1
        j = i - 1
        while j >= 0 and seq[j] == cid:
            run += 1
            j -= 1
        if run > 5:
            issues.append(
                {
                    "id": "old_stand",
                    "severity": "caution",
                    "title": f"{cname(cid)} stand is {run} years old",
                    "explanation": "Old stands thin out and yields fall; most guides plough out after 4–5 years.",
                    "suggestion": "Plan to end the stand and follow with a cereal that uses its nitrogen.",
                    "sources": k["sources"][:1],
                }
            )
            effect -= 0.05 * (run - 5)
        if j >= 0 and run == 1 and seq[j] == cid:
            pass
    # 2. family interval
    fam_need = int(k.get("family_return_years") or 1)
    if fam_need > 1 and not prev_same:
        prev_fam = [
            j
            for j in range(max(0, i - fam_need + 1), i)
            if crop(seq[j])["family"] == c["family"] and c["family"] not in ("Mixed",)
        ]
        if prev_fam:
            issues.append(
                {
                    "id": "family_interval",
                    "severity": "caution",
                    "title": f"Same plant family as {cname(seq[prev_fam[-1]])}",
                    "explanation": f"{cname(cid)} and {cname(seq[prev_fam[-1]])} are both {c['family']}; they share pests and diseases. "
                    f"Leave {fam_need} years between crops of this family.",
                    "suggestion": "Alternate plant families (e.g. grass → legume → brassica/other).",
                    "sources": k["sources"][:1],
                }
            )
            effect -= 0.04
            pests_pen += 10
    # 3. shared pathogens / pests
    for pid, p in [] if continuing_stand else hosts_of(cid):
        if not rotation_relevant(p, pid):
            continue
        pres, host_years = pathogen_pressure(seq, i, pid, p)
        lvl = pressure_level(pres)
        if lvl == "low":
            continue
        sev_w = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(str(p.get("severity", "medium")), 0.6)
        sev = "problem" if (lvl == "high" and sev_w >= 1.0) else "caution"
        hy = ", ".join(f"{cname(seq[j])} {years[j]}" for j in host_years[-3:])
        issues.append(
            {
                "id": f"shared_pathogen:{pid}",
                "severity": sev,
                "title": f"{lvl.capitalize()} {p.get('name', pid)} risk",
                "explanation": f"{p.get('note') or p.get('name', pid)} It survives about {p.get('survival_years', '?')} years in the soil, "
                f"and earlier host crops ({hy}) kept it alive.",
                "suggestion": f"Leave {p.get('break_years', 3)} years without its host crops before {cname(cid)}.",
                "sources": (p.get("sources") or [])[:2],
            }
        )
        effect -= (0.12 if lvl == "high" else 0.05) * sev_w
        pests_pen += (25 if lvl == "high" else 10) * sev_w
    # 4. predecessor effects
    n_credit = 0.0
    if i > 0:
        prev = seq[i - 1]
        pk = ck(prev)
        if prev in k["poor_predecessors"] and not continuing_stand:
            issues.append(
                {
                    "id": "poor_predecessor",
                    "severity": "caution",
                    "title": f"{cname(prev)} is a poor crop before {cname(cid)}",
                    "explanation": k.get("note")
                    or f"{cname(cid)} does worse after {cname(prev)} (pests, residue or nitrogen tie-up).",
                    "suggestion": f"Put a better predecessor before {cname(cid)}"
                    + (f", e.g. {cname(k['good_predecessors'][0])}." if k["good_predecessors"] else "."),
                    "sources": k["sources"][:1],
                }
            )
            if not neg_rule:
                effect -= 0.05
        elif not pos_rule and (
            prev in k["good_predecessors"] or pk["preceding_crop_value"] in ("high", "medium")
        ):
            benefits.append(
                f"{cname(prev)} is a good crop before {cname(cid)}"
                + (f" ({pk['note']})" if pk.get("note") and prev in k["good_predecessors"] else ".")
            )
            scale = (rule("predecessor_value_scale") or {}).get("scale") or {
                "high": 15,
                "medium": 5,
                "low": -5,
            }
            effect += float(scale.get(str(pk["preceding_crop_value"]), 0)) / 100.0
        elif not pos_rule and not neg_rule and pk["preceding_crop_value"] in ("low", "very_low"):
            scale = (rule("predecessor_value_scale") or {}).get("scale") or {"low": -5, "very_low": -15}
            effect += float(scale.get(str(pk["preceding_crop_value"]), -5)) / 100.0
        if pk.get("allelopathy") and prev != cid and "allelopathic_residue" not in matched:
            issues.append(
                {
                    "id": "allelopathy",
                    "severity": "info",
                    "title": f"Residues of {cname(prev)}",
                    "explanation": str(pk["allelopathy"]),
                    "suggestion": "Incorporate or let residues break down before sowing; avoid very small-seeded crops right after.",
                    "sources": pk["sources"][:1],
                }
            )
        n_credit += float(pk["n_effect_kg_ha"])
        cov = covers[i - 1]
        if cov:
            n_credit += float(crop(cov).get("n_fix_kg_ha", 0)) * 0.5
    if c["family"] == "Fabaceae":
        n_credit = max(n_credit, 0.0)
    if n_credit >= 20:
        benefits.append(f"About {n_credit:.0f} kg N/ha left by the previous crops — less fertiliser needed.")
    elif n_credit <= -15:
        issues.append(
            {
                "id": "n_deficit",
                "severity": "info",
                "title": "Nitrogen tied up by straw",
                "explanation": f"Residues of the previous crop tie up about {abs(n_credit):.0f} kg N/ha while they decompose.",
                "suggestion": "Plan a little extra nitrogen at sowing or follow with a legume.",
                "sources": [],
            }
        )

    # 5. simulation results (yield, water) with rotation effect
    st = stats[cid]
    if c["type"] == "perennial" and (i == 0 or seq[i - 1] != cid):
        effect -= 0.30  # establishment (seeding) year: ~70 % of a full-stand yield
        issues.append(
            {
                "id": "establishment",
                "severity": "info",
                "title": f"{cname(cid)} establishment year",
                "explanation": "A new stand yields about 70 % of a full year while roots establish.",
                "suggestion": None,
                "sources": [],
            }
        )
    effect = float(np.clip(effect, -0.30, 0.15))  # combined rotation effect capped (effects overlap)
    y_med = st["yield_median"] * (1 + effect)
    y_p10 = st["yield_p10"] * (1 + effect)
    price, cost = float(c.get("price_usd_t", 0)), float(c.get("cost_usd_ha", 0))
    margin = y_med * price - cost + max(0.0, n_credit) * 1.3
    if st["feasible_issue"]:
        issues.append(
            {
                "id": "climate",
                "severity": "problem",
                "title": f"{cname(cid)} struggles in this climate",
                "explanation": st["feasible_issue"],
                "suggestion": "Choose a crop from the list that fits this field's season.",
                "sources": [],
            }
        )
    alloc = field.get("water_allocation_mm")
    if field.get("irrigated") and alloc and st["irrigation_mm"] > alloc * 1.05:
        issues.append(
            {
                "id": "water_shortfall",
                "severity": "caution",
                "title": "Needs more water than you have",
                "explanation": f"{cname(cid)} needs about {st['irrigation_mm']:.0f} mm of irrigation in a typical year here; your allocation is {alloc:.0f} mm.",
                "suggestion": "Pick a lower-water crop, use deficit irrigation, or split the field.",
                "sources": [],
            }
        )
    if not field.get("irrigated") and st["fail_share"] > 0.25:
        issues.append(
            {
                "id": "drought_risk",
                "severity": "caution",
                "title": "Often fails in dry years",
                "explanation": f"Without irrigation, {cname(cid)} failed in {100 * st['fail_share']:.0f} % of the last {st['n']} seasons at this field.",
                "suggestion": "Consider a more drought-tolerant crop (e.g. sorghum, millet, cowpea) or earlier sowing.",
                "sources": [],
            }
        )

    # 6. soil cover / erosion
    cov_i = covers[i]
    covered = min(365, st["season_days"] + (int(crop(cov_i)["season_days"]) if cov_i else 0))
    bare = max(0, 365 - covered) if c["type"] != "perennial" else 0
    cfac = 0.02 if c["type"] == "perennial" else (0.20 if st["small_grain"] else 0.38)
    if covers[i]:
        cfac *= 0.6
    erosion = field["r_k_ls"] * cfac if field.get("r_k_ls") is not None else None
    if bare > 150 and not covers[i] and c["type"] != "perennial":
        issues.append(
            {
                "id": "bare_soil",
                "severity": "caution" if (erosion or 0) > 3 else "info",
                "title": f"Soil bare for ~{bare} days",
                "explanation": "Bare soil loses structure, carbon and — on slopes or in heavy rain — topsoil."
                + (f" Estimated erosion here: {erosion:.1f} t/ha per year." if erosion is not None else ""),
                "suggestion": "Sow a cover crop after harvest.",
                "sources": [],
            }
        )

    # 7. score components (0–100)
    comp = {
        "pests": max(0.0, 100 - min(80.0, pests_pen)),
        "soil": float(
            np.clip(
                40
                + 0.25 * max(0.0, n_credit)
                + (25 if c["type"] == "perennial" or covers[i] else 0)
                + (15 if crop(cid).get("residue") == "high" else 5)
                - bare / 10
                - (erosion or 0) * 3,
                0,
                100,
            )
        ),
        "water": float(
            np.clip(
                100 * (1 - st["irrigation_mm"] / 1400.0)
                if field.get("irrigated")
                else 100 * (1 - st["fail_share"]),
                0,
                100,
            )
        ),
        "income": float(np.clip(50 + margin / 30.0, 0, 100)),
        "risk": float(np.clip(100 * (1 - st["fail_share"]) - 5 * st["frost_share"] * 10, 0, 100)),
    }
    wsum = sum(priorities.values()) or 1.0
    score = sum(priorities[kk] * comp[kk] for kk in comp) / wsum
    score -= min(30.0, sum(SEVERITY_PENALTY[iss["severity"]] * 0.4 for iss in issues))
    score = float(np.clip(score, 0, 100))
    verdict = (
        "problem"
        if any(x["severity"] == "problem" for x in issues)
        else ("caution" if any(x["severity"] == "caution" for x in issues) else "good")
    )
    return {
        "year": years[i],
        "crop": cid,
        "cover_crop": covers[i],
        "verdict": verdict,
        "score": round(score, 1),
        "issues": issues,
        "benefits": benefits,
        "sim": {
            "yield_t_ha": round(y_med, 2),
            "yield_p10": round(y_p10, 2),
            "irrigation_mm": round(st["irrigation_mm"]),
            "water_use_mm": round(st["et_mm"]),
            "n_balance_kg_ha": round(n_credit),
            "margin_usd_ha": round(margin),
            "bare_days": int(bare),
            "erosion_t_ha": None if erosion is None else round(erosion, 2),
            "rotation_effect_pct": round(100 * effect, 1),
        },
    }


def best_cover(
    prev_main: str, next_main: str | None, available: set[str], tropical: bool = False
) -> str | None:
    """Pick a cover crop that does not share family/pathogens with the next cash crop (e.g. no brassica cover before canola);
    quick legumes in the tropics, winter-hardy grass/legume or phacelia/mustard in temperate climates."""
    for cov in TROPICAL_COVERS if tropical else TEMPERATE_COVERS:
        if cov not in available:
            continue
        if next_main and crop(cov)["family"] == crop(next_main)["family"]:
            continue
        if next_main and any(
            next_main in (p.get("hosts") or []) and cov in (p.get("hosts") or [])
            for p in knowledge()["pathogens"].values()
        ):
            continue
        return cov
    return None


def evaluate_plan(
    history: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    stats: dict[str, dict[str, Any]],
    field: dict[str, Any],
    priorities: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    seq = [h["crop"] for h in history] + [p["crop"] for p in plan]
    covers = [h.get("cover_crop") for h in history] + [p.get("cover_crop") for p in plan]
    years = [int(h["year"]) for h in history] + [int(p["year"]) for p in plan]
    out = [check_year(seq, covers, i, years, stats, field, priorities) for i in range(len(history), len(seq))]
    # disease pressure summary over plan years
    dp = []
    for pid, p in knowledge()["pathogens"].items():
        if not rotation_relevant(p, pid):
            continue
        worst = 0.0
        yrs = []
        for i in range(len(history), len(seq)):
            if seq[i] in (p.get("hosts") or []):
                pres, _ = pathogen_pressure(seq, i, pid, p)
                if pres >= 0.4:
                    yrs.append(years[i])
                worst = max(worst, pres)
        if yrs:
            dp.append(
                {"pathogen": pid, "name": p.get("name", pid), "level": pressure_level(worst), "years": yrs}
            )
    score = float(np.mean([y["score"] for y in out])) if out else 0.0
    n_prob = sum(y["verdict"] == "problem" for y in out)
    n_caut = sum(y["verdict"] == "caution" for y in out)
    verdict = "problem" if n_prob else ("caution" if n_caut else "good")
    summary = {
        "score": round(score, 1),
        "verdict": verdict,
        "total_margin_usd_ha": round(sum(y["sim"]["margin_usd_ha"] for y in out)),
        "avg_irrigation_mm": round(float(np.mean([y["sim"]["irrigation_mm"] for y in out])) if out else 0),
        "n_balance_kg_ha": round(sum(y["sim"]["n_balance_kg_ha"] for y in out)),
        "disease_pressure": sorted(dp, key=lambda d: {"high": 0, "medium": 1, "low": 2}[d["level"]]),
    }
    return out, summary


def optimize(
    history: list[dict[str, Any]],
    n_years: int,
    start_year: int,
    candidates: list[str],
    stats: dict[str, dict[str, Any]],
    field: dict[str, Any],
    priorities: dict[str, float],
    beam: int = 24,
    fixed: dict[int, str] | None = None,
) -> tuple[list[dict[str, Any]], float]:
    """Beam search over crop sequences (cover crops chosen greedily for bare-soil gaps)."""
    available_covers = {c for c in COVER_CANDIDATES if c in crops()}
    states: list[tuple[float, list[dict[str, Any]]]] = [(0.0, [])]
    for t in range(n_years):
        nxt: list[tuple[float, list[dict[str, Any]]]] = []
        options = [fixed[t]] if fixed and t in fixed else candidates
        for _, plan in states:
            for cid in options:
                trial = [*plan, {"year": start_year + t, "crop": cid, "cover_crop": None}]
                seq_hist = [h["crop"] for h in history]
                if crop(cid)["type"] not in ("perennial",) and stats[cid]["season_days"] < 250:
                    trial[-1]["cover_crop"] = best_cover(
                        cid, None, available_covers, bool(field.get("tropical"))
                    )
                if len(trial) >= 2 and trial[-2]["cover_crop"]:  # re-check previous cover against this crop
                    trial[-2]["cover_crop"] = best_cover(
                        trial[-2]["crop"], cid, available_covers, bool(field.get("tropical"))
                    )
                ys, _ = evaluate_plan(history, trial, stats, field, priorities)
                sc = float(np.mean([y["score"] for y in ys]))
                main = field.get("main_crop")
                if main and t == n_years - 1 and n_years >= 3 and not any(q["crop"] == main for q in trial):
                    sc -= 15.0  # keep the farm's staple/main crop in the rotation (food security, market, know-how)
                nxt.append((sc, trial))
                del seq_hist
        nxt.sort(key=lambda x: -x[0])
        # diversity: keep at most 3 states ending with the same crop
        kept: list[tuple[float, list[dict[str, Any]]]] = []
        per_last: dict[str, int] = {}
        for sc, pl in nxt:
            lc = pl[-1]["crop"]
            if per_last.get(lc, 0) >= 3:
                continue
            per_last[lc] = per_last.get(lc, 0) + 1
            kept.append((sc, pl))
            if len(kept) >= beam:
                break
        states = kept
    best = states[0]
    return best[1], best[0]


def slot_summary(slot: Any, c: dict[str, Any], feasible_issue: str | None, cid: str) -> dict[str, Any]:
    ys = slot.yields or [0.0]
    return {
        "yield_median": float(median(ys)),
        "yield_p10": float(np.percentile(ys, 10)),
        "irrigation_mm": float(median(slot.irr)) if slot.irr else 0.0,
        "et_mm": float(median(slot.et)) if slot.et else 0.0,
        "fail_share": float(slot.fail_share),
        "frost_share": float(np.mean([f > 0 for f in slot.frost])) if slot.frost else 0.0,
        "season_days": int(slot.length or c.get("season_days", 120)),
        "n": int(slot.n),
        "feasible_issue": feasible_issue,
        "small_grain": cid
        in {
            "winter_wheat",
            "barley",
            "triticale_forage",
            "oats",
            "rye",
            "spring_wheat",
            "durum_wheat",
            "winter_barley",
            "spelt",
            "teff",
        },
    }
