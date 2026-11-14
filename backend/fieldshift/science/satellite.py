"""Field-scale satellite analytics on Sentinel-2 L2A (10 m) NDVI.

* Cloud/shadow masking with the Scene Classification Layer (SCL classes 4 vegetation, 5 bare soil, 6 water).
* Time-series smoothing: daily linear gap-filling + Savitzky–Golay filter (Chen et al. 2004).
* Phenology: green-up / senescence at 50 % of the seasonal NDVI amplitude (TIMESAT "seasonal amplitude"
  method, Jönsson & Eklundh 2004); peak = maximum; bare periods = smoothed NDVI < 0.20 for ≥ 20 days;
  season type from the number of prominent peaks (scipy find_peaks, prominence ≥ 0.15).
* Satellite basal crop coefficient: fractional cover from scaled NDVI (Gutman & Ignatov 1998), then the FAO-56
  density-coefficient approach (Allen & Pereira 2009): Kcb = Kc_min + (Kcb_full − Kc_min) · min(1, ML·fc, fc^(1/(1+h))).
* Management zones (unsupervised ML): k-means (k = 2…4 chosen by silhouette score, Rousseeuw 1987) on
  standardized per-pixel features: mean NDVI, peak NDVI, temporal NDVI variability, slope, wetness (TWI).
  This is the standard "management zone delineation" approach in precision agriculture (Fridgen et al. 2004).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
from scipy.signal import find_peaks, savgol_filter

VALID_SCL = (4, 5, 6)
ZONE_COLORS = ["#1a9850", "#a6d96a", "#fdae61", "#d73027"]  # high → low vigour
PALETTES = {
    2: [ZONE_COLORS[0], ZONE_COLORS[3]],
    3: [ZONE_COLORS[0], ZONE_COLORS[2], ZONE_COLORS[3]],
    4: ZONE_COLORS,
}


def ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        v = (nir - red) / (nir + red)
    return np.where(np.isfinite(v), np.clip(v, -1, 1), np.nan)


def smooth_series(dates: list[dt.date], values: list[float]) -> tuple[list[dt.date], np.ndarray]:
    """Daily linear interpolation between clear observations, then Savitzky–Golay (window ~31 d, order 2)."""
    if len(dates) < 3:
        return dates, np.array(values, float)
    d0 = dates[0]
    x = np.array([(d - d0).days for d in dates], float)
    y = np.array(values, float)
    xd = np.arange(0, x[-1] + 1)
    yd = np.interp(xd, x, y)
    win = min(31, len(xd) - (1 - len(xd) % 2))
    if win >= 5:
        yd = savgol_filter(yd, window_length=win if win % 2 else win - 1, polyorder=2)
    return [d0 + dt.timedelta(days=int(k)) for k in xd], np.clip(yd, -0.2, 1.0)


def phenology(days: list[dt.date], sm: np.ndarray) -> dict[str, Any]:
    out: dict[str, Any] = {
        "greenup": None,
        "peak": None,
        "peak_ndvi": None,
        "senescence": None,
        "bare_periods": [],
        "season_type": "unknown",
    }
    if len(sm) < 30:
        return out
    k = int(np.argmax(sm))
    lo, hi = float(np.percentile(sm, 5)), float(sm[k])
    out["peak"], out["peak_ndvi"] = days[k].isoformat(), round(hi, 3)
    thr = lo + 0.5 * (hi - lo)
    before = np.where(sm[:k] < thr)[0]
    after = np.where(sm[k:] < thr)[0]
    if len(before):
        out["greenup"] = days[int(before[-1]) + 1].isoformat()
    if len(after):
        out["senescence"] = days[k + int(after[0])].isoformat()
    bare = sm < 0.20
    start = None
    for i, b in enumerate(np.append(bare, False)):
        if b and start is None:
            start = i
        elif not b and start is not None:
            if i - start >= 20:
                out["bare_periods"].append({"start": days[start].isoformat(), "end": days[i - 1].isoformat()})
            start = None
    peaks, _ = find_peaks(sm, prominence=0.15, distance=20)
    if hi < 0.3:
        out["season_type"] = "bare / fallow or sparse cover"
    elif len(peaks) >= 3:
        out["season_type"] = f"{len(peaks)} growth cycles (e.g. repeated cuttings)"
    elif len(peaks) == 2:
        out["season_type"] = "double crop (two seasons)"
    elif lo > 0.4:
        out["season_type"] = "perennial / continuously green"
    else:
        out["season_type"] = "single season"
    return out


def kcb_from_ndvi(
    ndvi_value: float,
    kcb_full: float,
    crop_height_m: float = 1.0,
    ndvi_soil: float = 0.15,
    ndvi_veg: float = 0.85,
) -> float:
    """FAO-56 density coefficient (Allen & Pereira 2009) with fc from scaled NDVI."""
    fc = float(np.clip((ndvi_value - ndvi_soil) / (ndvi_veg - ndvi_soil), 0.0, 1.0))
    kc_min = 0.15
    kd = min(1.0, 1.5 * fc, fc ** (1.0 / (1.0 + crop_height_m))) if fc > 0 else 0.0
    return round(kc_min + (kcb_full - kc_min) * kd, 3)


def management_zones(
    stack: np.ndarray, mask: np.ndarray, slope: np.ndarray | None, twi: np.ndarray | None, seed: int = 0
) -> dict[str, Any] | None:
    """k-means zoning. stack: (n_scenes, H, W) NDVI with NaN for cloud. Returns label map (−1 outside field)."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    n_valid = np.sum(np.isfinite(stack), axis=0)
    use = mask & (n_valid >= max(3, stack.shape[0] // 3))
    if use.sum() < 30:
        return None
    with np.errstate(all="ignore"):
        mean = np.nanmean(stack, axis=0)
        peak = np.nanpercentile(stack, 90, axis=0)
        cv = np.nanstd(stack, axis=0)
    feats = [mean[use], peak[use], cv[use]]
    names = ["mean NDVI", "peak NDVI", "NDVI variability"]
    if slope is not None:
        feats.append(slope[use])
        names.append("slope")
    if twi is not None:
        feats.append(twi[use])
        names.append("wetness")
    X = np.column_stack(feats)
    X = (X - X.mean(0)) / np.where(X.std(0) > 1e-9, X.std(0), 1.0)
    rng = np.random.default_rng(seed)
    sample = rng.choice(len(X), size=min(3000, len(X)), replace=False)
    best: tuple[float, int, Any] | None = None
    for k in (2, 3, 4):
        if len(X) < 10 * k:
            continue
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)
        s = (
            float(silhouette_score(X[sample], km.labels_[sample]))
            if len(set(km.labels_[sample])) > 1
            else -1.0
        )
        if best is None or s > best[0] + 0.02:  # prefer fewer zones unless clearly better separated
            best = (s, k, km)
    if best is None:
        return None
    sil, k, km = best
    labels = km.labels_
    # order zones by mean NDVI (0 = highest vigour)
    zmeans = [float(np.nanmean(mean[use][labels == z])) for z in range(k)]
    order = np.argsort(zmeans)[::-1]
    rank = {int(z): r for r, z in enumerate(order)}
    lab_map = np.full(mask.shape, -1, dtype=int)
    lab_map[use] = [rank[int(z)] for z in labels]
    zones = []
    names_by_k = {
        2: ["Higher vigour", "Lower vigour"],
        3: ["High vigour", "Medium vigour", "Low vigour"],
        4: ["High vigour", "Medium-high vigour", "Medium-low vigour", "Low vigour"],
    }
    for r, z in enumerate(order):
        sel = labels == z
        zinfo: dict[str, Any] = {
            "rank": r,
            "label": names_by_k[k][r],
            "color": PALETTES[k][r],
            "share_pct": round(100 * float(sel.mean()), 1),
            "ndvi_mean": round(zmeans[int(z)], 3),
            "ndvi_cv": round(float(np.nanmean(cv[use][sel])), 3),
        }
        if slope is not None:
            zinfo["slope_pct"] = round(float(np.nanmean(slope[use][sel])), 2)
        if twi is not None:
            zinfo["twi"] = round(float(np.nanmean(twi[use][sel])), 2)
        zones.append(zinfo)
    return {"labels": lab_map, "zones": zones, "k": k, "silhouette": round(sil, 3), "features": names}


def zone_advice(zones: list[dict[str, Any]], twi_field_mean: float | None) -> list[str]:
    adv = []
    if len(zones) < 2:
        return ["The field is fairly uniform; manage it as one unit."]
    hi, lo = zones[0], zones[-1]
    gap = hi["ndvi_mean"] - lo["ndvi_mean"]
    adv.append(
        f"Vigour differs by {gap:.2f} NDVI between the best ({hi['share_pct']} % of the field) and the weakest zone ({lo['share_pct']} %)."
    )
    if twi_field_mean is not None and lo.get("twi") is not None and lo["twi"] > twi_field_mean + 0.5:
        adv.append(
            "The weak zone sits where water collects: check for waterlogging, drainage or salinity before adding inputs."
        )
    elif lo.get("slope_pct") is not None and lo["slope_pct"] > (hi.get("slope_pct") or 0) + 1:
        adv.append(
            "The weak zone is on steeper ground: likely thinner soil and erosion — keep it covered and consider lower seeding rates."
        )
    else:
        adv.append(
            "Take separate soil samples in each zone: weak vigour often traces back to compaction, pH or nutrient patches."
        )
    adv.append(
        "Use the zones for variable-rate seeding/fertiliser or targeted scouting; walk the weakest zone first."
    )
    if lo["ndvi_cv"] > hi["ndvi_cv"] + 0.05:
        adv.append(
            "The weak zone is also the most variable over time — a sign of stress in dry spells (water-holding capacity)."
        )
    return adv


def harvest_events(
    dates: list[dt.date], values: list[float], min_drop: float = 0.2, max_gap_days: int = 25
) -> list[str]:
    """Cuttings/harvests seen from space: NDVI falls by >= min_drop between consecutive clear scenes <= max_gap_days apart
    from a green canopy (NDVI >= 0.5). Returns the midpoint date of each drop."""
    out = []
    for (d0, v0), (d1, v1) in zip(
        zip(dates, values, strict=True), zip(dates[1:], values[1:], strict=True), strict=False
    ):
        if v0 >= 0.5 and v0 - v1 >= min_drop and (d1 - d0).days <= max_gap_days:
            out.append((d0 + (d1 - d0) / 2).isoformat())
    return out
