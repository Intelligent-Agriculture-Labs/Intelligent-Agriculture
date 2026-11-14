"""Train and evaluate the FieldShift ML drought classifier (run on the data box: 24 cores, fast internet).

    backend/.venv/bin/python scripts/train_drought_ml.py [n_counties=80]

Data: U.S. Census county centroids → NASA POWER daily (2000–2024) per county → weekly USDM county statistics (2005–2024).
Model: sklearn HistGradientBoostingClassifier (class-balanced) on fieldshift.science.drought_ml.FEATURES.
Evaluation: 5-fold GroupKFold by county (unseen locations) vs. the rule-based status (drought.combined_level v2)
on exactly the same samples. Writes backend/fieldshift/models/drought_hgb.{joblib,json} and docs/validation/drought_ml.json.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

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


def county_samples(c: dict[str, object]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]] | None:
    try:
        lat, lon = float(c["lat"]), float(c["lon"])  # type: ignore[arg-type]
        p = sources.power_daily(lat, lon, START, END)
        doy = np.array([d.timetuple().tm_yday for d in p.dates])
        e0 = et0mod.et0_pm(
            p["T2M_MAX"], p["T2M_MIN"], p["ALLSKY_SFC_SW_DWN"], p["WS2M"], lat, 300.0, doy, tdew=p["T2MDEW"]
        )
        e0 = np.where(np.isfinite(e0), e0, et0mod.et0_hargreaves(p["T2M_MAX"], p["T2M_MIN"], lat, doy))
        rain = np.where(np.isfinite(p["PRECTOTCORR"]), p["PRECTOTCORR"], 0.0)
        X = drought_ml.feature_matrix(p.dates, rain, e0, p["T2M_MAX"])
        f = get_json(
            "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent",
            {"aoi": c["fips"], "startdate": "1/1/2005", "enddate": "12/31/2024", "statisticsType": 1},
            ttl_s=90 * 86400,
            timeout_s=180,
        )
        xs, ys, base, dsci = [], [], [], []
        for r in f.data:
            d = dt.date.fromisoformat(r["mapDate"][:10])
            i = (d - START).days
            if i < 400 or i >= len(p.dates) or not np.isfinite(X[i]).all():
                continue
            xs.append(X[i])
            ys.append(drought_ml.usdm_level(r))
            s30, s90, se90, se365 = X[i][0], X[i][1], X[i][5], X[i][7]
            base.append(
                drought.combined_level(float(s30), float(s90), float(se90), None, None, spei365=float(se365))[
                    0
                ]
            )
            dsci.append(sum(float(r[k]) for k in ("d0", "d1", "d2", "d3", "d4")))
        if not xs:
            return None
        return np.array(xs), np.array(ys), np.array([base, dsci]).T, [int(str(c["fips"]))] * len(xs)
    except Exception as e:
        print("county failed", c.get("fips"), e, flush=True)
        return None


def main() -> None:
    from scipy import stats
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    cs = counties(n)
    print("counties", len(cs), flush=True)
    with ProcessPoolExecutor(max_workers=12) as ex:
        res = [r for r in ex.map(county_samples, cs) if r is not None]
    X = np.vstack([r[0] for r in res])
    y = np.concatenate([r[1] for r in res])
    B = np.vstack([r[2] for r in res])
    g = np.concatenate([r[3] for r in res])
    print("samples", X.shape, "class counts", np.bincount(y, minlength=6).tolist(), flush=True)

    def score(pred: np.ndarray, truth: np.ndarray, dsci: np.ndarray) -> dict[str, float]:
        d1_true, d1_pred = truth >= 2, pred >= 2
        tp, fp, fn = (
            int(np.sum(d1_true & d1_pred)),
            int(np.sum(~d1_true & d1_pred)),
            int(np.sum(d1_true & ~d1_pred)),
        )
        return {
            "exact_acc": round(float(np.mean(pred == truth)), 3),
            "within1_acc": round(float(np.mean(np.abs(pred - truth) <= 1)), 3),
            "mae_levels": round(float(np.mean(np.abs(pred - truth))), 3),
            "spearman_vs_dsci": round(float(stats.spearmanr(pred, dsci).statistic), 3),
            "d1_hit_rate": round(tp / max(1, tp + fn), 3),
            "d1_false_alarm_ratio": round(fp / max(1, tp + fp), 3),
        }

    oof = np.zeros(len(y), int)
    for tr, te in GroupKFold(n_splits=5).split(X, y, g):
        m = HistGradientBoostingClassifier(
            max_iter=300,
            learning_rate=0.06,
            max_leaf_nodes=31,
            l2_regularization=1.0,
            class_weight="balanced",
            random_state=0,
        )
        m.fit(X[tr], y[tr])
        oof[te] = m.predict(X[te])
    ml = score(oof, y, B[:, 1])
    rules = score(B[:, 0].astype(int), y, B[:, 1])
    print("ML   (held-out counties)", ml, flush=True)
    print("RULES                   ", rules, flush=True)
    better = ml["within1_acc"] > rules["within1_acc"] and ml["spearman_vs_dsci"] >= rules["spearman_vs_dsci"]
    final = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.06,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        class_weight="balanced",
        random_state=0,
    ).fit(X, y)
    import joblib
    import sklearn

    md = ROOT / "backend" / "fieldshift" / "models"
    md.mkdir(parents=True, exist_ok=True)
    meta = {
        "features": drought_ml.FEATURES,
        "classes": drought_ml.LEVELS,
        "n_counties": len(res),
        "n_samples": int(len(y)),
        "period": "2005-2024 weekly USDM; NASA POWER 2000-2024",
        "cv": "GroupKFold(5) by county",
        "ml_heldout": ml,
        "rules_same_samples": rules,
        "adopted": bool(better),
        "sklearn": sklearn.__version__,
        "trained_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "counties": [c["fips"] for c in cs],
    }
    if better:
        joblib.dump(final, md / "drought_hgb.joblib", compress=3)
        (md / "drought_hgb.json").write_text(json.dumps(meta, indent=1))
    (ROOT / "docs" / "validation").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "validation" / "drought_ml.json").write_text(json.dumps(meta, indent=1))
    print("adopted:", better, flush=True)


if __name__ == "__main__":
    main()
