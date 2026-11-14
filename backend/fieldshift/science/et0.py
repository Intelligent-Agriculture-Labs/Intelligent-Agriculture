"""FAO-56 Penman–Monteith reference evapotranspiration (Allen et al., 1998, FAO Irrigation & Drainage Paper 56).

All equation numbers refer to FAO-56. Vectorised over numpy arrays.
"""

from __future__ import annotations

import numpy as np

GSC = 0.0820  # solar constant MJ m-2 min-1
SIGMA = 4.903e-9  # Stefan-Boltzmann MJ K-4 m-2 day-1


def sat_vp(t: np.ndarray | float) -> np.ndarray:
    """Saturation vapour pressure e°(T) [kPa], eq. 11."""
    return 0.6108 * np.exp(17.27 * np.asarray(t, float) / (np.asarray(t, float) + 237.3))


def slope_vp(t: np.ndarray | float) -> np.ndarray:
    """Slope of saturation vapour pressure curve Δ [kPa °C-1], eq. 13."""
    t = np.asarray(t, float)
    return 4098 * sat_vp(t) / (t + 237.3) ** 2


def psy_const(elev_m: float) -> float:
    """Psychrometric constant γ [kPa °C-1], eqs. 7–8."""
    p = 101.3 * ((293 - 0.0065 * elev_m) / 293) ** 5.26
    return 0.665e-3 * p


def ra(lat_deg: float, doy: np.ndarray | int) -> np.ndarray:
    """Extraterrestrial radiation Ra [MJ m-2 day-1], eqs. 21–25."""
    phi = np.radians(lat_deg)
    j = np.asarray(doy, float)
    dr = 1 + 0.033 * np.cos(2 * np.pi * j / 365)
    delta = 0.409 * np.sin(2 * np.pi * j / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1.0, 1.0))
    return (24 * 60 / np.pi) * GSC * dr * (ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws))


def wind_2m(u_z: np.ndarray | float, z: float) -> np.ndarray:
    """Convert wind speed at height z to 2 m, eq. 47."""
    return np.asarray(u_z, float) * 4.87 / np.log(67.8 * z - 5.42)


def et0_pm(
    tmax: np.ndarray,
    tmin: np.ndarray,
    rs: np.ndarray,
    u2: np.ndarray,
    lat_deg: float,
    elev_m: float,
    doy: np.ndarray,
    *,
    rh_mean: np.ndarray | None = None,
    tdew: np.ndarray | None = None,
    albedo: float = 0.23,
) -> np.ndarray:
    """Daily FAO-56 PM ET0 [mm day-1], eq. 6.

    Actual vapour pressure from dew point (eq. 14) if given, else from RHmean (eq. 19).
    Rs is incoming shortwave [MJ m-2 day-1]. Missing inputs propagate as NaN.
    """
    tmax = np.asarray(tmax, float)
    tmin = np.asarray(tmin, float)
    tmean = (tmax + tmin) / 2
    es = (sat_vp(tmax) + sat_vp(tmin)) / 2  # eq. 12
    if tdew is not None:
        ea = sat_vp(np.asarray(tdew, float))
    elif rh_mean is not None:
        ea = np.asarray(rh_mean, float) / 100 * es
    else:  # FAO-56 recommendation when humidity is missing: Tdew ≈ Tmin
        ea = sat_vp(tmin)
    ea = np.minimum(ea, es)
    delta = slope_vp(tmean)
    gamma = psy_const(elev_m)
    rs = np.asarray(rs, float)
    ra_ = ra(lat_deg, doy)
    rso = (0.75 + 2e-5 * elev_m) * ra_  # eq. 37
    rns = (1 - albedo) * rs  # eq. 38
    ratio = np.clip(np.where(rso > 0, rs / rso, 0.5), 0.25, 1.0)
    rnl = SIGMA * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2) * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0))) * (1.35 * ratio - 0.35)  # eq. 39
    rn = rns - rnl
    g = 0.0  # daily soil heat flux ≈ 0, eq. 42
    u2 = np.asarray(u2, float)
    num = 0.408 * delta * (rn - g) + gamma * (900 / (tmean + 273)) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)
    return np.maximum(num / den, 0.0)


def et0_hargreaves(tmax: np.ndarray, tmin: np.ndarray, lat_deg: float, doy: np.ndarray) -> np.ndarray:
    """Hargreaves–Samani ET0 [mm day-1], eq. 52 — fallback when radiation/wind are missing."""
    tmax = np.asarray(tmax, float)
    tmin = np.asarray(tmin, float)
    ra_mm = ra(lat_deg, doy) * 0.408
    return np.maximum(0.0023 * ((tmax + tmin) / 2 + 17.8) * np.sqrt(np.maximum(tmax - tmin, 0)) * ra_mm, 0.0)
