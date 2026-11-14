"""Long-term agroclimate indicators from the NASA POWER daily record (1984 → last complete year).

Trends: Theil–Sen slope (robust to outliers) with Mann–Kendall significance (Kendall's τ vs. year),
the standard pair for short climate records (Sen 1968; Mann 1945; Kendall 1975).
Seasons are hemisphere-aware: the warm season is Apr–Sep (north) or Oct–Mar (south).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
from scipy import stats

from .cropmodel import gdd


def _season_mask(dates: list[dt.date], year: int, lat: float) -> np.ndarray:
    if lat >= 0:
        return np.array([d.year == year and 4 <= d.month <= 9 for d in dates])
    return np.array(
        [(d.year == year and d.month >= 10) or (d.year == year + 1 and d.month <= 3) for d in dates]
    )


def yearly_metrics(
    dates: list[dt.date], tmax: np.ndarray, tmin: np.ndarray, precip: np.ndarray, et0: np.ndarray, lat: float
) -> dict[str, Any]:
    years = sorted({d.year for d in dates})
    last_full = (
        max(y for y in years if dt.date(y, 12, 31) <= dates[-1])
        if dates[-1].month < 12 or dates[-1].day < 31
        else years[-1]
    )
    if lat < 0:
        last_full -= 1  # southern season spills into the next year
    years = [y for y in years if y <= last_full and dt.date(y, 1, 1) >= dates[0]]
    yidx = np.array([d.year for d in dates])
    doy = np.array([d.timetuple().tm_yday for d in dates])
    m: dict[str, list[float | None]] = {
        k: []
        for k in (
            "tmax_summer",
            "tmin_winter",
            "gdd",
            "frost_free_days",
            "last_spring_frost_doy",
            "first_fall_frost_doy",
            "heat_days",
            "precip_annual",
            "precip_growing",
            "et0_annual",
            "water_deficit",
            "heavy_rain_days",
            "dry_spell_max",
        )
    }
    wet_all = precip[np.isfinite(precip) & (precip >= 1)]
    heavy_thr = float(np.percentile(wet_all, 95)) if len(wet_all) > 50 else 25.0
    for y in years:
        sel = yidx == y
        sm = _season_mask(dates, y, lat)
        if sel.sum() < 360 or not np.isfinite(tmax[sel]).any():
            for k in m:
                m[k].append(None)
            continue
        m["tmax_summer"].append(float(np.nanmean(tmax[sm])))
        wmask = np.array(
            [d.year == y and (d.month in (12, 1, 2) if lat >= 0 else d.month in (6, 7, 8)) for d in dates]
        )
        m["tmin_winter"].append(float(np.nanmean(tmin[wmask])) if wmask.any() else None)
        m["gdd"].append(float(np.nansum(gdd(tmax[sm], tmin[sm], 10.0))))
        # frost dates (Tmin ≤ 0 °C) — northern hemisphere convention; for south use season-relative indices
        ty = tmin[sel]
        dy = doy[sel]
        if lat >= 0:
            spring = np.where((ty <= 0) & (dy < 182))[0]
            fall = np.where((ty <= 0) & (dy >= 182))[0]
            last_spring = int(dy[spring[-1]]) if len(spring) else None
            first_fall = int(dy[fall[0]]) if len(fall) else None
        else:
            spring = np.where((ty <= 0) & (dy >= 182) & (dy < 366))[0]
            fall = np.where((ty <= 0) & (dy < 182))[0]
            last_spring = int(dy[spring[-1]]) - 182 if len(spring) else None
            first_fall = int(dy[fall[0]]) + 183 if len(fall) else None
        m["last_spring_frost_doy"].append(last_spring)
        m["first_fall_frost_doy"].append(first_fall)
        m["frost_free_days"].append(float((first_fall or 366) - (last_spring or 0)))
        m["heat_days"].append(float(np.nansum(tmax[sel] >= 35)))
        m["precip_annual"].append(float(np.nansum(precip[sel])))
        m["precip_growing"].append(float(np.nansum(precip[sm])))
        m["et0_annual"].append(float(np.nansum(et0[sel])))
        m["water_deficit"].append(float(np.nansum(et0[sm]) - np.nansum(precip[sm])))
        m["heavy_rain_days"].append(float(np.nansum(precip[sel] >= heavy_thr)))
        dry = precip[sm] < 1
        run = best = 0
        for v in dry:
            run = run + 1 if v else 0
            best = max(best, run)
        m["dry_spell_max"].append(float(best))
    return {"years": years, "metrics": m, "heavy_thr_mm": round(heavy_thr, 1)}


def trend(years: list[int], values: list[float | None]) -> tuple[float, float]:
    """Theil–Sen slope per decade and Mann–Kendall p-value."""
    x = np.array([y for y, v in zip(years, values, strict=True) if v is not None], float)
    y = np.array([v for v in values if v is not None], float)
    if len(x) < 8:
        return 0.0, 1.0
    slope = stats.theilslopes(y, x)[0]
    tau = stats.kendalltau(x, y)
    return float(slope * 10), float(tau.pvalue)


def monthly_normals(
    dates: list[dt.date],
    tmax: np.ndarray,
    tmin: np.ndarray,
    precip: np.ndarray,
    et0: np.ndarray,
    y0: int,
    y1: int,
) -> list[dict[str, float]]:
    n = len(dates)
    tmax, tmin, precip, et0 = tmax[:n], tmin[:n], precip[:n], et0[:n]
    out = []
    months = np.array([d.month for d in dates])
    ys = np.array([d.year for d in dates])
    nyears = max(1, y1 - y0 + 1)
    for mth in range(1, 13):
        s = (months == mth) & (ys >= y0) & (ys <= y1)
        out.append(
            {
                "month": mth,
                "tmax": round(float(np.nanmean(tmax[s])), 1),
                "tmin": round(float(np.nanmean(tmin[s])), 1),
                "precip": round(float(np.nansum(precip[s]) / nyears), 1),
                "et0": round(float(np.nansum(et0[s]) / nyears), 1),
            }
        )
    return out
