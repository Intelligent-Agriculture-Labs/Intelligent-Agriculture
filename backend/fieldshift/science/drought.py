"""Drought indices.

* SPI (McKee et al. 1993; WMO-No. 1090, 2012): precipitation accumulated over N days, fitted per
  calendar window with a two-parameter gamma distribution (mixed with the probability of zero),
  transformed to a standard normal deviate.
* SPEI-like climatic water balance index (Vicente-Serrano et al. 2010): same procedure on P − ET0,
  using a standardized (z-score via empirical ranks / normal scores) transform, as P − ET0 can be negative.
* Percentile of a current value within its climatology (used for soil moisture, NDVI).
* Combined status mapped to U.S. Drought Monitor-style categories D0–D4 (Svoboda et al. 2002):
  D0 ≤ −0.5, D1 ≤ −0.8, D2 ≤ −1.3, D3 ≤ −1.6, D4 ≤ −2.0 (SPI) / percentiles 30, 20, 10, 5, 2.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
from scipy import stats


def rolling_sum(x: np.ndarray, n: int) -> np.ndarray:
    x = np.where(np.isfinite(x), x, 0.0)
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.full(len(x), np.nan)
    out[n - 1 :] = c[n:] - c[:-n]
    return out


def _same_window(dates: list[dt.date], target: dt.date, half_width: int = 7) -> np.ndarray:
    """Indices of the same calendar day (± half_width days) in every year."""
    doy_t = target.timetuple().tm_yday
    doys = np.array([d.timetuple().tm_yday for d in dates])
    diff = np.abs(doys - doy_t)
    diff = np.minimum(diff, 366 - diff)
    return np.where(diff <= half_width)[0]


def spi_at(precip: np.ndarray, dates: list[dt.date], target: dt.date, n: int) -> float | None:
    acc = rolling_sum(precip, n)
    i = (target - dates[0]).days
    if i < n or i >= len(dates) or not np.isfinite(acc[i]):
        return None
    idx = _same_window(
        dates[: i + 1 - 30] if i > 400 else dates, target
    )  # climatology excludes the most recent month
    sample = acc[idx]
    sample = sample[np.isfinite(sample)]
    if len(sample) < 15:
        return None
    q = float(np.mean(sample == 0))
    pos = sample[sample > 0]
    if len(pos) < 10:
        return None
    a, _loc, scale = stats.gamma.fit(pos, floc=0)
    x = acc[i]
    cdf = q + (1 - q) * (stats.gamma.cdf(x, a, scale=scale) if x > 0 else 0.0)
    cdf = float(np.clip(cdf, 1e-4, 1 - 1e-4))
    return round(float(stats.norm.ppf(cdf)), 2)


def standardized_at(series: np.ndarray, dates: list[dt.date], target: dt.date, n: int) -> float | None:
    """SPEI-like index on an arbitrary accumulated series via empirical normal scores."""
    acc = rolling_sum(series, n)
    i = (target - dates[0]).days
    if i < n or i >= len(dates) or not np.isfinite(acc[i]):
        return None
    idx = _same_window(dates, target)
    sample = acc[idx]
    sample = sample[np.isfinite(sample)]
    if len(sample) < 15:
        return None
    rank = (np.sum(sample < acc[i]) + 0.5 * np.sum(sample == acc[i]) + 0.5) / (
        len(sample) + 1
    )  # Weibull-type plotting position
    return round(float(stats.norm.ppf(np.clip(rank, 1e-3, 1 - 1e-3))), 2)


def percentile_of(value: float, climatology: np.ndarray) -> float | None:
    c = climatology[np.isfinite(climatology)]
    if len(c) < 5 or not np.isfinite(value):
        return None
    return round(float(100 * (np.sum(c < value) + 0.5 * np.sum(c == value)) / len(c)), 1)


SPI_BREAKS = [(-2.0, 5), (-1.6, 4), (-1.3, 3), (-0.8, 2), (-0.5, 1)]
PCT_BREAKS = [(2, 5), (5, 4), (10, 3), (20, 2), (30, 1)]
LABELS = {
    0: "No drought",
    1: "Abnormally dry (D0)",
    2: "Moderate drought (D1)",
    3: "Severe drought (D2)",
    4: "Extreme drought (D3)",
    5: "Exceptional drought (D4)",
}


def level_from_spi(spi: float | None) -> int:
    if spi is None:
        return 0
    for thr, lvl in SPI_BREAKS:
        if spi <= thr:
            return lvl
    return 0


def level_from_pct(p: float | None) -> int:
    if p is None:
        return 0
    for thr, lvl in PCT_BREAKS:
        if p <= thr:
            return lvl
    return 0


def combined_level(
    spi30: float | None, spi90: float | None, spei90: float | None, sm_pct: float | None, vhi: float | None
) -> tuple[int, list[str]]:
    """Convergence-of-evidence blend (like the USDM): weighted mean of indicator levels, rounded.
    Long-term water balance (SPI/SPEI-90) weighs most; short-term SPI-30 and satellite indicators refine it."""
    parts: list[tuple[float, float, str]] = []
    if spi90 is not None:
        parts.append((level_from_spi(spi90), 0.3, f"SPI-90 = {spi90:+.2f}"))
    if spei90 is not None:
        parts.append((level_from_spi(spei90), 0.25, f"SPEI-90 = {spei90:+.2f}"))
    if spi30 is not None:
        parts.append((level_from_spi(spi30), 0.15, f"SPI-30 = {spi30:+.2f}"))
    if spei365 is not None:
        parts.append((level_from_spi(spei365), 0.3, f"SPEI-12 months = {spei365:+.2f}"))
    if sm_pct is not None:
        parts.append((level_from_pct(sm_pct), 0.2, f"soil-moisture percentile = {sm_pct:.0f}"))
    if vhi is not None:
        vlev = 0 if vhi >= 40 else (2 if vhi >= 30 else (3 if vhi >= 20 else 4))
        parts.append((vlev, 0.1, f"vegetation health index = {vhi:.0f}"))
    if not parts:
        return 0, []
    wsum = sum(w for _, w, _ in parts)
    lvl = sum(lv * w for lv, w, _ in parts) / wsum
    return int(round(lvl)), [p[2] for p in parts]
