"""Train and validate the FieldShift ML drought classifier on several continents (run on the data box).

    FIELDSHIFT_CACHE_DIR=~/fs-gdml-data/cache backend/.venv/bin/python scripts/drought_labels_global.py
    FIELDSHIFT_CACHE_DIR=~/fs-gdml-data/cache backend/.venv/bin/python scripts/train_drought_ml.py

Labels (see drought_labels_global.py for sources and licences):
  US   weekly U.S. Drought Monitor county categories, 80 counties, 2005-2024 (strong, 6 levels None..D4)
  EU   dekadal EDO Combined Drought Indicator, 80 sites, 2012-2024 (strong, Watch/Warning/Alert ~ D0/D1/D2)
  AUS, SAM, AFR, SAS, EAS  dekadal GDO soil-moisture anomaly, 30 sites each, 2005-2024 (weak: one modelled
       indicator, converted to levels with thresholds calibrated on the U.S. sites against USDM)
Features: NASA POWER daily 2000-2024 -> fieldshift.science.drought_ml.feature_matrix (v1, the U.S. model) and
feature_matrix_v2 (location-agnostic). The rule-based status (drought.combined_level) is scored on the same samples.

Validation (all on sites the model never saw):
  * U.S.: GroupKFold(5) by county, identical folds for every model; the new model also trains on all non-U.S. data.
  * Leave-one-region-out: train on every other region, test on the held-out region.
  * Leave-one-climate-zone-out (arid / tropical / temperate / cold, from NASA POWER climatology).
  * Transfer: train on Europe only -> test U.S., and U.S. only -> test Europe.
Metrics are reported on each region's native scale and on a harmonised 4-level scale (None, D0, D1, D2+) so that
regions with different label systems can be compared.

Adoption rule (fixed before the run): the new model replaces the current one only if, on the U.S. county CV, its
within-1 accuracy and Spearman correlation are at least as high as the current model's, AND on Europe (held out)
and on the pooled weak-label regions (each held out) its harmonised within-1 accuracy and Spearman are higher than
the current model's. Separately, the model is used in a region only where it also beats the rule-based status.

Writes docs/validation/drought_ml.json (always) and backend/fieldshift/models/drought_hgb.{joblib,json} (if adopted).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldshift.data import sources  # noqa: E402
from fieldshift.data.http import get_json  # noqa: E402
from fieldshift.science import drought, drought_ml  # noqa: E402
from fieldshift.science import et0 as et0mod  # noqa: E402

GAZ = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_counties_national.zip"
)
START, END = dt.date(2000, 1, 1), dt.date(2024, 12, 31)
DATA = Path(os.environ.get("FS_GD_DATA", Path.home() / "fs-gdml-data"))
WEAK = ("AUS", "SAM", "AFR", "SAS", "EAS")
REGIONS = ("US", "EU", *WEAK)
ZONES = ("arid", "tropical", "temperate", "cold")
# share of the total training weight per label source, fixed up front (weak labels count less)
SOURCE_SHARE = {"usdm": 0.4, "cdi": 0.4, "smia": 0.2}
HGB = {
    "max_iter": 300,
    "learning_rate": 0.06,
    "max_leaf_nodes": 31,
    "l2_regularization": 1.0,
    "class_weight": "balanced",
    "random_state": 0,
}


def counties(n: int) -> list[dict[str, object]]:
    raw = httpx.get(GAZ, timeout=120, follow_redirects=True).content
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        txt = z.read(z.namelist()[0]).decode("latin-1")
    rows = list(csv.DictReader(io.StringIO(txt), delimiter="\t"))
    out = []
    for r in rows:
        r = {k.strip(): v.strip() for k, v in r.items()}
        st = r["USPS"]
        if st in ("AK", "HI", "PR") or float(r["ALAND"]) < 5e8:
            continue
        out.append(
            {
                "fips": r["GEOID"],
                "state": st,
                "name": r["NAME"],
                "lat": float(r["INTPTLAT"]),
                "lon": float(r["INTPTLONG"]),
            }
        )
    rng = np.random.default_rng(42)
    # stratify: shuffle, then round-robin over states so all regions are represented
    by_state: dict[str, list[dict[str, object]]] = {}
    for c in rng.permutation(np.array(out, dtype=object)):
        by_state.setdefault(str(c["state"]), []).append(c)
    pick: list[dict[str, object]] = []
    while len(pick) < n and any(by_state.values()):
        for st in sorted(by_state):
            if by_state[st] and len(pick) < n:
                pick.append(by_state[st].pop())
    return pick


def climate_zone(aridity: float, coldest_month_t: float) -> str:
    """Köppen main groups, with the UNEP aridity index (P/ET0 < 0.5) standing in for Köppen's dry threshold."""
    if aridity < 0.5:
        return "arid"
    if coldest_month_t >= 18.0:
        return "tropical"
    return "temperate" if coldest_month_t > 0.0 else "cold"


