"""Heat stress for farm workers (outdoor WBGT) and livestock (temperature–humidity indices).

Workers
  * Outdoor Wet-Bulb Globe Temperature  WBGT = 0.7·Tnwb + 0.2·Tg + 0.1·Ta  (ISO 7243:2017).
  * Tnwb (natural wet bulb) and Tg (black globe, 150 mm) are solved from their steady-state energy
    balances after Liljegren, Carhart, Lawday, Tschopp & Sharp (2008), "Modeling the wet bulb globe
    temperature using standard meteorological measurements", J. Occup. Environ. Hyg. 5(10):645–655,
    doi:10.1080/15459620802310770 (the Argonne `wbgt.c` model). Inputs: 2 m air temperature,
    relative humidity, pressure, 2 m wind, global horizontal irradiance, direct-beam fraction and
    the cosine of the solar zenith angle.
  * Limits: NIOSH (2016) Criteria for a Recommended Standard – Occupational Exposure to Heat and Hot
    Environments, DHHS (NIOSH) Pub. 2016-106:
        REL (acclimatized)      = 56.7 − 11.5·log10(M)   [°C-WBGT, M = metabolic rate in W]
        RAL (unacclimatized)    = 59.9 − 14.1·log10(M)
    These equal the ISO 7243:2017 Annex A reference values. Work–rest cycles use the time-weighted
    metabolic rate M = f·M_work + (1 − f)·M_rest (NIOSH 2016 §4; ISO 7243 Annex A). Metabolic
    classes follow ISO 8996:2021 (rest 115 W, moderate 300 W, high 415 W for a 1.8 m² person).

Livestock
  * Cattle and poultry: THI = 0.8·T + RH·(T − 14.4) + 46.4  (RH as a fraction; NRC 1971 index in
    the °C form of Mader, Davis & Brown-Brandl 2006, J. Anim. Sci. 84:712–719). Species thresholds
    from St-Pierre, Cobanov & Schnitkey (2003), J. Dairy Sci. 86(E. Suppl.):E52–E77: dairy cow 70,
    beef cow 75, broiler 78, layer 70. Stress classes relative to the threshold (Hahn et al. 2009,
    ASABE "Livestock energetics and thermal environmental management", ch. 5): alert +1…4,
    danger +5…9, emergency ≥ +10.
  * Sheep and goats: THI = T − (0.31 − 0.31·RH)(T − 14.4)  (Marai et al. 2007, Small Rumin. Res.
    71:1–12): < 22.2 none, 22.2–23.3 moderate, 23.3–25.6 severe, ≥ 25.6 extreme.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

# ------------------------------------------------------------------ Liljegren et al. (2008) constants
SOLAR_CONST = 1367.0  # W/m²
STEFANB = 5.6696e-8
CP = 1003.5  # J/(kg K)
M_AIR = 28.97
M_H2O = 18.015
R_GAS = 8314.34
R_AIR = R_GAS / M_AIR
PR = CP / (CP + 1.25 * R_AIR)  # Prandtl number
RATIO = CP * M_AIR / M_H2O
EMIS_WICK, ALB_WICK, D_WICK, L_WICK = 0.95, 0.4, 0.007, 0.0254
EMIS_GLOBE, ALB_GLOBE, D_GLOBE = 0.95, 0.05, 0.0508
EMIS_SFC, ALB_SFC = 0.999, 0.45
CZA_MIN = 0.00873  # sun at least 0.5° above the horizon for direct beam
NORMSOLAR_MAX = 0.85
MIN_SPEED = 0.13  # m/s, instrument threshold
CONVERGENCE = 0.02
MAX_ITER = 500
WICK_A = 0.56  # Bedingfield & Drew (1950) mass-transfer exponent
# Operational floor for grid-model wind at 2 m: KNMI / ECMWF thermofeel apply 0.62 m/s at 10 m (≈ 0.5 m/s
# at 2 m). ~50 km model winds cannot resolve calm hours and the globe balance is ill-conditioned there.
GRID_WIND_FLOOR_2M = 0.5

# ISO 8996 metabolic rates (W, average person 1.8 m²)
MET_REST = 115.0
MET_MODERATE = 300.0
MET_HIGH = 415.0


def esat_hpa(t_k: float, p_hpa: float = 1013.25) -> float:
    """Saturation vapour pressure over water, Buck (1981) with enhancement factor (hPa)."""
    y = (t_k - 273.15) / (t_k - 32.18)
    return (1.0007 + 3.46e-6 * p_hpa) * 6.1121 * math.exp(17.502 * y)


def dew_point_k(e_hpa: float) -> float:
    z = math.log(e_hpa / (6.1121 * 1.0004))
    return 273.15 + 240.97 * z / (17.502 - z)


def _viscosity(t_k: float) -> float:
    """Dynamic viscosity of air, kg/(m s) (Bird, Stewart & Lightfoot 1960)."""
    sigma, eps_kappa = 3.617, 97.0
    tr = t_k / eps_kappa
    omega = (tr - 2.9) / 0.4 * (-0.034) + 1.048
    return 2.6693e-6 * math.sqrt(M_AIR * t_k) / (sigma * sigma * omega)


def _thermal_cond(t_k: float) -> float:
    return (CP + 1.25 * R_AIR) * _viscosity(t_k)


def _diffusivity(t_k: float, p_hpa: float) -> float:
    """Diffusivity of water vapour in air, m²/s."""
    pcrit13 = (36.4 * 218.0) ** (1.0 / 3.0)
    tcrit512 = (132.0 * 647.3) ** (5.0 / 12.0)
    tcrit12 = math.sqrt(132.0 * 647.3)
    mmix = math.sqrt(1.0 / M_AIR + 1.0 / M_H2O)
    return 3.640e-4 * (t_k / tcrit12) ** 2.334 * pcrit13 * tcrit512 * mmix / (p_hpa / 1013.25) * 1.0e-4


def _evap(t_k: float) -> float:
    """Latent heat of evaporation, J/kg."""
    return (313.15 - t_k) / 30.0 * (-71100.0) + 2.4073e6


def _emis_atm(t_k: float, rh: float, p_hpa: float) -> float:
    """Atmospheric emissivity (Oke 1978)."""
    e = rh * esat_hpa(t_k, p_hpa)
    return 0.575 * e**0.143


def _h_sphere(t_k: float, p_hpa: float, speed: float) -> float:
    density = p_hpa * 100.0 / (R_AIR * t_k)
    re = max(speed, MIN_SPEED) * density * D_GLOBE / _viscosity(t_k)
    nu = 2.0 + 0.6 * math.sqrt(re) * PR**0.3333
    return nu * _thermal_cond(t_k) / D_GLOBE


def _h_cylinder(t_k: float, p_hpa: float, speed: float) -> float:
    density = p_hpa * 100.0 / (R_AIR * t_k)
    re = max(speed, MIN_SPEED) * density * D_WICK / _viscosity(t_k)
    nu = 0.281 * re**0.6 * PR**0.44
    return nu * _thermal_cond(t_k) / D_WICK


def _radiation_terms(solar: float, cza: float, fdir: float | None) -> tuple[float, float, float]:
    """Clip GHI to the top-of-atmosphere value and estimate the direct-beam fraction if not given
    (Liljegren 2008 eq. 13: fdir = exp(3 − 1.34·S* − 1.65/S*), S* = GHI / TOA ≤ 0.85)."""
    if cza <= 0 or solar <= 0:
        return 0.0, 0.0, max(cza, 0.0)
    toa = SOLAR_CONST * cza if cza >= CZA_MIN else 0.0
    if toa <= 0:
        return min(solar, 50.0), 0.0, cza  # twilight: diffuse only
    norm = min(solar / toa, NORMSOLAR_MAX)
    solar = norm * toa
    if fdir is None:
        fdir = math.exp(3.0 - 1.34 * norm - 1.65 / norm) if norm > 0 else 0.0
    return solar, max(0.0, min(fdir, 0.9)), cza


def globe_temperature(
    t_c: float, rh_pct: float, p_hpa: float, speed: float, solar: float, fdir: float, cza: float
) -> float:
    """Black-globe (150 mm) temperature, °C — Liljegren (2008) eq. 7, fixed-point iteration."""
    ta = t_c + 273.15
    rh = rh_pct / 100.0
    tsfc = ta
    emis_air = _emis_atm(ta, rh, p_hpa)
    direct = fdir * (1.0 / (2.0 * cza) - 1.0) if (fdir > 0 and cza > 0) else 0.0
    tg_prev = ta
    for _ in range(MAX_ITER):
        tref = 0.5 * (tg_prev + ta)
        h = _h_sphere(tref, p_hpa, speed)
        tg_new = (
            0.5 * (emis_air * ta**4 + EMIS_SFC * tsfc**4)
            - h / (STEFANB * EMIS_GLOBE) * (tg_prev - ta)
            + solar / (2.0 * STEFANB * EMIS_GLOBE) * (1.0 - ALB_GLOBE) * (direct + 1.0 + ALB_SFC)
        ) ** 0.25
        if abs(tg_new - tg_prev) < CONVERGENCE:
            return tg_new - 273.15
        tg_prev = 0.9 * tg_prev + 0.1 * tg_new
    return float("nan")


def wet_bulb_temperature(
    t_c: float,
    rh_pct: float,
    p_hpa: float,
    speed: float,
    solar: float,
    fdir: float,
    cza: float,
    natural: bool = True,
) -> float:
    """Natural (natural=True, radiatively heated, naturally ventilated wick) or psychrometric wet bulb, °C
    — Liljegren (2008) eq. 9."""
    ta = t_c + 273.15
    rh = rh_pct / 100.0
    tsfc = ta
    sza = math.acos(max(-1.0, min(1.0, cza))) if cza > 0 else math.pi / 2
    eair = rh * esat_hpa(ta, p_hpa)
    emis_air = _emis_atm(ta, rh, p_hpa)
    tw_prev = dew_point_k(max(eair, 1e-3))
    rad = 1.0 if natural else 0.0
    tan_term = (math.tan(sza) / math.pi) if (fdir > 0 and cza > CZA_MIN) else 0.0
    for _ in range(MAX_ITER):
        tref = 0.5 * (tw_prev + ta)
        h = _h_cylinder(tref, p_hpa, speed if natural else max(speed, 4.0))
        fatm = STEFANB * EMIS_WICK * (0.5 * (emis_air * ta**4 + EMIS_SFC * tsfc**4) - tw_prev**4) + (
            1.0 - ALB_WICK
        ) * solar * ((1.0 - fdir) * (1.0 + 0.25 * D_WICK / L_WICK) + fdir * (tan_term + 0.25 * D_WICK / L_WICK) + ALB_SFC)
        ewick = esat_hpa(tw_prev, p_hpa)
        density = p_hpa * 100.0 / (R_AIR * tref)
        sc = _viscosity(tref) / (density * _diffusivity(tref, p_hpa))
        tw_new = (
            ta - _evap(tref) / RATIO * (ewick - eair) / (p_hpa - ewick) * (PR / sc) ** WICK_A + (fatm / h) * rad
        )
        if abs(tw_new - tw_prev) < CONVERGENCE:
            return tw_new - 273.15
        tw_prev = 0.9 * tw_prev + 0.1 * tw_new
    return float("nan")


@dataclass
class WBGT:
    wbgt: float
    tnwb: float
    tg: float
    ta: float


def wbgt_liljegren(
    t_c: float,
    rh_pct: float,
    speed_2m: float,
    solar_wm2: float,
    cza: float,
    p_hpa: float = 1013.25,
    fdir: float | None = None,
) -> WBGT:
    """Outdoor WBGT (°C) from standard weather data (Liljegren et al. 2008)."""
    solar, fd, cza = _radiation_terms(max(solar_wm2, 0.0), cza, fdir)
    speed = max(speed_2m, MIN_SPEED)
    tg = globe_temperature(t_c, rh_pct, p_hpa, speed, solar, fd, cza)
    tw = wet_bulb_temperature(t_c, rh_pct, p_hpa, speed, solar, fd, cza, natural=True)
    return WBGT(0.7 * tw + 0.2 * tg + 0.1 * t_c, tw, tg, t_c)


def wet_bulb_stull(t_c: float, rh_pct: float) -> float:
    """Psychrometric wet bulb, Stull (2011) J. Appl. Meteor. Climatol. 50:2267 — used only as a check."""
    rh = rh_pct
    return (
        t_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t_c + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * rh**1.5 * math.atan(0.023101 * rh)
        - 4.686035
    )


# ------------------------------------------------------------------ solar geometry
def cos_zenith(lat: float, lon: float, day: dt.date, solar_hour: float) -> float:
    """Cosine of the solar zenith angle at local *solar* time `solar_hour` (NOAA / Spencer 1971)."""
    del lon  # solar time already includes the longitude correction
    g = 2.0 * math.pi / 365.0 * (day.timetuple().tm_yday - 1 + (solar_hour - 12.0) / 24.0)
    decl = (
        0.006918
        - 0.399912 * math.cos(g)
        + 0.070257 * math.sin(g)
        - 0.006758 * math.cos(2 * g)
        + 0.000907 * math.sin(2 * g)
        - 0.002697 * math.cos(3 * g)
        + 0.00148 * math.sin(3 * g)
    )
    ha = math.radians(15.0 * (solar_hour - 12.0))
    phi = math.radians(lat)
    return math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(ha)


def equation_of_time_min(day: dt.date) -> float:
    g = 2.0 * math.pi / 365.0 * (day.timetuple().tm_yday - 1)
    return 229.18 * (
        0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g)
    )


def solar_hour(day: dt.date, clock_hour: float, lon: float, utc_offset_h: float) -> float:
    """Local solar time from local clock time."""
    return clock_hour + (4.0 * lon + equation_of_time_min(day)) / 60.0 - utc_offset_h


def pressure_hpa(elevation_m: float | None) -> float:
    """FAO-56 eq. 7."""
    z = elevation_m or 0.0
    return 1013.0 * ((293.0 - 0.0065 * z) / 293.0) ** 5.26


# ------------------------------------------------------------------ worker limits
def rel_wbgt(met_w: float, acclimatized: bool = True) -> float:
    """NIOSH (2016) REL (acclimatized) / RAL (unacclimatized) in °C-WBGT for metabolic rate M (W)."""
    return 56.7 - 11.5 * math.log10(met_w) if acclimatized else 59.9 - 14.1 * math.log10(met_w)


def max_work_fraction(
    wbgt: float, met_work: float = MET_MODERATE, met_rest: float = MET_REST, acclimatized: bool = True
) -> float:
    """Largest fraction of each hour that can be worked so that WBGT ≤ limit(time-weighted M).
    Returns 1.0 (no restriction) … 0.0 (only rest is within the limit)."""
    if wbgt <= rel_wbgt(met_work, acclimatized):
        return 1.0
    if wbgt > rel_wbgt(met_rest, acclimatized):
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        m = mid * met_work + (1 - mid) * met_rest
        if wbgt <= rel_wbgt(m, acclimatized):
            lo = mid
        else:
            hi = mid
    return lo


WORKER_LEVELS = ("low", "moderate", "high", "severe")


def worker_level(wbgt: float) -> str:
    """Risk class for moderate field work (300 W), acclimatized workers.
    low: below REL(300 W) ≈ 28.2 °C → no restriction;  moderate: work ≥ 75 % of the hour;
    high: 25–75 % work;  severe: < 25 % work allowed (≈ above REL at near-rest)."""
    f = max_work_fraction(wbgt)
    if f >= 1.0:
        return "low"
    if f >= 0.75:
        return "moderate"
    if f >= 0.25:
        return "high"
    return "severe"


# ------------------------------------------------------------------ livestock
def thi_nrc(t_c: float, rh_pct: float) -> float:
    """NRC (1971) THI in the °C form (Mader et al. 2006)."""
    return 0.8 * t_c + (rh_pct / 100.0) * (t_c - 14.4) + 46.4


def thi_small_ruminant(t_c: float, rh_pct: float) -> float:
    """Marai et al. (2007) THI for sheep and goats."""
    return t_c - (0.31 - 0.31 * rh_pct / 100.0) * (t_c - 14.4)


LIVESTOCK: dict[str, dict[str, Any]] = {
    # id: (index, threshold or class bounds, reference)
    "dairy_cattle": {"index": "nrc", "threshold": 70.0, "ref": "St-Pierre et al. 2003"},
    "beef_cattle": {"index": "nrc", "threshold": 75.0, "ref": "St-Pierre et al. 2003"},
    "poultry_layers": {"index": "nrc", "threshold": 70.0, "ref": "St-Pierre et al. 2003"},
    "poultry_broilers": {"index": "nrc", "threshold": 78.0, "ref": "St-Pierre et al. 2003"},
    "sheep_goats": {"index": "marai", "bounds": (22.2, 23.3, 25.6), "ref": "Marai et al. 2007"},
}
LIVESTOCK_CLASSES = ("none", "alert", "danger", "emergency")


def livestock_class(animal: str, t_c: float, rh_pct: float) -> tuple[float, str]:
    """(THI, class) with class in none/alert/danger/emergency."""
    spec = LIVESTOCK[animal]
    if spec["index"] == "marai":
        v = thi_small_ruminant(t_c, rh_pct)
        b = spec["bounds"]
        cls = "none" if v < b[0] else "alert" if v < b[1] else "danger" if v < b[2] else "emergency"
        return v, cls
    v = thi_nrc(t_c, rh_pct)
    ex = v - float(spec["threshold"])
    cls = "none" if ex < 1 else "alert" if ex < 5 else "danger" if ex < 10 else "emergency"
    return v, cls


# ------------------------------------------------------------------ hourly assessment
@dataclass
class HourRow:
    time: dt.datetime
    t: float
    rh: float
    wind2: float
    ghi: float
    cza: float
    wbgt: float
    level: str
    work_frac: float


def assess_hours(
    lat: float,
    lon: float,
    times: Sequence[dt.datetime],
    t: Sequence[float],
    rh: Sequence[float],
    wind2: Sequence[float],
    ghi: Sequence[float],
    utc_offset_h: float,
    p_hpa: float,
    direct: Sequence[float] | None = None,
) -> list[HourRow]:
    """Hourly outdoor WBGT and the work–rest level for each hour (missing inputs are skipped).
    Hourly values are hour-ending averages (Open-Meteo, POWER): the sun position is taken at mid-hour."""
    out: list[HourRow] = []
    for k, tm in enumerate(times):
        tk, rk, wk, gk = t[k], rh[k], wind2[k], ghi[k]
        if tk is None or rk is None or not np.isfinite(tk) or not np.isfinite(rk):
            continue
        wk = 1.0 if wk is None or not np.isfinite(wk) else max(float(wk), GRID_WIND_FLOOR_2M)
        gk = 0.0 if gk is None or not np.isfinite(gk) else float(gk)
        sh = solar_hour(tm.date(), tm.hour + tm.minute / 60.0 - 0.5, lon, utc_offset_h)
        cza = cos_zenith(lat, lon, tm.date(), sh)
        fdir = None
        if direct is not None and direct[k] is not None and gk > 1 and np.isfinite(direct[k]):
            fdir = float(direct[k]) / gk
        w = wbgt_liljegren(float(tk), float(min(max(rk, 1.0), 100.0)), wk, gk, cza, p_hpa, fdir)
        if not math.isfinite(w.wbgt):
            continue
        out.append(HourRow(tm, float(tk), float(rk), wk, gk, cza, w.wbgt, worker_level(w.wbgt), max_work_fraction(w.wbgt)))
    return out
