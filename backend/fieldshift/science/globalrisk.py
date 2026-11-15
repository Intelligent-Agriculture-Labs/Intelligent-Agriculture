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
        d = wp.start.date()
        if s > best.get(d, 0.0):
            best[d] = s
            per[d] = wp
    return best, per


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
# (tmin, topt, tmax in °C for the infection process; wmin/wmax = wetness hours at optimum / upper cap)
P_RICE_BLAST = {"tmin": 8.0, "topt": 28.0, "tmax": 35.0, "wmin": 8.0, "wmax": 24.0}
P_LEAF_RUST = {"tmin": 2.0, "topt": 20.0, "tmax": 30.0, "wmin": 4.0, "wmax": 16.0}
P_STEM_RUST = {"tmin": 2.0, "topt": 20.0, "tmax": 35.0, "wmin": 6.0, "wmax": 16.0}
P_COFFEE_RUST = {"tmin": 15.0, "topt": 22.0, "tmax": 28.0, "wmin": 6.0, "wmax": 48.0}
P_SIGATOKA = {"tmin": 12.0, "topt": 27.0, "tmax": 36.0, "wmin": 6.0, "wmax": 48.0}
P_GLS = {"tmin": 14.0, "topt": 27.0, "tmax": 35.0, "wmin": 11.0, "wmax": 24.0}
P_NLB = {"tmin": 10.0, "topt": 20.0, "tmax": 30.0, "wmin": 6.0, "wmax": 18.0}


def rice_blast(x: RiskInput) -> RiskResult:
    """Leaf/neck blast (Magnaporthe oryzae). Infection when a wet period of mean temperature 15–25 °C (BLASTAM
    window) meets the Magarey W(T) requirement, and only when the preceding 5-day mean temperature is
    20–25 °C (BLASTAM susceptibility condition; Koshimizu 1988, Hashimoto et al. 1984)."""
    r = _infection_model(P_RICE_BLAST, t_lo=15.0, t_hi=25.0)(x)
    tmean = (np.asarray(x.tmax) + np.asarray(x.tmin)) / 2
    for d in list(r.scores):
        i = x.di(d)
        prev = tmean[max(0, i - 5) : i] if i > 0 else np.array([])
        m5 = float(np.nanmean(prev)) if len(prev) else float("nan")
        if not (np.isfinite(m5) and 20.0 <= m5 <= 25.0):
            if r.scores[d] > 0:
                r.evidence.setdefault(d, []).append(
                    f"Previous 5-day mean temperature {m5:.1f} °C is outside 20–25 °C: plants are less susceptible (BLASTAM)."
                )
            r.scores[d] = round(r.scores[d] * 0.3, 3)
        elif r.scores[d] > 0:
            r.evidence.setdefault(d, []).append(
                f"Previous 5-day mean temperature {m5:.1f} °C (BLASTAM 20–25 °C: susceptible)."
            )
    return r


