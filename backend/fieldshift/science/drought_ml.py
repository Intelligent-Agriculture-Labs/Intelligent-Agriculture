"""ML drought classifier: gradient-boosted trees trained on 20 years of U.S. Drought Monitor county maps with
features computed from NASA POWER (multi-scale SPI/SPEI, temperature anomalies, seasonality, aridity).

The SAME feature code is used for training (scripts/train_drought_ml.py) and serving (advice), so there is no
train/serve skew. The model is only used where it was validated (contiguous U.S.); elsewhere the transparent
rule-based status (drought.combined_level) is used.
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


def usdm_level(row: dict[str, Any]) -> int:
    """Dominant USDM category of a county: highest Dk covering >= 50 % of the area (cumulative percentages)."""
    lvl = 0
    for k, key in enumerate(("d0", "d1", "d2", "d3", "d4"), start=1):
        if float(row[key]) >= 50:
            lvl = k
    return lvl


def in_validated_domain(lat: float, lon: float) -> bool:
    return 24.0 <= lat <= 50.0 and -125.0 <= lon <= -66.0


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
