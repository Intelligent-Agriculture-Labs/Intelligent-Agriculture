"""Generate site/impact.json from the running API: continuous current crop (2 history + 4 plan years) vs. IA's optimised plan on each demo field.

    python3 scripts/site_impact.py [--api http://localhost:8000]
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

API = sys.argv[sys.argv.index("--api") + 1] if "--api" in sys.argv else "http://localhost:8000"
CASES = {"fallon_nv": ("alfalfa", "furrow"), "machakos_ke": ("maize", "none"), "cordoba_es": ("winter_wheat", "none"), "ames_ia": ("maize", "none")}


def plan(p: dict, crop: str, irr: str) -> dict:
    body = {
        "lat": p["lat"], "lon": p["lon"], "irrigation": irr, "polygon": p.get("polygon"),
        "history": [{"year": 2024, "crop": crop}, {"year": 2025, "crop": crop}],
        "plan": [{"year": y, "crop": crop} for y in (2026, 2027, 2028, 2029)],
    }
    req = urllib.request.Request(f"{API}/api/rotations/plan", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=900))["impact"]


def main() -> None:
    presets = json.load(urllib.request.urlopen(f"{API}/api/presets"))
    presets = {p["id"]: p for p in (presets if isinstance(presets, list) else presets["presets"])}
    imp = {k: plan(presets[k], *CASES[k]) for k in CASES}
    nv, ke, es, ia = (imp[k] for k in ("fallon_nv", "machakos_ke", "cordoba_es", "ames_ia"))
    items = [
        {"value": f"{nv['field_total']['water_saved_m3_per_yr']:,} m³/yr",
         "label": f"less irrigation on a {nv['field_area_ha']:.1f} ha Nevada alfalfa field (trade-off shown in the app: lower margin)"},
        {"value": f"{ia['field_total']['soil_kept_t']:,} t",
         "label": f"topsoil kept over 4 years on a {ia['field_area_ha']:.0f} ha Iowa field vs. continuous maize"},
        {"value": f"−{ke['per_ha']['n_fertiliser_saved_kg_ha']} kg N/ha",
         "label": f"fertiliser over 4 years on a Kenyan smallholder field (≈ {ke['per_ha']['co2e_avoided_kg_ha']} kg CO₂e/ha avoided)"},
        {"value": f"+{es['per_ha']['bare_days_fewer_per_yr']} days/yr",
         "label": "soil covered on a Spanish wheat field (fewer bare days)"},
    ]
    out = Path(__file__).resolve().parents[1] / "site" / "impact.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n")
    (out.parent / "impact_raw.json").write_text(json.dumps(imp, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(items, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
