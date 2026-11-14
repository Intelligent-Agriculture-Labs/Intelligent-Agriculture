"""ML drought classifier: gradient-boosted trees trained on 20 years of U.S. Drought Monitor county maps with
features computed from NASA POWER (multi-scale SPI/SPEI, temperature anomalies, seasonality, aridity).

The SAME feature code is used for training (scripts/train_drought_ml.py) and serving (advice), so there is no
train/serve skew. The model is only used in regions where held-out validation showed it beats the rule-based status
(listed in the model metadata); elsewhere the transparent rule-based status (drought.combined_level) is used.
"""

from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
WINDOWS = (30, 90, 180, 365)
FEATURES = [
    *(f"spi{n}" for n in WINDOWS),
    *(f"spei{n}" for n in WINDOWS),
    "tmax_anom30",
    "tmax_anom90",
    "doy_sin",
    "doy_cos",
    "aridity",
]
LEVELS = ["None", "D0", "D1", "D2", "D3", "D4"]


def _rolling(x: np.ndarray, n: int) -> np.ndarray:
    x = np.where(np.isfinite(x), x, 0.0)
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.full(len(x), np.nan)
    out[n - 1 :] = c[n:] - c[:-n]
    return out


def _week_bins(dates: list[dt.date]) -> np.ndarray:
    return np.array([min(51, (d.timetuple().tm_yday - 1) // 7) for d in dates])


def spi_series(precip: np.ndarray, dates: list[dt.date], n: int, gamma: bool = True) -> np.ndarray:
    """Vectorised standardized index for every day: per week-of-year bin, fit once across years.
    gamma=True: SPI (gamma + zero mixture); False: empirical normal scores (SPEI-like for P−ET0)."""
    acc = _rolling(precip, n)
    wk = _week_bins(dates)
    out = np.full(len(acc), np.nan)
    for b in range(52):
        idx = np.where((wk == b) & np.isfinite(acc))[0]
        if len(idx) < 10:
            continue
        sample = acc[idx]
        if gamma:
            q = float(np.mean(sample <= 0))
            pos = sample[sample > 0]
            if len(pos) < 8:
                continue
            a, _, scale = stats.gamma.fit(pos, floc=0)
            cdf = q + (1 - q) * np.where(
                sample > 0, stats.gamma.cdf(np.maximum(sample, 1e-9), a, scale=scale), 0.0
            )
        else:
            ranks = stats.rankdata(sample)
            cdf = (ranks - 0.44) / (len(sample) + 0.12)  # Gringorten plotting position
        out[idx] = stats.norm.ppf(np.clip(cdf, 1e-3, 1 - 1e-3))
    return out


def feature_matrix(dates: list[dt.date], rain: np.ndarray, et0: np.ndarray, tmax: np.ndarray) -> np.ndarray:
    """Daily feature matrix (len(dates) × len(FEATURES))."""
    cols = [spi_series(rain, dates, n) for n in WINDOWS]
    cols += [spi_series(rain - et0, dates, n, gamma=False) for n in WINDOWS]
    wk = _week_bins(dates)
    clim = np.array([np.nanmean(tmax[wk == b]) if np.any(wk == b) else np.nan for b in range(52)])
    anom = tmax - clim[wk]
    cols += [_rolling(np.nan_to_num(anom), 30) / 30, _rolling(np.nan_to_num(anom), 90) / 90]
    doy = np.array([d.timetuple().tm_yday for d in dates])
    cols += [np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)]
    aridity = float(np.nansum(rain) / max(1e-6, np.nansum(et0)))
    cols.append(np.full(len(dates), aridity))
    return np.column_stack(cols)


FEATURES_V2 = [
    *(f"spi{n}" for n in WINDOWS),
    *(f"spei{n}" for n in WINDOWS),
    "spei90_lag90",
    "tmax_z30",
    "tmax_z90",
    "phase_sin",
    "phase_cos",
    "wet_season",
    "clim_rain90",
    "aridity",
    "tmax_mean",
    "rain_seasonality",
]


def feature_matrix_v2(
    dates: list[dt.date], rain: np.ndarray, et0: np.ndarray, tmax: np.ndarray
) -> np.ndarray:
    """Location-agnostic daily features (len(dates) x len(FEATURES_V2)).

    Everything is relative to the site's own climate, so the same tree splits mean the same thing in Iowa, Spain,
    Kenya or Queensland:
      * SPI/SPEI at 30-365 days (standardised against the local record) and SPEI-90 three months earlier (drought
        maps have memory);
      * Tmax anomalies as z-scores of the local 30/90-day anomaly distribution (not °C);
      * season phase measured from the locally warmest week, so January means the same in both hemispheres only if
        the climate does;
      * how wet the current 90-day window normally is (share of annual rain, and mm), aridity P/ET0, mean Tmax and
        the Walsh-Lawler rain seasonality index as a climate-class description.
    """
    n_days = len(dates)
    cols = [spi_series(rain, dates, n) for n in WINDOWS]
    cols += [spi_series(rain - et0, dates, n, gamma=False) for n in WINDOWS]
    lag = np.full(n_days, np.nan)
    lag[90:] = cols[5][:-90]
    cols.append(lag)
    wk = _week_bins(dates)
    clim = np.array([np.nanmean(tmax[wk == b]) if np.any(wk == b) else np.nan for b in range(52)])
    anom = np.nan_to_num(tmax - clim[wk])
    for n in (30, 90):
        a = _rolling(anom, n) / n
        sd = float(np.nanstd(a))
        cols.append(a / sd if sd > 0 else a * 0.0)
    sm = np.convolve(np.r_[clim[-2:], clim, clim[:2]], np.ones(5) / 5, mode="valid")
    warm = int(np.nanargmax(sm)) if np.isfinite(sm).any() else 28
    ang = 2 * np.pi * ((wk - warm) % 52) / 52
    cols += [np.sin(ang), np.cos(ang)]
    r = np.where(np.isfinite(rain), rain, 0.0)
    rclim = np.array([np.mean(r[wk == b]) if np.any(wk == b) else 0.0 for b in range(52)])
    daily_clim = rclim[wk]
    clim90 = _rolling(daily_clim, 90)
    mean_daily = float(np.mean(rclim)) or 1e-6
    cols += [clim90 / (90 * mean_daily), clim90]
    cols.append(np.full(n_days, float(np.nansum(rain) / max(1e-6, np.nansum(et0)))))
    cols.append(np.full(n_days, float(np.nanmean(tmax))))
    four_wk = rclim[:52].reshape(13, 4).sum(axis=1)
    tot = float(four_wk.sum())
    si = float(np.sum(np.abs(four_wk - tot / 13)) / tot) if tot > 0 else 0.0
    cols.append(np.full(n_days, si))
    return np.column_stack(cols)


def features_for(meta: dict[str, Any]) -> Any:
    """The feature function a saved model was trained with."""
    return feature_matrix_v2 if meta.get("feature_set") == "v2" else feature_matrix


def usdm_level(row: dict[str, Any]) -> int:
    """Dominant USDM category of a county: highest Dk covering >= 50 % of the area (cumulative percentages)."""
    lvl = 0
    for k, key in enumerate(("d0", "d1", "d2", "d3", "d4"), start=1):
        if float(row[key]) >= 50:
            lvl = k
    return lvl


# Rough boxes of the regions with held-out validation (scripts/train_drought_ml.py). A model is served only in
# the regions its metadata lists under "model_regions" (where it beat the rule-based status on held-out sites).
REGION_BOXES: dict[str, tuple[float, float, float, float]] = {  # lat0, lat1, lon0, lon1
    "US": (24.0, 50.0, -125.0, -66.0),
    "EU": (36.0, 72.0, -25.0, 40.0),
    "AUS": (-39.0, -12.0, 113.0, 154.0),
    "SAM": (-40.0, 5.0, -75.0, -35.0),
    "AFR": (-35.0, 15.0, -18.0, 52.0),
    "SAS": (6.0, 35.0, 66.0, 98.0),
    "EAS": (20.0, 50.0, 100.0, 135.0),
}


def region_of(lat: float, lon: float) -> str | None:
    for r, (la0, la1, lo0, lo1) in REGION_BOXES.items():
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return r
    return None


def in_validated_domain(lat: float, lon: float, meta: dict[str, Any] | None = None) -> bool:
    """True where the saved model was validated on held-out sites and beat the rule-based status there."""
    regions = (meta or {}).get("model_regions", ["US"])
    r = region_of(lat, lon)
    return r is not None and r in regions


@lru_cache
def load() -> tuple[Any, dict[str, Any]] | None:
    p = MODEL_DIR / "drought_hgb.joblib"
    m = MODEL_DIR / "drought_hgb.json"
    if not p.exists() or not m.exists():
        return None
    import joblib

    return joblib.load(p), json.loads(m.read_text())


def predict(features: np.ndarray) -> tuple[int, list[float]] | None:
    loaded = load()
    if loaded is None:
        return None
    model, _meta = loaded
    x = np.asarray(features, float).reshape(1, -1)
    if not np.isfinite(x).all():
        return None
    proba = model.predict_proba(x)[0]
    classes = list(model.classes_)
    full = [float(proba[classes.index(k)]) if k in classes else 0.0 for k in range(6)]
    return int(np.argmax(full)), full
