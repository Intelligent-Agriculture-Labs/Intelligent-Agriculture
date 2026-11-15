"""Train the candidate selector of the tap-to-detect pipeline (``fieldshift/science/fielddetect.py``).

1. ``data``: for every orthophoto training window (``build_windows.py``), simulate up to 4 taps inside labelled FTW
   fields. Generate candidates and features with the *production* functions (``edge_maps``, ``candidates``,
   ``feature_matrix``) and record each candidate's IoU with the true field. Cross-fitting: windows of FR+ES are
   scored with an edge model trained on NL+AT only (and vice versa), so the selector sees the noisy edge maps of
   unseen countries, not the over-confident maps of its own training windows.
2. ``train``: gradient-boosted regression trees (scikit-learn) predict candidate IoU. Selection quality is checked
   across countries (FR+ES -> NL+AT and back), then a model on all rows is exported as plain arrays
   (``fieldshift/models/fieldselect.npz``) evaluated by ``fielddetect._predict_iou`` in numpy.

    EDGE=work/fieldedge_B.npz COUNTRIES=france,spain OUT=work/sel_fs.json python selector.py data
    EDGE=work/fieldedge_A.npz COUNTRIES=netherlands,austria OUT=work/sel_na.json python selector.py data
    python selector.py train work/sel_fs.json work/sel_na.json backend/fieldshift/models/fieldselect.npz
"""

from __future__ import annotations

import glob
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from fieldshift.science import fielddetect, fieldedge  # noqa: E402

WORK = Path(os.environ.get("FD_WORK", "~/fd_bench")).expanduser()


def one(f: str) -> list[dict]:
    fieldedge.MODEL_PATH = Path(os.environ["EDGE"]).expanduser()
    fieldedge._weights.cache_clear()
    rng = np.random.default_rng(abs(hash(os.path.basename(f))) % 2**32)
    d = np.load(f)
    img, pxm = d["img"], float(d["pxm"])
    E, b, x, ds = fielddetect.edge_maps(img, pxm)
    h, w = E.shape

    def pool(a, fn):
        return fn(a[: h * ds, : w * ds].reshape(h, ds, w, ds), axis=(1, 3))

    ext = pool(d["ext"] > 0, np.mean) > 0.5
    bnd = pool(d["bnd"] > 0, np.max)
    lab, n = ndimage.label(ext & ~bnd)
    if n == 0:
        return []
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    ok = [i + 1 for i in range(n) if sizes[i] * (ds * pxm) ** 2 >= 400]
    rows = []
    for fid in rng.permutation(ok)[:4]:
        g = lab == fid
        inner = ndimage.binary_erosion(g, iterations=2)
        if not inner.any():
            inner = g
        rr, cc = np.nonzero(inner)
        k = rng.integers(len(rr))
        cands, _ = fielddetect.candidates(E, (int(rr[k]), int(cc[k])))
        if not cands:
            continue
        X = fielddetect.feature_matrix(cands, E, b, x, ds * pxm)
        gd = ndimage.binary_dilation(
            g
        )  # labels exclude boundary pixels; the detector gives them back by dilation
        for (_t, _r, reg), xrow in zip(cands, X, strict=True):
            m = ndimage.binary_dilation(ndimage.binary_fill_holes(reg))
            iou = (m & gd).sum() / max(1, (m | gd).sum())
            rows.append(
                {"x": [float(v) for v in xrow], "iou": float(iou), "grp": f"{os.path.basename(f)}:{fid}"}
            )
    return rows


def cmd_data() -> None:
    cs = os.environ["COUNTRIES"].split(",")
    files = [
        f for f in sorted(glob.glob(str(WORK / "train" / "*.npz"))) if os.path.basename(f).split("_")[0] in cs
    ]
    with ProcessPoolExecutor(int(os.environ.get("WORKERS", 22))) as ex:
        rs = [r for rr in ex.map(one, files, chunksize=4) for r in rr]
    Path(os.environ["OUT"]).write_text(json.dumps(rs))
    print(len(rs), "candidate rows", len({r["grp"] for r in rs}), "taps")


def table(path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rs = json.loads(Path(path).read_text())
    return np.array([r["x"] for r in rs]), np.array([r["iou"] for r in rs]), np.array([r["grp"] for r in rs])


def sel_eval(model, X, y, g) -> tuple[float, float]:
    p = model.predict(X)
    order = np.argsort(g, kind="stable")
    g, p, y = g[order], p[order], y[order]
    starts = np.r_[0, np.nonzero(g[1:] != g[:-1])[0] + 1, len(g)]
    res = [(y[a:b][np.argmax(p[a:b])], y[a:b].max()) for a, b in zip(starts[:-1], starts[1:], strict=True)]
    arr = np.array(res)
    return float(arr[:, 0].mean()), float(arr[:, 1].mean())


def fit(X, y):
    from sklearn.ensemble import (
        GradientBoostingRegressor,
        HistGradientBoostingRegressor,  # noqa: F401  (kept for experiments)
    )

    m = GradientBoostingRegressor(
        n_estimators=int(os.environ.get("NE", 300)),
        max_depth=4,
        learning_rate=0.05,
        subsample=0.5,
        min_samples_leaf=40,
        random_state=0,
    )
    return m.fit(X, y)


def export(m, path: str) -> None:
    trees = [e[0].tree_ for e in m.estimators_]
    n = max(t.node_count for t in trees)

    def pad(a, fill):
        return np.array([np.pad(x, (0, n - len(x)), constant_values=fill) for x in a])

    np.savez_compressed(
        path,
        left=pad([t.children_left for t in trees], -1).astype(np.int16),
        right=pad([t.children_right for t in trees], -1).astype(np.int16),
        feature=pad([t.feature for t in trees], -2).astype(np.int8),
        threshold=pad([t.threshold for t in trees], 0).astype(np.float32),
        value=pad([t.value[:, 0, 0] for t in trees], 0).astype(np.float32),
        lr=np.float32(m.learning_rate),
        init=np.float32(m.init_.constant_[0][0]),
        feats=np.array(fielddetect.FEATS),
    )
    print("exported", path, os.path.getsize(path))


def cmd_train(a_path: str, b_path: str, out: str) -> None:
    A, B = table(a_path), table(b_path)
    report = {}
    for name, tr, te in (("A->B", A, B), ("B->A", B, A)):
        m = fit(tr[0], tr[1])
        s, o = sel_eval(m, *te)
        report[name] = {
            "selected_iou": round(s, 4),
            "oracle_iou": round(o, 4),
            "taps": int(len(np.unique(te[2]))),
        }
        print(name, report[name], flush=True)
    m = fit(np.vstack([A[0], B[0]]), np.concatenate([A[1], B[1]]))
    export(m, out)
    imp = dict(zip(fielddetect.FEATS, np.round(m.feature_importances_, 3).tolist(), strict=True))
    print(json.dumps({"cross_country": report, "importance": imp}))


if __name__ == "__main__":
    if sys.argv[1] == "data":
        cmd_data()
    else:
        cmd_train(*sys.argv[2:5])