def tropical_late_blight(x: RiskInput) -> RiskResult:
    """Late blight in the tropics: Wallin (1962) severity values as used by BLITECAST (Krause et al. 1975)
    and SimCast (Grünwald et al. 2002, validated in the Toluca highlands, Mexico).
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
        d = wp.start.date()
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
    """Maize gray leaf spot (Cercospora zeae-maydis): long humid periods (RH ≥ 90 %) at warm temperatures;
    infection needs ≥ 11–13 h of high humidity near 22–30 °C (Rupe, Siegel & Hartman 1982; Beckman & Payne 1982),
    expressed with the Magarey W(T) curve (Wmin 11 h at Topt 27 °C). Dry gaps of ≤ 2 h tolerated (spores survive
    short dry spells; Magarey et al. 2005)."""
    return _infection_model(P_GLS, gap=2)(x)


def northern_leaf_blight(x: RiskInput) -> RiskResult:
    """Northern corn leaf blight (Exserohilum turcicum): moderate temperatures 18–27 °C with ≥ 6 h dew
    (Levy & Cohen 1983)."""
    return _infection_model(P_NLB)(x)


def wheat_leaf_rust(x: RiskInput) -> RiskResult:
    """Wheat leaf rust (Puccinia triticina): urediniospores need free water; infection with ≥ 3–4 h dew near
    15–20 °C, more at cooler/warmer temperatures (Roelfs, Singh & Saari 1992, Table 2; Magarey et al. 2005)."""
    return _infection_model(P_LEAF_RUST, method="dpd")(x)


def wheat_stem_rust(x: RiskInput) -> RiskResult:
    """Wheat stem rust (Puccinia graminis f. sp. tritici): ≥ 6–8 h dew at 15–24 °C, followed by light
    (Roelfs, Singh & Saari 1992). Warmer than leaf/stripe rust."""
    return _infection_model(P_STEM_RUST, method="dpd")(x)


def coffee_leaf_rust(x: RiskInput) -> RiskResult:
    """Coffee leaf rust (Hemileia vastatrix): germination needs liquid water and ~21–25 °C; infection needs
    ≥ 6 h wetness at the optimum (Kushalappa & Eskes 1989; Nutman, Roberts & Clarke 1963)."""
    return _infection_model(P_COFFEE_RUST, gap=2)(x)


def black_sigatoka(x: RiskInput) -> RiskResult:
    """Banana black Sigatoka (Pseudocercospora/Mycosphaerella fijiensis): ascospore infection with long wet
    periods at 20–30 °C (Jacome & Schuh 1992; Jacome, Schuh & Stevenson 1991)."""
    return _infection_model(P_SIGATOKA, gap=2)(x)


# --------------------------------------------------------------------------- insect / locust (daily data)
def cassava_whitefly(x: RiskInput) -> RiskResult:
    """Bemisia tabaci on cassava (vector of cassava mosaic disease). Populations build when it is warm and fairly
    dry; heavy rain knocks adults down. Score for each day: warm-and-dry index over the preceding 14 days —
    mean temperature within 20–32 °C (fast development; lower threshold ~10–11 °C) and ≤ 30 mm rain
    (Legg 1995; Fishpool & Burban 1994; Sseruwagi et al. 2003)."""
    r = RiskResult()
    tmean = (np.asarray(x.tmax) + np.asarray(x.tmin)) / 2
    for k, d in enumerate(x.dates):
        if k < 14:
            continue
        tm = float(np.nanmean(tmean[k - 14 : k]))
        rn = float(np.nansum(x.rain[k - 14 : k]))
        if not np.isfinite(tm):
            continue
        warm = 1.0 if 20 <= tm <= 32 else max(0.0, 1 - min(abs(tm - 20), abs(tm - 32)) / 6)
        dry = 1.0 if rn <= 30 else max(0.0, 1 - (rn - 30) / 70)
        r.scores[d] = round(warm * dry, 3)
        r.evidence[d] = [f"Last 14 days: mean temperature {tm:.1f} °C, rain {rn:.0f} mm."]
    return r


def desert_locust(x: RiskInput) -> RiskResult:
    """Desert locust breeding conditions in recession areas (FAO Desert Locust Guidelines, Cressman & Elliott;
    Symmons & Cressman 2001): ≥ 25 mm rain in a month moistens the sand to 10–15 cm for egg-laying and greens
    annual vegetation; eggs develop and hoppers appear ~2–6 weeks later if temperatures are warm (mean ≥ 20 °C).
    Score: 30-day rain/25 mm (capped 1) × warm factor."""
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
            f"Rain in the last 30 days: {rn:.0f} mm (FAO breeding guide: ≥ 25 mm); mean temperature {tm:.1f} °C."
        ]
    return r


# --------------------------------------------------------------------------- geography
# Fields wetter than this (10-year mean annual rain) are outside the arid/semi-arid breeding habitat.
LOCUST_MAX_ANNUAL_RAIN_MM = 500.0

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
            "BLASTAM criteria (Koshimizu 1988) with the Magarey et al. 2005 wetness–temperature curve",
        ),
        Model(
            "wheat_leaf_rust",
            "disease",
            ["winter_wheat", "spring_wheat", "durum_wheat", "triticale_forage", "spelt"],
            wheat_leaf_rust,
            "Roelfs, Singh & Saari 1992; Magarey et al. 2005",
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
            "Wallin 1962 severity values (BLITECAST, Krause et al. 1975; SimCast, Grünwald et al. 2002)",
            tropics_only=True,
        ),
        Model(
            "gray_leaf_spot",
            "disease",
            ["maize", "maize_silage", "sweet_corn"],
            gray_leaf_spot,
            "Rupe et al. 1982; Magarey et al. 2005",
            season=(30, 120),
        ),
        Model(
            "northern_leaf_blight",
            "disease",
            ["maize", "maize_silage", "sweet_corn", "sorghum"],
            northern_leaf_blight,
            "Levy & Cohen 1983; Magarey et al. 2005",
            season=(20, 120),
        ),
        Model(
            "coffee_leaf_rust",
            "disease",
            ["coffee"],
            coffee_leaf_rust,
            "Kushalappa & Eskes 1989; Magarey et al. 2005",
            tropics_only=True,
        ),
        Model(
            "black_sigatoka",
            "disease",
            ["banana", "plantain"],
            black_sigatoka,
            "Jacome & Schuh 1992; Magarey et al. 2005",
            tropics_only=True,
        ),
        Model(
            "cassava_whitefly",
            "pest",
            ["cassava"],
            cassava_whitefly,
            "Legg 1995; Sseruwagi et al. 2003",
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