def _labels(path: Path) -> dict[int, list[tuple[dt.date, float]]]:
    z = np.load(path)
    out: dict[int, list[tuple[dt.date, float]]] = {}
    for s, d, v in zip(z["site"], z["date"], z["value"], strict=True):
        out.setdefault(int(s), []).append((dt.date.fromisoformat(str(d)), float(v)))
    return out


def site_samples(job: tuple[int, dict[str, Any], list[tuple[dt.date, float]], list[tuple[dt.date, float]]]) -> dict[str, Any] | None:
    """Features + labels for one site. Dekadal labels are matched to the last day of their dekad."""
    k, s, cdi, smia = job
    cache = DATA / "feat" / f"{s['id']}.npz"
    try:
        if cache.exists():
            return dict(np.load(cache, allow_pickle=True)["d"].item())
        lat, lon = float(s["lat"]), float(s["lon"])
        p = sources.power_daily(lat, lon, START, END)
        doy = np.array([d.timetuple().tm_yday for d in p.dates])
        e0 = et0mod.et0_pm(
            p["T2M_MAX"], p["T2M_MIN"], p["ALLSKY_SFC_SW_DWN"], p["WS2M"], lat, 300.0, doy, tdew=p["T2MDEW"]
        )
        e0 = np.where(np.isfinite(e0), e0, et0mod.et0_hargreaves(p["T2M_MAX"], p["T2M_MIN"], lat, doy))
        rain = np.where(np.isfinite(p["PRECTOTCORR"]), p["PRECTOTCORR"], 0.0)
        X1 = drought_ml.feature_matrix(p.dates, rain, e0, p["T2M_MAX"])
        X2 = drought_ml.feature_matrix_v2(p.dates, rain, e0, p["T2M_MAX"])
        tmean = (p["T2M_MAX"] + p["T2M_MIN"]) / 2
        months = np.array([d.month for d in p.dates])
        coldest = float(min(np.nanmean(tmean[months == m]) for m in range(1, 13)))
        aridity = float(np.nansum(rain) / max(1e-6, np.nansum(e0)))
        zone = climate_zone(aridity, coldest)

        idx, y, cont = [], [], []
        if s["region"] == "US":
            f = get_json(
                "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent",
                {"aoi": s["fips"], "startdate": "1/1/2005", "enddate": "12/31/2024", "statisticsType": 1},
                ttl_s=90 * 86400,
                timeout_s=180,
            )
            for r in f.data:
                idx.append((dt.date.fromisoformat(r["mapDate"][:10]) - START).days)
                y.append(drought_ml.usdm_level(r))
                cont.append(sum(float(r[q]) for q in ("d0", "d1", "d2", "d3", "d4")))  # DSCI
        elif s["region"] == "EU":
            for d, v in cdi:
                idx.append((d - START).days + 9)
                y.append(int(v))
                cont.append(float(v))
        else:
            for d, v in smia:
                idx.append((d - START).days + 9)
                y.append(-1)  # assigned after calibration
                cont.append(-v)  # drier = larger
        # SMIA z at every site (for calibration / label agreement), keyed by the dekad end
        sm_idx = np.array([(d - START).days + 9 for d, _ in smia], dtype=int)
        sm_val = np.array([v for _, v in smia], dtype=float)

        keep = [
            j
            for j, i in enumerate(idx)
            if 400 <= i < len(p.dates) and np.isfinite(X1[i]).all() and np.isfinite(X2[i]).all()
        ]
        ii = np.array([idx[j] for j in keep], dtype=int)
        rules = np.array(
            [
                drought.combined_level(
                    float(X1[i][0]), float(X1[i][1]), float(X1[i][5]), None, None, spei365=float(X1[i][7])
                )[0]
                for i in ii
            ],
            dtype=int,
        )
        out = {
            "k": k,
            "id": s["id"],
            "region": s["region"],
            "label": s["label"],
            "zone": zone,
            "aridity": aridity,
            "coldest": coldest,
            "day": ii,
            "X1": X1[ii].astype(np.float32),
            "X2": X2[ii].astype(np.float32),
            "y": np.array([y[j] for j in keep], dtype=int),
            "cont": np.array([cont[j] for j in keep], dtype=float),
            "rules": rules,
            "sm_day": sm_idx,
            "sm_val": sm_val,
        }
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, d=np.array(out, dtype=object))
        return out
    except Exception as e:  # one failing site must not stop the run
        print("site failed", s.get("id"), repr(e), flush=True)
        return None


