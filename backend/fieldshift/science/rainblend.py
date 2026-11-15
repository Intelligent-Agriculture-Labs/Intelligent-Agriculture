"""Blending NASA POWER rain (MERRA-2 PRECTOTCORR) with NASA GPM IMERG Final rain.

Why: POWER's rain comes from the MERRA-2 reanalysis (~50 km), which is weakest in the tropics where rain is
convective and gauges are sparse. IMERG merges passive-microwave and IR satellite rain at 0.1° and is calibrated
to GPCC gauges every month. Validation against 18 GHCN-Daily gauges on 6 continents (docs/VALIDATION.md, V13)
decided the policy below; it is the outcome of that test, not a guess:

  * the 50/50 daily mean of POWER and IMERG beat POWER alone at 16 of 18 gauges on daily correlation and on
    monthly Kling–Gupta efficiency, in the tropics (11/12) and outside them (5/6). The weight was fixed at 0.5
    before the test; 0.3 and 0.7 give similar results, so it is not tuned to these gauges;
  * it is adopted only inside the validated latitude band (|lat| ≤ 45°). Poleward of that, IMERG is less
    reliable over snow and frozen ground and we have no gauge evidence, so POWER is served unchanged.

Serving rule (`blend_for_location`):
  * days with IMERG (1998 → ~2 months ago):  0.5 · POWER + 0.5 · IMERG;
  * other days (before 1998, IMERG's ~2-month latency, forecast bridge): POWER × (0.5 + 0.5 · r_m), where r_m is
    the calendar-month climatological IMERG/POWER ratio at the field. This has the same long-run mean as the
    blend, so SPI/SPEI see one consistent climatology instead of a jump at the seam.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

import numpy as np

RATIO_CAP = (0.25, 4.0)
TROPICS_LAT = 23.5
W_IMERG = 0.5
MAX_ABS_LAT = 45.0  # validated band (gauges from 35° S to 42° N)


def zone(lat: float) -> str:
    return "tropics" if abs(lat) <= TROPICS_LAT else "extratropics"


def blend_daily(p: np.ndarray, i: np.ndarray, w_imerg: float) -> np.ndarray:
    """Weighted daily mean; where IMERG is missing, POWER alone."""
    out = (1 - w_imerg) * p + w_imerg * i
    return np.where(np.isfinite(i), out, p)


def _cap(r: float) -> float:
    return float(min(RATIO_CAP[1], max(RATIO_CAP[0], r)))


def climatological_ratio(p: np.ndarray, i: np.ndarray, dates: Sequence[dt.date]) -> np.ndarray:
    """12 calendar-month ratios sum(IMERG)/sum(POWER) over days where both exist (capped; 1.0 if no data)."""
    mon = np.array([d.month - 1 for d in dates])
    ok = np.isfinite(p) & np.isfinite(i)
    out = np.ones(12)
    for m in range(12):
        sel = ok & (mon == m)
        sp, si = float(p[sel].sum()), float(i[sel].sum())
        if sel.sum() >= 60 and sp > 5.0:
            out[m] = _cap(si / sp)
        elif sel.sum() >= 60 and sp <= 5.0 and si <= 5.0:
            out[m] = 1.0  # dry month in both: nothing to correct
    return out


def monthly_rescale(
    p: np.ndarray, i: np.ndarray, dates: Sequence[dt.date], clim: np.ndarray | None = None
) -> np.ndarray:
    """POWER timing with IMERG monthly totals. Months without a complete IMERG month use the climatological ratio."""
    if clim is None:
        clim = climatological_ratio(p, i, dates)
    ym = np.array([d.year * 12 + d.month - 1 for d in dates])
    mon = np.array([d.month - 1 for d in dates])
    out = p * clim[mon]
    for m in np.unique(ym):
        sel = ym == m
        pi, ii = p[sel], i[sel]
        if not np.isfinite(ii).all() or not np.isfinite(pi).all():
            continue
        sp, si = float(pi.sum()), float(ii.sum())
        if sp >= 1.0:
            out[sel] = pi * _cap(si / sp)
        elif si >= 1.0:
            out[sel] = ii  # POWER dry but IMERG saw rain: take IMERG's days
        else:
            out[sel] = pi
    return out


def bridge_factor(clim_ratio: np.ndarray, w_imerg: float = W_IMERG) -> np.ndarray:
    """Multiplier for POWER rain on days without IMERG: same long-run mean as the daily blend."""
    return (1 - w_imerg) + w_imerg * clim_ratio


def adopted(lat: float) -> bool:
    return abs(lat) <= MAX_ABS_LAT


def blend_for_location(
    lat: float, dates: Sequence[dt.date], p: np.ndarray, i: np.ndarray | None
) -> tuple[np.ndarray, dict[str, Any]]:
    """Rain series to serve at `lat` (aligned on `dates`), plus provenance metadata for the Why view.
    `p` may contain non-POWER days at the end (forecast bridge); they get the climatological bridge factor."""
    z = zone(lat)
    if i is None or not np.isfinite(i).any():
        return p, {"method": "power", "zone": z, "imerg_used": False, "reason": "imerg_unavailable"}
    if not adopted(lat):
        return p, {"method": "power", "zone": z, "imerg_used": False, "reason": "outside_validated_band"}
    clim = climatological_ratio(p, i, dates)
    mon = np.array([d.month - 1 for d in dates])
    bridged = p * bridge_factor(clim)[mon]
    out = np.where(np.isfinite(i) & np.isfinite(p), blend_daily(p, i, W_IMERG), bridged)
    fin = np.where(np.isfinite(i) & np.isfinite(p))[0]
    return out, {
        "method": "blend_50_50",
        "zone": z,
        "imerg_used": True,
        "imerg_first": dates[int(fin[0])].isoformat(),
        "imerg_last": dates[int(fin[-1])].isoformat(),
        "monthly_ratio": [round(float(x), 2) for x in clim],
        "annual_power_mm": round(float(np.mean(p[fin])) * 365.25),
        "annual_imerg_mm": round(float(np.mean(i[fin])) * 365.25),
    }


def summarise(rows: list[dict[str, Any]], products: list[str]) -> dict[str, Any]:
    """Per zone: mean metrics per product and how many sites each product beats POWER (P_lst) on."""
    out: dict[str, Any] = {}
    for z in ("tropics", "extratropics", "all"):
        rs = [r for r in rows if z == "all" or r["zone"] == z]
        if not rs:
            continue
        zz: dict[str, Any] = {"n_sites": len(rs), "sites": [r["site"] for r in rs]}
        for k in products:
            ms = [r["metrics"][k] for r in rs]
            base = [r["metrics"]["P_lst"] for r in rs]
            d: dict[str, Any] = {}
            for metric in ("daily_r", "wet_day_csi", "monthly_r", "monthly_kge", "anom3_r"):
                vals = np.array([m[metric] for m in ms], dtype=float)
                d[metric] = round(float(np.nanmean(vals)), 3)
                if k != "P_lst":
                    b = np.array([m[metric] for m in base], dtype=float)
                    ok = np.isfinite(vals) & np.isfinite(b)
                    d[f"{metric}_wins"] = f"{int((vals[ok] > b[ok]).sum())}/{int(ok.sum())}"
            d["abs_bias_pct"] = round(float(np.nanmean([abs(m["monthly_bias_pct"]) for m in ms])), 1)
            zz[k] = d
        out[z] = zz
    return out
