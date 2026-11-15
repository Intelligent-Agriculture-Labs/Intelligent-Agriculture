"""Long-term water-storage trend from GRACE / GRACE-FO (the farmer-facing "groundwater trend").

Model (per location, monthly anomalies y in cm):
    y(t) = a + b·(t − t0) + Σ_{k=1,2} [c_k sin(2πkt) + d_k cos(2πkt)] + e(t)
b is the trend (cm/yr). Monthly residuals are autocorrelated, so the OLS standard error is inflated by
sqrt(n / n_eff) with n_eff = n·(1 − ρ)/(1 + ρ) (ρ = lag-1 residual autocorrelation; Santer et al. 2000), and the
p-value uses a t distribution with n_eff − 6 degrees of freedom. The GRACE → GRACE-FO gap (Jul 2017 – May 2018)
is simply missing months; the harmonic + trend fit needs no gap filling.

Classification (documented in docs/MODELS.md and ADR-025):
    declining          b ≤ −0.3 cm/yr and p < 0.05
    likely_declining   b ≤ −0.3 cm/yr and p < 0.20
    rising / likely_rising   the same with b ≥ +0.3 cm/yr
    stable             otherwise
The "likely" classes exist because multi-year wet and dry spells make monthly residuals strongly autocorrelated
(n_eff is often only 8–15 for 260 months), so a real, well-documented decline such as California's Central
Valley comes out at p ≈ 0.07 over the full record. The card states the p-value either way.
0.3 cm/yr is ~1 cm per 3 years, about the size of trend errors from GRACE leakage and GIA model uncertainty in
mascon solutions, so smaller trends are not called a change even when "significant".
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

MIN_TREND_CM_YR = 0.3
ALPHA = 0.05
ALPHA_LIKELY = 0.20


@dataclass
class StorageTrend:
    slope_cm_yr: float
    slope_se_cm_yr: float
    p_value: float
    change_cm: float  # fitted change from the start of 2003 to the last month
    recent_slope_cm_yr: float | None  # last 5 years (context only)
    anomaly_cm: float  # deseasonalised anomaly, mean of the last 3 months
    percentile: float  # where that anomaly ranks in the record, 0–100
    n_months: int
    n_eff: float
    first: str
    last: str
    status: str  # "declining" | "likely_declining" | "stable" | "likely_rising" | "rising"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def decimal_year(d: dt.date) -> float:
    y0 = dt.date(d.year, 1, 1)
    return d.year + (d - y0).days / ((dt.date(d.year + 1, 1, 1) - y0).days)


def _design(t: np.ndarray, t0: float) -> np.ndarray:
    w = 2 * np.pi * t
    return np.column_stack([np.ones_like(t), t - t0, np.sin(w), np.cos(w), np.sin(2 * w), np.cos(2 * w)])


def _t_sf(t: float, df: float) -> float:
    """Two-sided p-value for a t statistic."""
    from scipy.stats import t as tdist

    return float(2 * tdist.sf(abs(t), df))


def fit(dates: Sequence[dt.date], y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """OLS fit; returns (beta, decimal-year times, residuals, t0)."""
    t = np.array([decimal_year(d) for d in dates])
    ok = np.isfinite(y)
    t, yy = t[ok], np.asarray(y, dtype=float)[ok]
    t0 = float(t.mean())
    X = _design(t, t0)
    beta, *_ = np.linalg.lstsq(X, yy, rcond=None)
    return beta, t, yy - X @ beta, t0


def analyse(dates: Sequence[dt.date], y: np.ndarray, today: dt.date | None = None) -> StorageTrend | None:
    """Trend, significance and current anomaly. Only months up to `today` are used (as-of replays)."""
    yy = np.asarray(y, dtype=float)
    keep = [k for k, d in enumerate(dates) if (today is None or d <= today) and np.isfinite(yy[k])]
    if len(keep) < 36:
        return None
    ds = [dates[k] for k in keep]
    yv = yy[keep]
    beta, t, resid, t0 = fit(ds, yv)
    n = len(yv)
    X = _design(t, t0)
    dof = max(1, n - X.shape[1])
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.inv(X.T @ X)
    rho = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if n > 3 else 0.0
    rho = min(0.95, max(0.0, rho))
    n_eff = max(8.0, n * (1 - rho) / (1 + rho))
    se = math.sqrt(cov[1, 1]) * math.sqrt(n / n_eff)
    slope = float(beta[1])
    p = _t_sf(slope / se, max(2.0, n_eff - X.shape[1])) if se > 0 else 0.0
    seasonal = X[:, 2:] @ beta[2:]
    deseason = yv - seasonal
    anom = float(np.mean(deseason[-3:]))
    pct = float(100.0 * np.mean(deseason <= anom))
    t_start = max(2003.0, float(t[0]))
    change = slope * (float(t[-1]) - t_start)
    recent = None
    rk = t >= t[-1] - 5.0
    if rk.sum() >= 36:
        b_r, *_ = np.linalg.lstsq(_design(t[rk], float(t[rk].mean())), yv[rk], rcond=None)
        recent = round(float(b_r[1]), 2)
    status = classify(slope, p)
    return StorageTrend(
        slope_cm_yr=round(slope, 2),
        slope_se_cm_yr=round(se, 2),
        p_value=round(p, 4),
        change_cm=round(change, 1),
        recent_slope_cm_yr=recent,
        anomaly_cm=round(anom, 1),
        percentile=round(pct, 0),
        n_months=n,
        n_eff=round(n_eff, 1),
        first=ds[0].strftime("%Y-%m"),
        last=ds[-1].strftime("%Y-%m"),
        status=status,
    )


def classify(slope: float, p: float) -> str:
    if abs(slope) < MIN_TREND_CM_YR or p >= ALPHA_LIKELY:
        return "stable"
    word = "declining" if slope < 0 else "rising"
    return word if p < ALPHA else f"likely_{word}"


def trend_line(dates: Sequence[dt.date], y: np.ndarray) -> np.ndarray:
    """Fitted linear trend (intercept + slope, no seasonal terms) at `dates`, for the Why chart."""
    beta, _, _, t0 = fit(dates, np.asarray(y, dtype=float))
    t = np.array([decimal_year(d) for d in dates])
    return beta[0] + beta[1] * (t - t0)
