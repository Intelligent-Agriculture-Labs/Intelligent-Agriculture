"""Leaf wetness from hourly weather, shared by the disease models.

Two cited estimators (Sentelhas et al. 2008 compared both against flat-plate sensors at sites in
Brazil, Canada, Italy and the U.S.):

* ``rh90`` — an hour is wet when relative humidity ≥ 90 % (constant RH threshold; Sentelhas et al. 2008,
  Agric. For. Meteorol. 148:392–400, https://doi.org/10.1016/j.agrformet.2007.09.011).
* ``dpd`` — dew-point depression with hysteresis (Gillespie, Srivastava & Pitblado 1993, J. Appl. Meteorol.
  32:567–573): wetness starts when T − Td < 2.0 °C and ends when T − Td > 3.8 °C.

With either method an hour with measurable rain (≥ 0.1 mm) counts as wet, because foliage is wet during rain
whatever the humidity. Hourly rain is present in the forecast feed and absent from NASA POWER hourly
replays (there the estimate is humidity-only, which is drier — see docs/LIMITATIONS.md).

Gridded RH (~10–50 km) is smoother than in-canopy RH; both estimators therefore tend to *under*-estimate
wetness in dense or irrigated canopies and in valley bottoms.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np

RH_WET = 90.0
DPD_ON = 2.0
DPD_OFF = 3.8
RAIN_WET_MM = 0.1


def dew_point(t: np.ndarray, rh: np.ndarray) -> np.ndarray:
    """Magnus formula (Alduchov & Eskridge 1996 coefficients a = 17.625, b = 243.04 °C)."""
    a, b = 17.625, 243.04
    g = np.log(np.clip(rh, 1.0, 100.0) / 100.0) + a * t / (b + t)
    return np.asarray(b * g / (a - g))


def wet_mask(
    t: np.ndarray,
    rh: np.ndarray,
    rain: np.ndarray | None = None,
    dew: np.ndarray | None = None,
    method: str = "rh90",
) -> np.ndarray:
    """Boolean wet/dry per hour."""
    t = np.asarray(t, dtype=float)
    rh = np.asarray(rh, dtype=float)
    if method == "rh90":
        wet = rh >= RH_WET
    elif method == "dpd":
        td = np.asarray(dew, dtype=float) if dew is not None else dew_point(t, rh)
        dpd = t - td
        wet = np.zeros(len(t), dtype=bool)
        state = False
        for i, x in enumerate(dpd):
            if not np.isfinite(x):
                state = False
            elif state:
                state = x <= DPD_OFF
            else:
                state = x < DPD_ON
            wet[i] = state
    else:
        raise ValueError(f"unknown leaf-wetness method {method!r}")
    if rain is not None:
        r = np.asarray(rain, dtype=float)
        wet = wet | (np.isfinite(r) & (r >= RAIN_WET_MM))
    return wet


@dataclass
class Hourly:
    """Hourly series normalised from an Open-Meteo-style dict (also produced for NASA POWER hourly)."""

    time: list[dt.datetime]
    t: np.ndarray
    rh: np.ndarray
    rain: np.ndarray | None
    dew: np.ndarray | None

    @property
    def dates(self) -> list[dt.date]:
        return [x.date() for x in self.time]

    def wet(self, method: str = "rh90") -> np.ndarray:
        return wet_mask(self.t, self.rh, self.rain, self.dew, method)


def from_dict(hourly: dict[str, list[Any]]) -> Hourly:
    """Drops hours without T or RH; keeps rain/dew point when the feed has them."""
    times, ts, rhs, rains, dews = [], [], [], [], []
    rain_in = hourly.get("precipitation")
    dew_in = hourly.get("dew_point_2m")
    for i, (ts_, t, rh) in enumerate(
        zip(
            hourly.get("time", []),
            hourly.get("temperature_2m", []),
            hourly.get("relative_humidity_2m", []),
            strict=False,
        )
    ):
        if t is None or rh is None:
            continue
        times.append(dt.datetime.fromisoformat(ts_[:16]))
        ts.append(float(t))
        rhs.append(float(rh))
        r = rain_in[i] if rain_in is not None and i < len(rain_in) else None
        rains.append(float(r) if r is not None else np.nan)
        d = dew_in[i] if dew_in is not None and i < len(dew_in) else None
        dews.append(float(d) if d is not None else np.nan)
    return Hourly(
        times,
        np.array(ts),
        np.array(rhs),
        np.array(rains) if rain_in is not None else None,
        np.array(dews) if dew_in is not None else None,
    )


@dataclass
class WetPeriod:
    start: dt.datetime
    hours: int  # wet hours in the period (dry gaps excluded)
    t_mean: float  # mean temperature over the wet hours
    i0: int
    i1: int  # inclusive


def wet_periods(h: Hourly, wet: np.ndarray, max_gap_h: int = 0) -> list[WetPeriod]:
    """Contiguous wet periods; dry interruptions of ≤ max_gap_h hours do not end a period
    (Magarey et al. 2005 treat short dry interruptions as non-lethal for many fungi)."""
    out: list[WetPeriod] = []
    cur: list[int] = []
    gap = 0

    def close() -> None:
        out.append(WetPeriod(h.time[cur[0]], len(cur), float(np.mean(h.t[cur])), cur[0], cur[-1]))

    for i, w in enumerate(wet):
        if w:
            cur.append(i)
            gap = 0
        elif cur:
            gap += 1
            if gap > max_gap_h:
                close()
                cur = []
                gap = 0
    if cur:
        close()
    return out


def daily_wet_hours(h: Hourly, wet: np.ndarray) -> dict[dt.date, int]:
    by: dict[dt.date, int] = defaultdict(int)
    for x, w in zip(h.time, wet, strict=True):
        by[x.date()] += int(w)
    return dict(by)
