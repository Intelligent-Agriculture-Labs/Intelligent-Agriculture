"""Render the numeric tables of docs/VALIDATION.md from docs/validation/results.json.

    python3 scripts/validation_report.py                    # all tables
    python3 scripts/validation_report.py --drought-ml-only  # only V8 (from docs/validation/drought_ml.json)

Only the block between <!-- RESULTS:BEGIN --> and <!-- RESULTS:END --> is replaced, so the hand-written
interpretation around it stays. Numbers in the doc therefore always match the last validation run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "docs" / "validation" / "results.json"
DOC = ROOT / "docs" / "VALIDATION.md"
NAMES = {
    "fallon_nv": "Fallon, NV",
    "ames_ia": "Ames, IA",
    "cordoba_es": "Córdoba, ES",
    "machakos_ke": "Machakos, KE",
}


def fmt(x: Any, nd: int = 2) -> str:
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def status_or(r: dict[str, Any], key: str) -> str | None:
    v = r.get(key)
    if isinstance(v, dict) and "status" in v and len(v) == 1:
        return f"*{v['status']}*"
    return None


def render(r: dict[str, Any]) -> str:
    out: list[str] = []
    et = r.get("et0", {})
    out.append(
        "### V1 · Reference ET₀ (FieldShift FAO-56 PM from NASA POWER) vs. ERA5 FAO-56 ET₀, daily 2015–2024"
    )
    out.append(f"_run: {r.get('et0_run_at', '–')}_\n")
    out.append(
        "| Site | n days | daily r | daily RMSE (mm/d) | daily bias (mm/d) | monthly r | monthly bias (mm/mo) |"
    )
    out.append("|---|---|---|---|---|---|---|")
    for k, v in et.items():
        if isinstance(v, dict) and "daily_mm" in v:
            d, m = v["daily_mm"], v["monthly_mm"]
            out.append(
                f"| {NAMES.get(k, k)} | {d['n']} | {fmt(d['r'])} | {fmt(d['rmse'])} | {fmt(d['bias'])} | {fmt(m['r'], 3)} | {fmt(m['bias'], 1)} |"
            )
    out.append("")
    for key, title in (
        ("soil", "V2 · Rain-fed root-zone water (1 − Dr/TAW) vs. ERA5-Land 7–100 cm soil moisture"),
        ("smap", "V3 · Rain-fed root-zone water vs. NASA SMAP L4 root-zone soil moisture (0–100 cm)"),
    ):
        v = r.get(key, {})
        out.append(f"### {title}")
        out.append(f"_run: {r.get(key + '_run_at', '–')}_\n")
        if status_or(r, key):
            out.append(status_or(r, key) or "")
            out.append("")
            continue
        out.append("| Site | crop | seasons | median r per season | pooled standardized r |")
        out.append("|---|---|---|---|---|")
        for k, s in v.items():
            if isinstance(s, dict) and "seasons" in s:
                out.append(
                    f"| {NAMES.get(k, k)} | {s['crop']} | {s['seasons']} | {fmt(s['median_r_per_season'])} | {fmt(s['pooled_standardized_r'])} |"
                )
            elif isinstance(s, dict):
                out.append(f"| {NAMES.get(k, k)} | – | – | {s.get('status', '–')} | – |")
        out.append("")
    u = r.get("usdm", {})
    out.append("### V4 · Drought status vs. U.S. Drought Monitor (weekly 2005–2024, county DSCI)")
    out.append(f"_run: {r.get('usdm_run_at', '–')}_\n")
    out.append(
        "| County | weeks | ρ SPI-90 | ρ SPEI-90 | ρ SPEI-12 | ρ status v1 | ρ status v2 (used) | D1 hit rate v2 | D1 false-alarm ratio v2 |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|")
    for k, s in u.items():
        if isinstance(s, dict) and "weeks" in s:
            d2 = s.get("d1_detection_v2", {})
            out.append(
                f"| {NAMES.get(k, k)} | {s['weeks']} | {fmt(s.get('spearman_spi90'))} | {fmt(s.get('spearman_spei90'))} | {fmt(s.get('spearman_spei365'))} | "
                f"{fmt(s.get('spearman_level_v1'))} | {fmt(s.get('spearman_level_v2'))} | {fmt(d2.get('hit_rate'))} | {fmt(d2.get('false_alarm_ratio'))} |"
            )
    out.append("")
    y = r.get("yield", {})
    out.append("### V5 · Documented drought years in simulated rain-fed yields")
    out.append(f"_run: {r.get('yield_run_at', '–')}_\n")
    if "rank_of_2012" in y:
        k = y.get("kenya_short_rains", {})
        out.append("| Site / season | years simulated | documented drought year | rank (1 = worst) |")
        out.append("|---|---|---|---|")
        out.append(f"| Ames, IA maize | {y['n_years']} | 2012 | **{y['rank_of_2012']}** |")
        out.append(f"| Ames, IA maize | {y['n_years']} | 1988 | **{y['rank_of_1988']}** |")
        if k:
            out.append(
                f"| Machakos, KE maize (short rains) | {k['n_years']} | 2016 | **{k['rank_of_2016']}** |"
            )
            out.append(
                f"| Machakos, KE maize (short rains) | {k['n_years']} | 2005 | **{k['rank_of_2005']}** |"
            )
    out.append("")
    m = r.get("mod16", {})
    out.append(
        "### V6 · Irrigated alfalfa ET at the Fallon field: model vs NASA ECOSTRESS (70 m) and MODIS MOD16 (500 m)"
    )
    out.append(f"_run: {r.get('mod16_run_at', '–')}_\n")
    if "ecostress_daily" in m:
        e = m["ecostress_daily"]
        out.append(
            f"ECOSTRESS daily ET on {e['n']} clear overpass days (May–Sep 2018–2024): r = {fmt(e['r'])}, bias = {fmt(e['bias'])} mm/day "
            f"(model mean {fmt(e['mean_model'])} vs ECOSTRESS {fmt(e['mean_ref'])} mm/day), RMSE {fmt(e['rmse'])} mm/day.\n"
        )
    if "mod16_annual" in m:
        a = m["mod16_annual"]
        out.append("| Year | " + " | ".join(str(x) for x in a["years"]) + " |")
        out.append("|---|" + "---|" * len(a["years"]))
        out.append("| FieldShift (mm/yr) | " + " | ".join(str(x) for x in a["model_mm"]) + " |")
        out.append("| MOD16 (mm/yr) | " + " | ".join(str(x) for x in a["mod16_mm"]) + " |")
    if "status" in m:
        out.append(f"*{m['status']}*")
    if "note" in m:
        out.append(f"\n{m['note']}")
    out.append("")
    b = r.get("blight", {})
    out.append("### V7 · Late-blight weather risk (Hutton criteria, NASA POWER hourly), Ithaca NY, Jun–Aug")
    out.append(f"_run: {r.get('blight_run_at', '–')}_\n")
    if "per_year" in b:
        yrs = sorted(b["per_year"])
        out.append("| Year | " + " | ".join(yrs) + " |")
        out.append("|---|" + "---|" * len(yrs))
        out.append("| Hutton days | " + " | ".join(str(b["per_year"][x]["hutton_days"]) for x in yrs) + " |")
        out.append(f"\n2009 (documented epidemic) ranks **{b['rank_of_2009']} of {b['n_years']}**.")
    out.append("")
    mlp = RES.parent / "drought_ml.json"
    if mlp.exists():
        out += render_drought_ml(json.loads(mlp.read_text()))
    return "\n".join(out)


REGION_NAMES = {
    "US": "U.S. (USDM)",
    "EU": "Europe (EDO CDI)",
    "AUS": "Australia (GDO SMIA, weak)",
    "SAM": "South America (GDO SMIA, weak)",
    "AFR": "Sub-Saharan Africa (GDO SMIA, weak)",
    "SAS": "South Asia (GDO SMIA, weak)",
    "EAS": "East Asia (GDO SMIA, weak)",
    "WEAK_POOLED": "All weak-label regions pooled",
}
METRICS = (
    ("exact_acc", "Exact"),
    ("within1_acc", "Within ±1"),
    ("mae_levels", "MAE"),
    ("spearman", "Spearman"),
    ("d1_hit_rate", "D1+ hit"),
    ("d1_false_alarm_ratio", "D1+ FAR"),
)


def _rows(models: dict[str, dict[str, Any]], names: dict[str, str]) -> list[str]:
    out = ["| Model | n | " + " | ".join(lab for _, lab in METRICS) + " |", "|---|---|" + "---|" * len(METRICS)]
    for k, lab in names.items():
        if k in models:
            v = models[k]
            out.append(f"| {lab} | {v['n']:,} | " + " | ".join(fmt(v[m], 3) for m, _ in METRICS) + " |")
    return out


def render_drought_ml(m: dict[str, Any]) -> list[str]:
    """V8: drought classifier, held-out by county (U.S.), by region and by climate zone (scripts/train_drought_ml.py)."""
    out = ["### V8 · AI drought classifier on sites, regions and climate zones the model never saw"]
    out.append(
        f"_trained: {m['trained_at']} · {m['n_sites']} sites in {len(m['regions'])} regions · "
        f"{m['n_samples']:,} labels · {m['cv']}_\n"
    )
    names = {
        "current_model": "Current model (U.S.-trained, v1 features)",
        "new_model": "Global model (v2 features, class-balanced)",
        "new_model_unbalanced": "Global model (v2 features, unbalanced)",
        "rules": "Rule-based blend",
    }
    us = m["per_region"]["US"]
    out.append("**U.S., native USDM scale (None…D4), counties held out (GroupKFold 5); Spearman vs. DSCI**\n")
    out += _rows(us["native_usdm"], names)
    out.append("")
    out.append(
        "**Per region, harmonised scale (None / D0·Watch / D1·Warning / D2+·Alert).** U.S. = county CV; every other "
        "region = leave-one-region-out (the global model never saw that region; the current model never saw anything "
        "outside the U.S.). Spearman vs. the label level.\n"
    )
    for r, v in m["per_region"].items():
        out.append(f"_{REGION_NAMES.get(r, r)}: {v['n_sites']} sites_\n")
        extra = dict(names)
        extra["v2_trained_on_us_only"] = "v2 features, trained on U.S. only"
        extra["europe_only_model"] = "v2 features, trained on Europe only"
        out += _rows(v["harmonised"], extra)
        out.append("")
    out.append("**Leave-one-climate-zone-out (harmonised scale)**\n")
    for z, v in m["per_zone"].items():
        regs = ", ".join(f"{k} {n}" for k, n in v["regions"].items())
        out.append(f"_{z}: {v['n_sites']} sites ({regs})_\n")
        zone_models = {k.removesuffix("_lozo"): x for k, x in v.items() if isinstance(x, dict) and "n" in x}
        out += _rows(zone_models, {k: lab + (" — zone held out" if k.startswith("new_model") else "") for k, lab in names.items()})
        out.append("")
    lq = m["label_quality"]
    out.append(
        f"**Weak-label quality.** SMIA thresholds (D0…D4, calibrated on U.S. sites): {m['smia_thresholds_d0_d4']}. "
        f"Agreement of the SMIA label with USDM (U.S.): within ±1 {fmt(lq['smia_vs_usdm_us']['within1_acc'], 3)}, "
        f"Spearman {fmt(lq['smia_vs_usdm_us']['spearman'], 3)}"
        + (
            f"; with CDI (Europe): within ±1 {fmt(lq['smia_vs_cdi_eu']['within1_acc'], 3)}, "
            f"Spearman {fmt(lq['smia_vs_cdi_eu']['spearman'], 3)}."
            if "smia_vs_cdi_eu" in lq
            else "."
        )
        + "\n"
    )
    for k, c in m["adoption_checks"].items():
        out.append(f"- {names.get(k, k)}: " + ", ".join(f"{a}: {b}" for a, b in c.items()))
    out.append(
        f"\n**Adopted: {m['adopted']}** (served: {names.get(m['served_key'], m['served_key'])}). "
        f"Model used in: {', '.join(m['model_regions'])}; elsewhere the rule-based blend.\n"
    )
    return out


def main() -> None:
    doc = DOC.read_text()
    a, b = "<!-- RESULTS:BEGIN -->", "<!-- RESULTS:END -->"
    i, j = doc.index(a) + len(a), doc.index(b)
    if "--drought-ml-only" in sys.argv:
        # replace only the V8 subsection (keeps hand-written notes on pending checks elsewhere in the block)
        k = doc.index("### V8 ", i)
        v8 = "\n".join(render_drought_ml(json.loads((RES.parent / "drought_ml.json").read_text())))
        DOC.write_text(doc[:k] + v8 + "\n" + doc[j:])
    else:
        r = json.loads(RES.read_text())
        DOC.write_text(doc[:i] + "\n" + render(r) + "\n" + doc[j:])
    print("updated", DOC)


if __name__ == "__main__":
    main()