# ----------------------------------------------------------------------------------------------- metrics
def harm(level: np.ndarray) -> np.ndarray:
    """Harmonised scale shared by all label systems: 0 None, 1 D0/Watch, 2 D1/Warning, 3 D2+/Alert."""
    return np.minimum(level, 3)


def score(pred: np.ndarray, truth: np.ndarray, cont: np.ndarray | None = None) -> dict[str, float]:
    from scipy import stats

    d1_true, d1_pred = truth >= 2, pred >= 2
    tp, fp, fn = (
        int(np.sum(d1_true & d1_pred)),
        int(np.sum(~d1_true & d1_pred)),
        int(np.sum(d1_true & ~d1_pred)),
    )
    ref = truth if cont is None else cont
    rho = stats.spearmanr(pred, ref).statistic if np.std(pred) > 0 and np.std(ref) > 0 else 0.0
    return {
        "n": int(len(truth)),
        "exact_acc": round(float(np.mean(pred == truth)), 3),
        "within1_acc": round(float(np.mean(np.abs(pred - truth) <= 1)), 3),
        "mae_levels": round(float(np.mean(np.abs(pred - truth))), 3),
        "spearman": round(float(rho), 3),
        "d1_hit_rate": round(tp / max(1, tp + fn), 3),
        "d1_false_alarm_ratio": round(fp / max(1, tp + fp), 3),
    }


