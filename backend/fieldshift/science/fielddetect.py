"""Automatic field-boundary detection from a single tap ("tap-to-delineate").

Pipeline (classical computer vision, explainable, CPU-only, ~1–3 s):
  1. Sub-metre RGB imagery around the tap is downsampled to ~2.5–3 m and median-filtered, so in-field texture
     (crop rows, wheel tracks, irrigation borders) disappears while field-scale boundaries (roads, ditches,
     hedges, colour changes between fields) remain.
  2. CIE-Lab colour; graph-based segmentation (Felzenszwalb & Huttenlocher 2004) into ~100 field-scale segments.
  3. The tap is snapped to the calmest pixel nearby (lowest colour gradient), so a tap on a hedge or track still works.
  4. Edge-aware region growing on the segment adjacency: a neighbouring segment joins when its mean colour is close to
     the region's mean (ΔE < 9) AND the boundary it shares with the region is weak (median gradient along the
     shared border below the scene's 90th-percentile gradient). Roads and ditches therefore stop the growth even when
     the same crop continues on the other side.
  5. Fill holes, morphological opening, keep the component with the tap; trace the contour and simplify it
     (Douglas–Peucker) into an editable polygon. Confidence combines boundary contrast and compactness.
Known weakness: smallholder plots made of contrasting strips (terraces, intercropping) may come out as a single strip —
the farmer edits the outline by hand in the app.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import ndimage

T_COLOR = 9.0
EDGE_PCTL = 90.0
EDGE_FLOOR = 5.0


def detect(
    rgb: np.ndarray, seed_rc: tuple[int, int], *, pixel_m: float = 1.0, max_frac: float = 0.5
) -> dict[str, Any] | None:
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
        "params": {"segments": n, "downsample": ds, "t_color": T_COLOR, "edge_pctl": EDGE_PCTL},
    }
