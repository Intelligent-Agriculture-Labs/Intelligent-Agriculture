"""Weather-driven risk models for high-impact pests and diseases of the world's major crops.

Every model returns a daily score 0..1 meaning "how fully the weather met the published infection or
development criteria on that day", plus the evidence used, so the advice card can show its reasoning.
A score is *favourable weather*, never a detection: cards always ask the farmer to scout first.

Equations, parameters and citations are listed per model below and in docs/MODELS.md §Global pest and
disease risk; validations are in docs/VALIDATION.md (V9). Leaf wetness comes from `leafwet.py`.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import leafwet as lw
from .pests import region_of

TROPIC = 23.44


# --------------------------------------------------------------------------- inputs / outputs
@dataclass
class RiskInput:
    lat: float
    lon: float
    today: dt.date
    dates: list[dt.date]  # daily series (NASA POWER + forecast), aligned with tmax/tmin/rain
    tmax: np.ndarray
    tmin: np.ndarray
    rain: np.ndarray
    hourly: lw.Hourly | None = None
    elevation_m: float | None = None
    planting: dt.date | None = None
    rh: np.ndarray | None = None  # daily mean RH (%), aligned with dates

    def di(self, d: dt.date) -> int:
        return (d - self.dates[0]).days


@dataclass
class RiskResult:
    scores: dict[dt.date, float] = field(default_factory=dict)
    evidence: dict[dt.date, list[str]] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- generic infection model
def magarey_f(t: float, tmin: float, topt: float, tmax: float) -> float:
    """Temperature response of Magarey, Sutton & Thayer (2005, Phytopathology 95:92–100, eq. 1):
    f(T) = ((Tmax − T)/(Tmax − Topt)) · ((T − Tmin)/(Topt − Tmin))^((Topt − Tmin)/(Tmax − Topt)),
    0 outside (Tmin, Tmax); 1 at Topt."""
    if not (tmin < t < tmax):
        return 0.0
    return float(
        ((tmax - t) / (tmax - topt)) * ((t - tmin) / (topt - tmin)) ** ((topt - tmin) / (tmax - topt))
    )


def magarey_w(t: float, p: dict[str, float]) -> float:
    """Wetness hours needed for infection at mean temperature T: W(T) = Wmin / f(T), capped at Wmax
    (Magarey et al. 2005, eq. 2). Returns inf when infection is impossible at T."""
    f = magarey_f(t, p["tmin"], p["topt"], p["tmax"])
    if f <= 0:
        return math.inf
    w = p["wmin"] / f
    return w if w <= p["wmax"] else math.inf


def _wet_period_scores(
    h: lw.Hourly,
    p: dict[str, float],
    method: str = "rh90",
    gap: int = 0,
    t_lo: float | None = None,
    t_hi: float | None = None,
) -> tuple[dict[dt.date, float], dict[dt.date, lw.WetPeriod]]:
    """Fraction of the wetness requirement W(T) met by the longest-qualifying wet period starting each day."""
    wet = h.wet(method)
    best: dict[dt.date, float] = {d: 0.0 for d in sorted(set(h.dates))}
    per: dict[dt.date, lw.WetPeriod] = {}
    for wp in lw.wet_periods(h, wet, gap):
        if t_lo is not None and wp.t_mean < t_lo:
            continue
        if t_hi is not None and wp.t_mean > t_hi:
            continue
        need = magarey_w(wp.t_mean, p)
        s = 0.0 if not math.isfinite(need) else min(1.0, wp.hours / need)
        for d in _days_covered(h, wp):
            if s > best.get(d, 0.0):
                best[d] = s
                per[d] = wp
    return best, per


def _days_covered(h: lw.Hourly, wp: lw.WetPeriod) -> list[dt.date]:
    """Every calendar day a wet period touches: a multi-day wet spell counts on each of its days, not only the
    day it started (found during validation V9 — continuous rainy-season wetness was otherwise under-counted)."""
    d0, d1 = h.time[wp.i0].date(), h.time[wp.i1].date()
    return [d0 + dt.timedelta(days=k) for k in range((d1 - d0).days + 1)]


def _complete_days(h: lw.Hourly, min_hours: int = 18) -> set[dt.date]:
    cnt: dict[dt.date, int] = {}
    for d in h.dates:
        cnt[d] = cnt.get(d, 0) + 1
    return {d for d, n in cnt.items() if n >= min_hours}


def _fmt_wp(wp: lw.WetPeriod, need: float) -> str:
    need_s = f"{need:.0f} h" if math.isfinite(need) else "not reachable at this temperature"
    return (
        f"Wet period from {wp.start:%d %b %H:00}: {wp.hours} h leaf wetness at a mean {wp.t_mean:.1f} °C "
        f"(needed at that temperature: {need_s})."
    )


def _infection_model(
    params: dict[str, float],
    method: str = "rh90",
    gap: int = 0,
    t_lo: float | None = None,
    t_hi: float | None = None,
) -> Callable[[RiskInput], RiskResult]:
    def run(x: RiskInput) -> RiskResult:
        r = RiskResult()
        if x.hourly is None or not len(x.hourly.t):
            return r
        ok = _complete_days(x.hourly)
        best, per = _wet_period_scores(x.hourly, params, method, gap, t_lo, t_hi)
        for d, s in best.items():
            if d not in ok:
                continue
            r.scores[d] = round(s, 3)
            if d in per:
                r.evidence[d] = [_fmt_wp(per[d], magarey_w(per[d].t_mean, params))]
        return r

    return run


# --------------------------------------------------------------------------- pathogen parameters
# Magarey et al. (2005) form: tmin/topt/tmax (°C) of infection, wmin = wetness hours at Topt, wmax = upper cap.
# Wheat leaf rust: Magarey et al. 2005, Table 2 row "Puccinia recondita" (2.6 / 25 / 30 °C, 5 / 16 h); dry-interruption
#   class "sensitive" (D50 1–2 h) -> gap 1 h.
P_LEAF_RUST = {"tmin": 2.6, "topt": 25.0, "tmax": 30.0, "wmin": 5.0, "wmax": 16.0}
# Wheat stem rust (not in Magarey Table 2): Roelfs, Singh & Saari 1992 — germination 2 / 15–24 / 30 °C (Table 2),
#   6–8 h dew needed, maximum infection with 8–12 h dew at 18 °C (text) -> Topt 18, Wmin 6; Wmax from Magarey's
#   regression Wmax ≈ 3.8 + 3.0·Wmin = 21.8 h.
P_STEM_RUST = {"tmin": 2.0, "topt": 18.0, "tmax": 30.0, "wmin": 6.0, "wmax": 21.8}
# Coffee leaf rust: cardinal temperatures of the Kushalappa & Eskes (1989) infection curve (12.5 / 32.5 °C), optimum
#   at the centre of the 21–25 °C germination optimum (Avelino et al. 2015, citing Waller 1982); infection needs free
#   water and ≈ 6 h wetness (zero point of Kushalappa & Eskes' wetness curve); Wmax by Magarey's regression.
P_COFFEE_RUST = {"tmin": 12.5, "topt": 23.0, "tmax": 32.5, "wmin": 6.0, "wmax": 21.8}
# Black Sigatoka: germination 20–35 °C, optimum 26.5 °C (Jacome & Schuh 1991); conidia infect with 0–18 h wetness,
#   symptom development fastest after 18 h (Jacome & Schuh 1992). Wmin 12 h is OUR choice inside that range (not a
#   published constant) — documented in docs/MODELS.md as an assumption.
P_SIGATOKA = {"tmin": 20.0, "topt": 26.5, "tmax": 35.0, "wmin": 12.0, "wmax": 48.0}

# BLASTAM (Japanese prefectural plant-protection offices; wetness table after Yokouchi, Higuchi & Munakata):
# wet hours required at the mean temperature of the wet period (°C, rounded).
BLASTAM_HOURS = {15: 17, 16: 15, 17: 14, 18: 13, 19: 12, 20: 11, 21: 11, 22: 10, 23: 10, 24: 10, 25: 10}


def blastam_required(t: float) -> float:
    k = int(round(t))
    return float(BLASTAM_HOURS[k]) if k in BLASTAM_HOURS else math.inf


def rice_blast(x: RiskInput) -> RiskResult:
    """Rice blast (Magnaporthe oryzae), BLASTAM criteria. A day is *favourable* (score 1) when a wet period starting
    that day has a mean temperature of 15–25 °C, lasts at least the BLASTAM hours for that temperature (17 h at
    15 °C … 10 h at 22–25 °C), and the mean daily temperature of the 5 days up to that day is 20–25 °C.
    *Quasi-favourable* (score 0.5): ≥ 10 wet hours but one temperature condition missed (BLASTAM patterns 1–3), or
    the temperatures fit but wetness is short (pattern 4, scaled by hours/required). Symptoms follow 7–10 days later.
    Wetness: RH ≥ 90 % or rain (BLASTAM itself estimates wetness from AMeDAS rain, wind and sunshine)."""
    r = RiskResult()
    h = x.hourly
    if h is None or not len(h.t):
        return r
    ok = _complete_days(h)
    tmean = (np.asarray(x.tmax) + np.asarray(x.tmin)) / 2
    best: dict[dt.date, tuple[float, str]] = {}
    for wp in lw.wet_periods(h, h.wet("rh90"), 0):
        d = wp.start.date()
        i = x.di(d)
        m5 = float(np.nanmean(tmean[max(0, i - 4) : i + 1])) if 0 <= i < len(tmean) else float("nan")
        need = blastam_required(wp.t_mean)
        t_ok = 15.0 <= wp.t_mean <= 25.0
        m_ok = np.isfinite(m5) and 20.0 <= m5 <= 25.0
        if t_ok and m_ok and wp.hours >= need:
            s, why = 1.0, "favourable"
        elif wp.hours >= 10 and (t_ok or m_ok) and not (t_ok and m_ok and wp.hours >= need):
            s, why = 0.5, "quasi-favourable (one temperature condition missed)"
        elif t_ok and m_ok:
            s, why = 0.5 * wp.hours / need, "wet period too short"
        else:
            s, why = 0.0, "unfavourable"
        need_s = f"{need:.0f} h" if math.isfinite(need) else "outside 15–25 °C"
        for dd in _days_covered(h, wp):
            if s <= best.get(dd, (-1.0, ""))[0]:
                continue
            best[dd] = (
                s,
                f"Wet period from {wp.start:%d %b %H:00}: {wp.hours} h at a mean {wp.t_mean:.1f} °C (BLASTAM needs "
                f"{need_s}); 5-day mean temperature {m5:.1f} °C (needs 20–25 °C) → {why}.",
            )
    for d in sorted(ok):
        s, why = best.get(d, (0.0, ""))
        r.scores[d] = round(s, 3)
        if why:
            r.evidence[d] = [why]
    return r


def tropical_late_blight(x: RiskInput) -> RiskResult:
    """Late blight in the tropics: Wallin (1962) severity values as used by BLITECAST (Krause et al. 1975).
    In the Toluca highlands (Grünwald, Rubio-Covarrubias & Fry 2000) BLITECAST's cumulative-SV spray trigger came
    too late; FieldShift therefore alerts on each day's SV, not on the cumulative trigger.
    Per day: the longest RH ≥ 90 % period and its mean temperature give a severity value 0–4:
      7.2–11.6 °C: 16–18 h → 1, 19–21 → 2, 22–24 → 3, ≥ 25 → 4
      11.7–15.0 °C: 13–15 h → 1, 16–18 → 2, 19–21 → 3, ≥ 22 → 4
      15.1–26.6 °C: 10–12 h → 1, 13–15 → 2, 16–18 → 3, ≥ 19 → 4
    Score = SV/4. Unlike Hutton (Tmin ≥ 10 °C), cool highland nights still count; hot lowland periods (> 26.6 °C)
    do not."""
    r = RiskResult()
    h = x.hourly
    if h is None or not len(h.t):
        return r
    ok = _complete_days(h)
    wet = h.wet("rh90")
    best: dict[dt.date, tuple[int, lw.WetPeriod]] = {}
    for wp in lw.wet_periods(h, wet, 0):
        sv = wallin_sv(wp.hours, wp.t_mean)
        for d in _days_covered(h, wp):
            if d not in best or sv > best[d][0] or (sv == best[d][0] and wp.hours > best[d][1].hours):
                best[d] = (sv, wp)
    for d in sorted(ok):
        sv, wp = best.get(d, (0, None))  # type: ignore[assignment]
        r.scores[d] = sv / 4
        if wp is not None:
            r.evidence[d] = [
                f"Longest humid period from {wp.start:%d %b %H:00}: {wp.hours} h at RH ≥ 90 %, mean {wp.t_mean:.1f} °C "
                f"→ Wallin severity value {sv} of 4."
            ]
    ds = sorted(r.scores)
    r.extra["sv7"] = {d: int(sum(4 * r.scores[e] for e in ds if 0 <= (d - e).days < 7)) for d in ds}
    return r


def wallin_sv(hours: int, t: float) -> int:
    if 7.2 <= t <= 11.6:
        cuts = (16, 19, 22, 25)
    elif 11.6 < t <= 15.0:
        cuts = (13, 16, 19, 22)
    elif 15.0 < t <= 26.6:
        cuts = (10, 13, 16, 19)
    else:
        return 0
    return sum(hours >= c for c in cuts)


def gray_leaf_spot(x: RiskInput) -> RiskResult:
    """Maize gray leaf spot (Cercospora zeae-maydis) after Paul & Munkvold (2005, Phytopathology 95:388–396): the
    best weather predictors of severity (V4–V12, Iowa 1998–2002) were the hours at 22–30 °C (observed 85.5–230.5 h)
    and the night hours with RH ≥ 90 % (122–330 h). Here both are accumulated over the trailing 14 days and expressed
    as a fraction of the upper end of the observed range, pro-rated to the window length (V4–V12 ≈ 30 days):
    score = ½ (warm_h / (230.5·14/30) + wet_night_h / (330·14/30)), capped at 1. A risk *index*, not the authors'
    fitted regression (whose coefficients need field inoculum data)."""
    r = RiskResult()
    h = x.hourly
    if h is None or not len(h.t):
        return r
    ok = sorted(_complete_days(h))
    warm = (h.t >= 22) & (h.t <= 30)
    night = np.array([t.hour >= 20 or t.hour < 8 for t in h.time])
    wetn = (h.rh >= 90) & night
    days = np.array(h.dates)
    win = 14
    ref_w, ref_n = 230.5 * win / 30, 330.0 * win / 30
    for d in ok:
        m = (days > d - dt.timedelta(days=win)) & (days <= d)
        n_days = len({e for e in days[m]})
        if n_days < 10:
            continue
        a, b = float(warm[m].sum()) * win / n_days, float(wetn[m].sum()) * win / n_days
        r.scores[d] = round(min(1.0, 0.5 * (min(1.0, a / ref_w) + min(1.0, b / ref_n))), 3)
        r.evidence[d] = [
            f"Last {win} days: {a:.0f} h at 22–30 °C (epidemic-level ≈ {ref_w:.0f} h) and {b:.0f} humid night hours "
            f"at RH ≥ 90 % (≈ {ref_n:.0f} h), from Paul & Munkvold 2005."
        ]
    return r


def wheat_leaf_rust(x: RiskInput) -> RiskResult:
    """Wheat leaf rust (Puccinia triticina): Magarey et al. 2005 Table 2 (P. recondita: 2.6 / 25 / 30 °C, Wmin 5 h,
    Wmax 16 h; dry interruptions of > 1 h end a wet period). Roelfs et al. 1992: ≤ 3 h dew at ~20 °C, 12 h at 10 °C."""
    return _infection_model(P_LEAF_RUST, gap=1)(x)


def wheat_stem_rust(x: RiskInput) -> RiskResult:
    """Wheat stem rust (Puccinia graminis f. sp. tritici): Roelfs, Singh & Saari 1992 — 6–8 h dew, maximum infection
    with 8–12 h dew at 18 °C (followed by light, not modelled). Parameters: see P_STEM_RUST."""
    return _infection_model(P_STEM_RUST, gap=1)(x)


def coffee_leaf_rust(x: RiskInput) -> RiskResult:
    """Coffee leaf rust (Hemileia vastatrix). Infection: a wet period meeting W(T) with P_COFFEE_RUST (free water;
    Kushalappa & Eskes 1989). Development: Avelino et al. (2015) link the 2008–2013 epidemics to a narrower daily
    temperature range — more days with Tmax 22–28 °C (optimal latent period); on days outside that band the score is
    halved."""
    r = _infection_model(P_COFFEE_RUST, gap=2)(x)
    for d in list(r.scores):
        i = x.di(d)
        if not (0 <= i < len(x.tmax)):
            continue
        tx = float(x.tmax[i])
        if not (22.0 <= tx <= 28.0):
            r.scores[d] = round(r.scores[d] * 0.5, 3)
        if r.scores[d] > 0:
            r.evidence.setdefault(d, []).append(
                f"Daily maximum {tx:.1f} °C ({'inside' if 22 <= tx <= 28 else 'outside'} the 22–28 °C band that "
                "shortens the latent period; Avelino et al. 2015)."
            )
    return r


def black_sigatoka(x: RiskInput) -> RiskResult:
    """Banana black Sigatoka (Pseudocercospora fijiensis): germination 20–35 °C, optimum 26.5 °C (Jacome & Schuh
    1991); infection with long wet periods (0–18 h, fastest symptoms after 18 h; Jacome & Schuh 1992)."""
    return _infection_model(P_SIGATOKA, gap=2)(x)


# --------------------------------------------------------------------------- insect / locust (daily data)
def _band(v: float, lo: float, hi: float, taper: float) -> float:
    """1 inside [lo, hi], falling linearly to 0 at `taper` outside."""
    if lo <= v <= hi:
        return 1.0
    dist = lo - v if v < lo else v - hi
    return max(0.0, 1.0 - dist / taper)


def cassava_whitefly(x: RiskInput) -> RiskResult:
    """Bemisia tabaci on cassava (vector of cassava mosaic disease). Katono et al. (2021, Insects 12:604; Uganda
    2016–17): counts were highest at 28–30 °C, 30–150 mm rain per month and RH 55–70 %; rain and heat above that
    reduced them. Score = product of the three band memberships over the trailing 30 days (linear taper: 4 °C,
    100 mm, 15 % RH). RH is skipped when not available."""
    r = RiskResult()
    tmean = (np.asarray(x.tmax) + np.asarray(x.tmin)) / 2
    for k, d in enumerate(x.dates):
        if k < 30:
            continue
        tm = float(np.nanmean(tmean[k - 30 : k]))
        rn = float(np.nansum(x.rain[k - 30 : k]))
        if not np.isfinite(tm):
            continue
        s = _band(tm, 28.0, 30.0, 4.0) * _band(rn, 30.0, 150.0, 100.0)
        txt = f"Last 30 days: mean temperature {tm:.1f} °C (best 28–30), rain {rn:.0f} mm (best 30–150)"
        if x.rh is not None:
            rh = float(np.nanmean(x.rh[k - 30 : k]))
            if np.isfinite(rh):
                s *= _band(rh, 55.0, 70.0, 15.0)
                txt += f", RH {rh:.0f} % (best 55–70)"
        r.scores[d] = round(s, 3)
        r.evidence[d] = [txt + " — Katono et al. 2021."]
    return r


def desert_locust(x: RiskInput) -> RiskResult:
    """Desert locust breeding conditions in recession areas (FAO: breeding usually needs at least 25–50 mm of rain,
    which moistens sandy soil to 5–10 cm for egg-laying and greens annual vegetation; Symmons & Cressman 2001, FAO
    Desert Locust Guidelines). Eggs and hoppers develop only when warm; we require a 30-day mean ≥ 20 °C (full) with
    a linear taper from 15 °C (our assumption). Score: 30-day rain / 25 mm (capped 1) × warm factor; < 10 mm → 0."""
    r = RiskResult()
    tmean = (np.asarray(x.tmax) + np.asarray(x.tmin)) / 2
    for k, d in enumerate(x.dates):
        if k < 30:
            continue
        rn = float(np.nansum(x.rain[k - 30 : k + 1]))
        tm = float(np.nanmean(tmean[k - 30 : k + 1]))
        warm = 1.0 if tm >= 20 else max(0.0, (tm - 15) / 5)
        s = min(1.0, rn / 25.0) * warm
        r.scores[d] = round(s if rn >= 10 else 0.0, 3)
        r.evidence[d] = [
            f"Rain in the last 30 days: {rn:.0f} mm (FAO: breeding usually needs ≥ 25 mm); mean temperature {tm:.1f} °C."
        ]
    return r


# --------------------------------------------------------------------------- geography
# Recession areas get < 200 mm/yr (FAO); summer breeding extends into the drier Sahel. Fields wetter than this
# (10-year mean annual rain) are treated as outside the breeding habitat.
LOCUST_MAX_ANNUAL_RAIN_MM = 400.0

# Desert locust recession area (FAO): Sahara–Sahel, Arabian Peninsula, Iran–Pakistan–NW India.
LOCUST_BOXES = [
    (12.0, 35.0, -18.0, 35.0),  # Sahara and Sahel, Mauritania → Sudan
    (8.0, 22.0, 35.0, 52.0),  # Horn of Africa, Red Sea coasts
    (12.0, 32.0, 34.0, 60.0),  # Arabian Peninsula
    (22.0, 32.0, 56.0, 75.5),  # SE Iran, Pakistan, Rajasthan
]


def in_locust_area(lat: float, lon: float) -> bool:
    return any(a <= lat <= b and c <= lon <= e for a, b, c, e in LOCUST_BOXES)


@dataclass
class Model:
    id: str
    kind: str  # disease | pest
    crops: list[str]
    fn: Callable[[RiskInput], RiskResult]
    ref: str
    hourly: bool = True
    regions: list[str] | None = None  # continent list (pests.region_of); None = everywhere the host grows
    tropics_only: bool = False
    in_range_fn: Callable[[float, float, float | None], bool] | None = None
    season: tuple[int, int] | None = None  # days after planting when the crop is at risk (annual crops)
    window_back: int = 0  # look back N days too (slow-building conditions, e.g. rain-triggered breeding)
    min_score: float = 0.25

    def in_range(self, lat: float, lon: float, elev: float | None = None) -> bool:
        if self.tropics_only and abs(lat) > TROPIC:
            return False
        if self.regions is not None and region_of(lat, lon) not in self.regions:
            return False
        return not (self.in_range_fn is not None and not self.in_range_fn(lat, lon, elev))

    def in_season(self, today: dt.date, planting: dt.date | None, perennial: bool) -> bool:
        if self.season is None or perennial or planting is None:
            return True
        k = (today - planting).days
        return self.season[0] <= k <= self.season[1]


ALL = ["north_america", "south_america", "europe", "africa", "asia", "oceania"]

MODELS: dict[str, Model] = {
    m.id: m
    for m in [
        Model(
            "rice_blast",
            "disease",
            ["rice"],
            rice_blast,
            "BLASTAM criteria (Japanese prefectural forecasting; Yokouchi, Higuchi & Munakata wetness table)",
        ),
        Model(
            "wheat_leaf_rust",
            "disease",
            ["winter_wheat", "spring_wheat", "durum_wheat", "triticale_forage", "spelt"],
            wheat_leaf_rust,
            "Magarey et al. 2005 Table 2 (P. recondita); Roelfs, Singh & Saari 1992",
        ),
        Model(
            "wheat_stem_rust",
            "disease",
            ["winter_wheat", "spring_wheat", "durum_wheat", "triticale_forage", "spelt", "barley"],
            wheat_stem_rust,
            "Roelfs, Singh & Saari 1992; Magarey et al. 2005",
        ),
        Model(
            "late_blight_tropical",
            "disease",
            ["potato", "tomato"],
            tropical_late_blight,
            "Wallin 1962 severity values (BLITECAST, Krause et al. 1975)",
            tropics_only=True,
        ),
        Model(
            "gray_leaf_spot",
            "disease",
            ["maize", "maize_silage", "sweet_corn"],
            gray_leaf_spot,
            "Paul & Munkvold 2005 weather predictors",
            season=(30, 120),
        ),
        Model(
            "coffee_leaf_rust",
            "disease",
            ["coffee"],
            coffee_leaf_rust,
            "Kushalappa & Eskes 1989; Avelino et al. 2015; Magarey et al. 2005",
            tropics_only=True,
        ),
        Model(
            "black_sigatoka",
            "disease",
            ["banana", "plantain"],
            black_sigatoka,
            "Jacome & Schuh 1991, 1992; Magarey et al. 2005",
            tropics_only=True,
        ),
        Model(
            "cassava_whitefly",
            "pest",
            ["cassava"],
            cassava_whitefly,
            "Katono et al. 2021",
            hourly=False,
            regions=["africa", "asia"],
            season=(0, 120),
            min_score=0.55,
        ),
        Model(
            "desert_locust",
            "pest",
            ["*"],
            desert_locust,
            "FAO Desert Locust Guidelines (Symmons & Cressman 2001)",
            hourly=False,
            in_range_fn=lambda lat, lon, _e: in_locust_area(lat, lon),
            min_score=0.55,
        ),
    ]
}


def applies(mid: str, crop_id: str) -> bool:
    c = MODELS[mid].crops
    return crop_id in c or "*" in c


def risk_label(score: float) -> str:
    if score >= 0.85:
        return "severe"
    if score >= 0.55:
        return "high"
    if score >= 0.25:
        return "moderate"
    return "low"