def main() -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold

    sites = json.loads((DATA / "sites.json").read_text())
    cdi, smia = _labels(DATA / "labels_cdi.npz"), _labels(DATA / "labels_smia.npz")
    jobs = [(k, s, cdi.get(k, []), smia.get(k, [])) for k, s in enumerate(sites)]
    with ProcessPoolExecutor(max_workers=12) as ex:
        res = [r for r in ex.map(site_samples, jobs) if r is not None and len(r["y"])]
    print("sites with samples", {r: sum(x["region"] == r for x in res) for r in REGIONS}, flush=True)

    # ---- weak-label calibration on the U.S. sites: SMIA z thresholds whose exceedance rates match USDM's
    z_us, lv_us = [], []
    for r in res:
        if r["region"] != "US" or not len(r["sm_day"]):
            continue
        for d, lv in zip(r["day"], r["y"], strict=True):
            j = np.where((r["sm_day"] >= d) & (r["sm_day"] < d + 10))[0]  # the dekad whose end is <= 9 days later
            if len(j):
                z_us.append(r["sm_val"][j[0]])
                lv_us.append(lv)
    z_us_a, lv_us_a = np.array(z_us), np.array(lv_us)
    thresholds = [float(np.quantile(z_us_a, float(np.mean(lv_us_a >= k)))) for k in range(1, 6)]
    print("SMIA thresholds (D0..D4)", [round(t, 2) for t in thresholds], flush=True)

    def smia_level(z: np.ndarray) -> np.ndarray:
        return np.sum(np.stack([z <= t for t in thresholds]), axis=0).astype(int)

    label_quality: dict[str, Any] = {
        "smia_vs_usdm_us": score(harm(smia_level(z_us_a)), harm(lv_us_a)),
    }
    z_eu, lv_eu = [], []
    for r in res:
        if r["region"] == "EU":
            for d, lv in zip(r["day"], r["y"], strict=True):
                j = np.where(r["sm_day"] == d)[0]
                if len(j):
                    z_eu.append(r["sm_val"][j[0]])
                    lv_eu.append(lv)
    if z_eu:
        label_quality["smia_vs_cdi_eu"] = score(harm(smia_level(np.array(z_eu))), harm(np.array(lv_eu)))
    print("label quality", label_quality, flush=True)
    for r in res:
        if r["label"] == "smia":
            r["y"] = smia_level(-r["cont"])

    # ---- stack
    X1 = np.vstack([r["X1"] for r in res])
    X2 = np.vstack([r["X2"] for r in res])
    y = np.concatenate([r["y"] for r in res])
    cont = np.concatenate([r["cont"] for r in res])
    rules = np.concatenate([r["rules"] for r in res])
    site = np.concatenate([[r["k"]] * len(r["y"]) for r in res])
    region = np.concatenate([[r["region"]] * len(r["y"]) for r in res])
    source = np.concatenate([[r["label"]] * len(r["y"]) for r in res])
    zone = np.concatenate([[r["zone"]] * len(r["y"]) for r in res])
    w = np.zeros(len(y))
    for src, share in SOURCE_SHARE.items():
        m = source == src
        w[m] = share * len(y) / max(1, m.sum())
    print("samples", X2.shape, {r: int(np.sum(region == r)) for r in REGIONS}, flush=True)
    print("zones", {z: int(np.sum(zone == z)) for z in ZONES}, flush=True)

    def fit(X: np.ndarray, m: np.ndarray, weighted: bool = True) -> Any:
        return HistGradientBoostingClassifier(**HGB).fit(X[m], y[m], sample_weight=w[m] if weighted else None)

    us = region == "US"
    # ---- current model (v1 features, U.S. only): county CV inside the U.S., then the full-U.S. model elsewhere
    old = np.full(len(y), -1)
    new = np.full(len(y), -1)
    folds = list(GroupKFold(n_splits=5).split(X1[us], y[us], site[us]))
    us_idx = np.where(us)[0]
    for tr, te in folds:
        m = np.zeros(len(y), bool)
        m[us_idx[tr]] = True
        old[us_idx[te]] = fit(X1, m, weighted=False).predict(X1[us_idx[te]])
        m2 = m | ~us  # the new model may also learn from every non-U.S. region
        new[us_idx[te]] = fit(X2, m2).predict(X2[us_idx[te]])
        print("fold done", flush=True)
    old_full = fit(X1, us, weighted=False)
    old[~us] = old_full.predict(X1[~us])
    v2_us_only = fit(X2, us, weighted=False)
    v2us = np.full(len(y), -1)
    v2us[~us] = v2_us_only.predict(X2[~us])

    # ---- leave-one-region-out for every non-U.S. region
    for r in REGIONS[1:]:
        te = region == r
        new[te] = fit(X2, ~te).predict(X2[te])
        print("LORO", r, flush=True)
    # ---- transfer: Europe only -> U.S.
    eu_only_on_us = fit(X2, region == "EU").predict(X2[us])

    # ---- leave-one-climate-zone-out
    lozo = np.full(len(y), -1)
    for z in ZONES:
        te = zone == z
        if te.any() and (~te).any():
            lozo[te] = fit(X2, ~te).predict(X2[te])
            print("LOZO", z, flush=True)

    # ---- report
    def block(m: np.ndarray, native: bool) -> dict[str, Any]:
        c = cont[m] if native else None
        out = {
            "current_model": score(old[m], y[m], c) if native else score(harm(old[m]), harm(y[m])),
            "new_model": score(new[m], y[m], c) if native else score(harm(new[m]), harm(y[m])),
            "rules": score(rules[m], y[m], c) if native else score(harm(rules[m]), harm(y[m])),
        }
        return out

    per_region: dict[str, Any] = {}
    for r in REGIONS:
        m = region == r
        if not m.any():
            continue
        per_region[r] = {
            "n_sites": int(len(np.unique(site[m]))),
            "n_samples": int(m.sum()),
            "label": str(source[m][0]),
            "harmonised": block(m, False),
        }
        if r == "US":
            per_region[r]["native_usdm"] = block(m, True)
            per_region[r]["harmonised"]["europe_only_model"] = score(harm(eu_only_on_us), harm(y[m]))
        else:
            per_region[r]["harmonised"]["v2_trained_on_us_only"] = score(harm(v2us[m]), harm(y[m]))
    weak = np.isin(region, WEAK)
    per_region["WEAK_POOLED"] = {
        "n_sites": int(len(np.unique(site[weak]))),
        "n_samples": int(weak.sum()),
        "label": "smia",
        "harmonised": block(weak, False),
    }
    per_zone: dict[str, Any] = {}
    for z in ZONES:
        m = zone == z
        if m.any():
            per_zone[z] = {
                "n_sites": int(len(np.unique(site[m]))),
                "n_samples": int(m.sum()),
                "regions": {r: int(len(np.unique(site[m & (region == r)]))) for r in REGIONS if (m & (region == r)).any()},
                "new_model_lozo": score(harm(lozo[m]), harm(y[m])),
                "current_model": score(harm(old[m]), harm(y[m])),
                "rules": score(harm(rules[m]), harm(y[m])),
            }

    def beats(a: dict[str, float], b: dict[str, float], strict: bool) -> bool:
        if strict:
            return a["within1_acc"] > b["within1_acc"] and a["spearman"] > b["spearman"]
        return a["within1_acc"] >= b["within1_acc"] and a["spearman"] >= b["spearman"]

    us_n = per_region["US"]["native_usdm"]
    checks = {
        "us_new_at_least_current": beats(us_n["new_model"], us_n["current_model"], strict=False),
        "eu_new_better_than_current": beats(
            per_region["EU"]["harmonised"]["new_model"], per_region["EU"]["harmonised"]["current_model"], True
        ),
        "weak_new_better_than_current": beats(
            per_region["WEAK_POOLED"]["harmonised"]["new_model"],
            per_region["WEAK_POOLED"]["harmonised"]["current_model"],
            True,
        ),
    }
    adopted = all(checks.values())
    # regions where the adopted model also beats the transparent rules (otherwise rules are served there)
    model_regions = [
        r
        for r in REGIONS
        if beats(
            per_region[r]["native_usdm" if r == "US" else "harmonised"]["new_model"],
            per_region[r]["native_usdm" if r == "US" else "harmonised"]["rules"],
            strict=False,
        )
    ]
    print(json.dumps({"checks": checks, "model_regions": model_regions}, indent=1), flush=True)

    import joblib
    import sklearn

    meta: dict[str, Any] = {
        "feature_set": "v2",
        "features": drought_ml.FEATURES_V2,
        "classes": drought_ml.LEVELS,
        "n_sites": int(len(res)),
        "n_samples": int(len(y)),
        "n_counties": int(len(np.unique(site[us]))),
        "regions": {r: per_region[r]["n_sites"] for r in REGIONS if r in per_region},
        "period": "USDM weekly 2005-2024; EDO CDI dekadal 2012-2024; GDO SMIA dekadal 2005-2024; NASA POWER 2000-2024",
        "label_sources": {
            "usdm": "U.S. Drought Monitor county statistics (NDMC/USDA/NOAA, public domain)",
            "cdi": "EDO Combined Drought Indicator v4.1, (c) European Union, CC BY 4.0",
            "smia": "GDO Soil Moisture Index Anomaly v3.0.1, (c) European Union, CC BY 4.0",
        },
        "smia_thresholds_d0_d4": [round(t, 3) for t in thresholds],
        "label_quality": label_quality,
        "source_weight_share": SOURCE_SHARE,
        "hgb": HGB,
        "cv": "U.S.: GroupKFold(5) by county; other regions: leave-one-region-out; zones: leave-one-climate-zone-out",
        "per_region": per_region,
        "per_zone": per_zone,
        "adoption_checks": checks,
        "adopted": bool(adopted),
        "new_model_beats_rules_in": model_regions,
        # where the served model is used; the current model stays U.S.-only if the new one is not adopted
        "model_regions": model_regions if adopted else ["US"],
        # kept for the app's Why text: the U.S. held-out numbers of the model that is served
        "ml_heldout": {
            "within1_acc": us_n["new_model" if adopted else "current_model"]["within1_acc"],
            "spearman_vs_dsci": us_n["new_model" if adopted else "current_model"]["spearman"],
        },
        "sklearn": sklearn.__version__,
        "trained_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "sites": [{"id": r["id"], "region": r["region"], "zone": r["zone"]} for r in res],
    }
    md = ROOT / "backend" / "fieldshift" / "models"
    if adopted:
        final = fit(X2, np.ones(len(y), bool))
        joblib.dump(final, md / "drought_hgb.joblib", compress=3)
        (md / "drought_hgb.json").write_text(json.dumps({k: v for k, v in meta.items() if k != "sites"}, indent=1))
    (ROOT / "docs" / "validation" / "drought_ml.json").write_text(json.dumps(meta, indent=1))
    print("adopted:", adopted, flush=True)


if __name__ == "__main__":
    main()
