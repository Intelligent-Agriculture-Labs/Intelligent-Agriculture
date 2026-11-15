"""Automatic field-boundary detection from a single tap ("tap-to-delineate").

v3 (default, EXP-13): learned edge map + candidate selection. CPU-only, ~0.5–1.5 s.
  1. Sub-metre RGB imagery around the tap is downsampled to ~2.7 m (Lanczos), which removes crop rows and wheel tracks.
  2. A tiny U-Net (``fieldedge.py``) predicts, per pixel, the probability of a field boundary B and of field
     interior X. It was trained on Fields of The World (FTW) polygons over open orthophotos of four countries only.
     The cost map is E = B + 0.5 (1 − X).
  3. Candidate regions: flood fills from the tap over {E ≤ t} for 24 thresholds t (quantiles of E), each also after
     a morphological opening of radius 0–3 px. Openings cut thin leaks through hedge gaps and farm tracks, and the
     threshold sweep makes the method scale-adaptive: small plots and 100 ha fields come from the same sweep.
  4. Each candidate is described by 14 shape and contrast features: area, solidity, compactness, boundary
     probability on its rim vs. inside, interior probability, threshold, opening radius, and so on. A small
     gradient-boosted tree model (``fieldselect.npz``, trained on the same four countries) predicts the candidate's
     IoU with the true field. The best candidate maximises predicted IoU + 0.3 x rim contrast x solidity², a small
     prior that keeps large uniform fields whole. The predicted IoU is the reported confidence.
  5. Fill holes, give back the 1-pixel boundary, close slits (radius 2 px), trace and simplify (Douglas–Peucker)
     into an editable polygon.
v2 (fallback when the model files are missing): Felzenszwalb segmentation + edge-aware region growing
(``detect_classical``; EXP-10).
Measured accuracy worldwide: docs/VALIDATION.md (V8). Smallholder plots remain the hardest case, and the polygon is
always editable in the app.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from . import fieldedge

T_COLOR = 9.0
EDGE_PCTL = 90.0
EDGE_FLOOR = 5.0

TARGET_M = 2.7  # working resolution (m/pixel)
LAM = 0.5  # weight of (1 − interior probability) in the cost map
N_THRESH = 24
Q_LO, Q_HI = 0.20, 0.98
MAX_OPEN = 3
# weight of the rim-contrast x solidity² prior added to the predicted IoU (tuned on DEV countries)
HAND_W = 0.3
CLOSE_R = 2  # final morphological closing radius (working pixels)
SELECT_PATH = Path(__file__).resolve().parents[1] / "models" / "fieldselect.npz"
FEATS = (
    "log_a",
    "sol",
    "cmp",
    "bring",
    "bin",
    "xin",
    "xring",
    "ering",
    "ein",
    "touch",
    "t",
    "r",
    "rel_a",
    "t_rank",
)


def detect(
    rgb: np.ndarray, seed_rc: tuple[int, int], *, pixel_m: float = 1.0, max_frac: float = 0.45
) -> dict[str, Any] | None:
    """Field polygon (input-pixel row/col) around the tapped pixel, or None. Uses the learned pipeline when the model
    files are present, otherwise the classical one."""
    if fieldedge.available():
        res = detect_learned(rgb, seed_rc, pixel_m=pixel_m, max_frac=max_frac)
        if res is not None:
            return res
    return detect_classical(rgb, seed_rc, pixel_m=pixel_m)


@lru_cache(maxsize=1)
def _selector() -> dict[str, np.ndarray] | None:
    if not SELECT_PATH.exists():
        return None
    with np.load(SELECT_PATH) as z:
        sel = {k: z[k] for k in z.files}
    if tuple(str(f) for f in sel["feats"]) != FEATS:
        return None
    return sel


def _predict_iou(X: np.ndarray) -> np.ndarray | None:
    """Gradient-boosted regression trees (exported from scikit-learn) evaluated in numpy."""
    s = _selector()
    if s is None:
        return None
    left, right, feat, thr, val = s["left"], s["right"], s["feature"], s["threshold"], s["value"]
    out = np.full(len(X), float(s["init"]))
    rows = np.arange(len(X))
    for k in range(left.shape[0]):
        node = np.zeros(len(X), dtype=np.int64)
        while True:
            f = feat[k, node].astype(np.int64)
            leaf = f < 0
            if leaf.all():
                break
            go_left = X[rows, np.maximum(f, 0)] <= thr[k, node]
            nxt = np.where(go_left, left[k, node], right[k, node])
            node = np.where(leaf, node, nxt)
        out += float(s["lr"]) * val[k, node]
    return out


def _disk(r: int) -> np.ndarray:
    y, x = np.ogrid[-r : r + 1, -r : r + 1]
    return np.asarray(x * x + y * y <= r * r)


def _features(reg: np.ndarray, E: np.ndarray, b: np.ndarray, x: np.ndarray) -> dict[str, float]:
    from skimage.morphology import convex_hull_image

    rows, cols = np.nonzero(reg)
    r0, r1 = max(0, rows.min() - 3), min(reg.shape[0], rows.max() + 4)
    c0, c1 = max(0, cols.min() - 3), min(reg.shape[1], cols.max() + 4)
    sub = _fill_holes(reg[r0:r1, c0:c1])
    ring = ndimage.binary_dilation(sub, iterations=2) & ~sub
    Es, bs, xs = E[r0:r1, c0:c1], b[r0:r1, c0:c1], x[r0:r1, c0:c1]
    a = float(sub.sum())
    perim = max(1.0, ring.sum() / 2.0)
    touch = (
        rows.min() == 0 or cols.min() == 0 or rows.max() == reg.shape[0] - 1 or cols.max() == reg.shape[1] - 1
    )
    return {
        "a": a,
        "sol": a / max(1.0, float(convex_hull_image(sub).sum())),
        "cmp": min(1.0, 4 * np.pi * a / perim**2),
        "bring": float(bs[ring].mean()) if ring.any() else 0.0,
        "bin": float(bs[sub].mean()),
        "xin": float(xs[sub].mean()),
        "xring": float(xs[ring].mean()) if ring.any() else 0.0,
        "ering": float(Es[ring].mean()) if ring.any() else 0.0,
        "ein": float(Es[sub].mean()),
        "touch": float(touch),
    }


def edge_maps(rgb: np.ndarray, pixel_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, int] | None:
    """Downsample to ~TARGET_M and run the edge model: (cost map E, boundary prob, interior prob, downsample factor)."""
    from PIL import Image

    ds = max(1, int(round(TARGET_M / max(pixel_m, 0.1))))
    h0, w0 = rgb.shape[:2]
    small = np.asarray(Image.fromarray(rgb).resize((w0 // ds, h0 // ds), Image.Resampling.LANCZOS))
    pred = fieldedge.predict(small)
    if pred is None:
        return None
    b, x = pred
    return b + LAM * (1.0 - x), b, x, ds


def candidates(
    E: np.ndarray, seed: tuple[int, int], max_frac: float = 0.45
) -> tuple[list[tuple[float, int, np.ndarray]], tuple[int, int]]:
    """Flood fills from the (snapped) seed over {E <= t} for a sweep of thresholds, each also after an opening."""
    sr, sc = min(seed[0], E.shape[0] - 1), min(seed[1], E.shape[1] - 1)
    r0, c0 = max(0, sr - 3), max(0, sc - 3)
    win = E[r0 : sr + 4, c0 : sc + 4]
    dr, dc = np.unravel_index(int(np.argmin(win)), win.shape)
    sr, sc = r0 + int(dr), c0 + int(dc)
    out: list[tuple[float, int, np.ndarray]] = []
    H, W = E.shape
    for t in np.quantile(E, np.linspace(Q_LO, Q_HI, N_THRESH)):
        low = np.less_equal(E, t)
        if not low[sr, sc]:
            continue
        lab, _ = ndimage.label(low)
        comp = lab == lab[sr, sc]
        sl = ndimage.find_objects(comp.astype(np.int8))[0]
        for r in range(MAX_OPEN + 1):
            if r == 0:
                reg = comp
            else:
                # opening(low) restricted to the tap's component == opening(component): open only its bounding box
                a0, a1 = max(0, sl[0].start - r - 1), min(H, sl[0].stop + r + 1)
                b0, b1 = max(0, sl[1].start - r - 1), min(W, sl[1].stop + r + 1)
                op = ndimage.binary_opening(comp[a0:a1, b0:b1], structure=_disk(r))
                lab2, _ = ndimage.label(op)
                k = lab2[sr - a0, sc - b0]
                if k == 0:
                    continue
                reg = np.zeros_like(comp)
                reg[a0:a1, b0:b1] = lab2 == k
            a = int(reg.sum())
            if a > max_frac * E.size or a < 6:
                continue
            out.append((float(t), r, reg))
    return out, (sr, sc)


def _fill_holes(m: np.ndarray) -> np.ndarray:
    """Same result as ndimage.binary_fill_holes (4-connected background), in one labelling pass."""
    lab, n = ndimage.label(~m)
    if n == 0:
        return m.copy()
    keep = np.zeros(n + 1, dtype=bool)
    keep[0] = True
    keep[np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])] = True
    return np.asarray(m | ~keep[lab])


def feature_matrix(
    cands: list[tuple[float, int, np.ndarray]], E: np.ndarray, b: np.ndarray, x: np.ndarray, m_per_px: float
) -> np.ndarray:
    """One row of FEATS per candidate (identical code at training and inference time)."""
    cache: dict[tuple[int, ...], dict[str, float]] = {}
    feats: list[dict[str, float]] = []
    for _t, _r, reg in cands:
        rows, cols = np.nonzero(reg)
        key = (len(rows), int(rows.min()), int(rows.max()), int(cols.min()), int(cols.max()))
        if key not in cache:
            cache[key] = _features(reg, E, b, x)
        feats.append(cache[key])
    la = np.log10(np.maximum(1.0, np.array([f["a"] for f in feats]) * m_per_px**2))
    ts = sorted({c[0] for c in cands})
    med = float(np.median(la))
    return np.array(
        [
            [
                *(
                    la[i],
                    f["sol"],
                    f["cmp"],
                    f["bring"],
                    f["bin"],
                    f["xin"],
                    f["xring"],
                    f["ering"],
                    f["ein"],
                ),
                *(f["touch"], cands[i][0], float(cands[i][1]), la[i] - med),
                ts.index(cands[i][0]) / max(1, len(ts) - 1),
            ]
            for i, f in enumerate(feats)
        ]
    )


def detect_learned(
    rgb: np.ndarray, seed_rc: tuple[int, int], *, pixel_m: float = 1.0, max_frac: float = 0.45
) -> dict[str, Any] | None:
    from skimage.measure import approximate_polygon, find_contours

    maps = edge_maps(rgb, pixel_m)
    if maps is None:
        return None
    E, b, x, ds = maps
    cands, _ = candidates(E, (seed_rc[0] // ds, seed_rc[1] // ds), max_frac)
    if not cands:
        return None
    X = feature_matrix(cands, E, b, x, ds * pixel_m)
    pred_iou = _predict_iou(X)
    if (
        pred_iou is None
    ):  # hand-made score if the selector file is missing: rim-vs-interior contrast x convexity
        e_ring, e_in, sol = X[:, 7], X[:, 8], X[:, 1]
        score = (e_ring - e_in) / (e_ring + e_in + 1e-6) * sol
    else:
        # Learned IoU + a small prior for strong, convex rims. The selector saw few > 40 ha fields (EXP-13), and the
        # prior keeps large uniform fields whole (Ames demo field).
        score = pred_iou + HAND_W * (X[:, 3] - X[:, 4]) * X[:, 1] ** 2
    i = int(np.argmax(score))
    t_best, r_best, best = cands[i]

    mask = _fill_holes(best)
    mask = ndimage.binary_dilation(mask, iterations=1)  # boundary pixels belong half to each side
    pad = CLOSE_R + 1  # closing removes slits along internal borders (irrigation checks, tramlines)
    mask = ndimage.binary_closing(np.pad(mask, pad), structure=_disk(CLOSE_R))[pad:-pad, pad:-pad]
    mask = _fill_holes(mask)
    touches = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
    contours = find_contours(np.pad(mask, 1).astype(float), 0.5)
    if not contours:
        return None
    cont = max(contours, key=len) - 1
    poly = approximate_polygon(cont, tolerance=1.0) * ds
    if pred_iou is not None:
        conf = float(np.clip(pred_iou[i], 0.05, 0.95))
    else:
        conf = float(np.clip(0.2 + 0.6 * score[i], 0.05, 0.95))
    if touches:
        conf = max(0.05, conf - 0.2)
    return {
        "polygon_rc": poly.tolist(),
        "area_px": float(mask.sum()) * ds * ds,
        "confidence": round(conf, 2),
        "touches_border": touches,
        "params": {
            "method": "learned",
            "downsample": ds,
            "candidates": len(cands),
            "threshold": round(t_best, 3),
            "opening_px": r_best,
            "predicted_iou": None if pred_iou is None else round(float(pred_iou[i]), 3),
        },
    }


def detect_classical(
    rgb: np.ndarray, seed_rc: tuple[int, int], *, pixel_m: float = 1.0, max_frac: float = 0.5
) -> dict[str, Any] | None:
    """v2 (EXP-10): Felzenszwalb segments + edge-aware region growing. Used when the learned model is unavailable."""
    from PIL import Image
    from skimage.color import rgb2lab
    from skimage.filters import sobel
    from skimage.measure import approximate_polygon, find_contours
    from skimage.segmentation import felzenszwalb

    ds = max(1, int(round(2.7 / max(pixel_m, 0.1))))
    h0, w0 = rgb.shape[:2]
    small = np.asarray(Image.fromarray(rgb).resize((w0 // ds, h0 // ds), Image.Resampling.LANCZOS)).astype(
        np.float64
    )
    small = ndimage.median_filter(small, size=(5, 5, 1))
    lab = rgb2lab(small / 255.0)
    seg = felzenszwalb(lab, scale=300, sigma=0.8, min_size=max(20, int(1600 / ds**2)))
    grad = np.sqrt(sum(sobel(lab[..., c]) ** 2 for c in range(3)))
    sr, sc = min(seed_rc[0] // ds, seg.shape[0] - 1), min(seed_rc[1] // ds, seg.shape[1] - 1)
    r0, c0 = max(0, sr - 4), max(0, sc - 4)
    win = grad[r0 : sr + 5, c0 : sc + 5]
    dr, dc = np.unravel_index(int(np.argmin(win)), win.shape)
    sr, sc = r0 + int(dr), c0 + int(dc)

    n = int(seg.max()) + 1
    cnt = np.bincount(seg.ravel(), minlength=n).astype(float)
    means = np.stack(
        [
            np.bincount(seg.ravel(), weights=lab[..., c].ravel(), minlength=n) / np.maximum(cnt, 1)
            for c in range(3)
        ],
        1,
    )
    gthr = max(
        float(np.percentile(grad, EDGE_PCTL)), EDGE_FLOOR
    )  # floor: weak internal lines (borders, tracks) never stop growth
    region = {int(seg[sr, sc])}
    limit = max_frac * seg.size
    changed = True
    while changed:
        changed = False
        m = np.isin(seg, list(region))
        ring = ndimage.binary_dilation(m) & ~m
        idx = list(region)
        mu = (means[idx] * cnt[idx, None]).sum(0) / cnt[idx].sum()
        for nb in np.unique(seg[ring]):
            nb = int(nb)
            band = ndimage.binary_dilation(ring & (seg == nb)) & (m | (seg == nb))
            bstr = float(np.median(grad[band])) if band.any() else 0.0
            if np.linalg.norm(means[nb] - mu) < T_COLOR and bstr < gthr and cnt[nb] < max_frac * seg.size:
                region.add(nb)
                changed = True
        if cnt[list(region)].sum() > limit:
            break
    mask = ndimage.binary_fill_holes(np.isin(seg, list(region)))
    mask = ndimage.binary_opening(mask, structure=np.ones((3, 3)))
    lab_cc, _ = ndimage.label(mask)
    if lab_cc[sr, sc] == 0:
        return None
    mask = lab_cc == lab_cc[sr, sc]
    touches = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
    contours = find_contours(np.pad(mask, 1).astype(float), 0.5)
    if not contours:
        return None
    cont = max(contours, key=len) - 1
    poly = approximate_polygon(cont, tolerance=2.0) * ds  # back to input-pixel coordinates
    ring_px = ndimage.binary_dilation(mask, iterations=2) & ~mask
    inner = ndimage.binary_erosion(mask, iterations=2)
    contrast = (
        float(np.linalg.norm(lab[ring_px].mean(0) - lab[inner].mean(0)))
        if ring_px.any() and inner.any()
        else 0.0
    )
    area_px = float(mask.sum()) * ds * ds
    perim = float(np.sum(np.hypot(*np.diff(cont, axis=0).T))) * ds
    compact = 4 * np.pi * area_px / max(1.0, perim**2)
    conf = float(np.clip(0.2 + contrast / 30.0 + 0.4 * compact - (0.3 if touches else 0.0), 0.05, 0.95))
    return {
        "polygon_rc": poly.tolist(),
        "area_px": area_px,
        "confidence": round(conf, 2),
        "touches_border": touches,
        "params": {
            "method": "classical",
            "segments": n,
            "downsample": ds,
            "t_color": T_COLOR,
            "edge_pctl": EDGE_PCTL,
        },
    }
