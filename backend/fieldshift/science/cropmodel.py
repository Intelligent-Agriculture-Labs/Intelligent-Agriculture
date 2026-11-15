"""Daily crop water balance + yield model ("FieldShift season model").

Components (equations in docs/MODELS.md):
  * Phenology in thermal time: progress = ΣGDD / GDD_req, where GDD_req is calibrated per location as the
    climatological ΣGDD over the crop's FAO-56 season length from the planting date. Warmer scenarios
    therefore shorten the season, as in reality.
  * Crop coefficient Kc: FAO-56 four-stage piecewise-linear curve (single-Kc approach, Ch. 6).
    Alfalfa: per-cutting Kc cycles; a cut happens every `cut_gdd` °C·d.
  * Root-zone water balance: FAO-56 Ch. 8 (eq. 85) bucket with TAW = θ-range × Zr, RAW = p·TAW,
    p adjusted for ETc (Table 22 note), water-stress coefficient Ks (eq. 84), deep percolation on overflow.
  * Irrigation strategies: rainfed, full (refill at RAW), deficit (refill to a fraction), seasonal allocation.
  * Yield: FAO-33 / FAO-56 yield response  1 − Ya/Ym = Ky (1 − ETa/ETm)  (eq. 90), with Ym = typical
    yield × season-completion factor, and penalties for heat at flowering and frost during the season.
  * Biomass diagnostic: AquaCrop-style B = WP* Σ(Tr/ET0) (Steduto et al. 2009) reported for comparison.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"

IRRIGATION_EFFICIENCY = {
    "none": 1.0,
    "drip": 0.90,
    "sprinkler": 0.75,
    "pivot": 0.85,
    "furrow": 0.60,
    "flood": 0.65,
}


@lru_cache
def crops() -> dict[str, dict[str, Any]]:
    """Crop table: crops.yaml plus crops_extra.yaml (expanded, literature-sourced crop set) when present."""
    with open(CONFIG / "crops.yaml") as f:
        out: dict[str, dict[str, Any]] = yaml.safe_load(f)["crops"]
    extra = CONFIG / "crops_extra.yaml"
    if extra.exists():
        with open(extra) as f:
            more = (yaml.safe_load(f) or {}).get("crops", {}) or {}
        for k, v in more.items():
            out.setdefault(k, v)
    return out


def crop(cid: str) -> dict[str, Any]:
    c = crops().get(cid)
    if c is None:
        raise KeyError(f"unknown crop '{cid}'")
    return c


@dataclass
class Weather:
    """Daily driving data. et0 is pre-computed (FAO-56 PM) for the unperturbed climate."""

    dates: list[dt.date]
    tmax: np.ndarray
    tmin: np.ndarray
    rain: np.ndarray
    et0: np.ndarray
    # location for the global yield calibration (science/yieldcal.py); None = uncalibrated
    region: str | None = None
    _zone: str | None = field(default=None, repr=False)
    # ISO 3166 alpha-3 of the field's country (country yield factor, ADR-027); None = region only
    country: str | None = None

    def index(self, d: dt.date) -> int:
        return (d - self.dates[0]).days

    def climate_zone(self) -> str:
        """Köppen–Geiger main group of this record (cached; observed days only)."""
        if self._zone is None:
            from .yieldcal import climate_zone

            self._zone = climate_zone(self.dates, self.tmax, self.tmin, self.rain)
        return self._zone

    def yield_factor(self, crop_id: str, irrigated: bool = False) -> float:
        """Global yield calibration factor for this location (1.0 when the location is unknown)."""
        if self.region is None:
            return 1.0
        from .yieldcal import calibration, factor

        zone = self.climate_zone() if calibration().get("zones") else None
        return factor(crop_id, self.region, zone, irrigated, self.country)

    def perturbed(self, delta_t: float = 0.0, rain_factor: float = 1.0) -> Weather:
        """Simple delta-change climate scenario. ET0 scaled with the FAO-56 temperature sensitivity
        (~ +3 % per °C for typical semi-arid conditions; see docs/MODELS.md) instead of a full re-run."""
        if delta_t == 0 and rain_factor == 1:
            return self
        # the calibration (management / yield gap) stays that of the real location under a scenario
        zone = self.climate_zone() if self.region is not None else None
        return Weather(
            self.dates,
            self.tmax + delta_t,
            self.tmin + delta_t,
            self.rain * rain_factor,
            self.et0 * (1 + 0.03 * delta_t),
            self.region,
            zone,
            self.country,
        )


def gdd(tmax: np.ndarray, tmin: np.ndarray, t_base: float, t_upper: float = 30.0) -> np.ndarray:
    """Growing degree days, method 2 (McMaster & Wilhelm 1997) with upper cut-off."""
    tx = np.clip(tmax, t_base, t_upper)
    tn = np.clip(tmin, t_base, t_upper)
    return np.maximum((tx + tn) / 2 - t_base, 0.0)


def kc_at(c: dict[str, Any], frac: float) -> tuple[float, str, float]:
    """Kc, stage name and root fraction at season progress `frac` (0..1) for annual crops."""
    s = np.array(c["stages"], float)
    cum = np.cumsum(s) / s.sum()
    ini, mid, end = c["kc_ini"], c["kc_mid"], c["kc_end"]
    if frac <= cum[0]:
        return ini, "initial", frac / cum[1]
    if frac <= cum[1]:
        f = (frac - cum[0]) / (cum[1] - cum[0])
        return ini + f * (mid - ini), "development", frac / cum[1]
    if frac <= cum[2]:
        return mid, "mid-season", 1.0
    f = min(1.0, (frac - cum[2]) / (1 - cum[2]))
    return mid + f * (end - mid), "late-season", 1.0


def kc_alfalfa(c: dict[str, Any], cycle_frac: float) -> float:
    """Kc within one cutting cycle (FAO-56 Table 11/12 individual cutting periods)."""
    s = np.array(c["stages"], float)
    cum = np.cumsum(s) / s.sum()
    if cycle_frac <= cum[0]:
        return c["kc_ini"]
    if cycle_frac <= cum[1]:
        f = (cycle_frac - cum[0]) / (cum[1] - cum[0])
        return c["kc_ini"] + f * (c["kc_mid"] - c["kc_ini"])
    if cycle_frac <= cum[2]:
        return c["kc_mid"]
    f = (cycle_frac - cum[2]) / (1 - cum[2])
    return c["kc_mid"] + f * (c["kc_end"] - c["kc_mid"])


@dataclass
class SeasonResult:
    crop: str
    start: dt.date
    end: dt.date
    yield_t_ha: float
    biomass_t_ha: float
    et_mm: float
    etm_mm: float
    irrigation_mm: float  # gross, at the field inlet
    rain_mm: float
    deep_perc_mm: float
    stress_days: int
    heat_days: int
    frost_events: int
    cuts: float = 0.0
    daily: dict[str, list[Any]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    final_depletion_mm: float = 0.0
    final_taw_mm: float = 0.0
    final_raw_mm: float = 0.0
    final_kc: float = 0.0
    final_stage: str = ""


def gdd_requirement(c: dict[str, Any], w: Weather, planting: dt.date, years: list[int]) -> float:
    """Location-calibrated thermal time to maturity: mean ΣGDD over the FAO-56 season length."""
    tot = []
    md = (planting.month, min(planting.day, 28))
    for y in years:
        try:
            s = dt.date(y, *md)
        except ValueError:
            continue
        i0 = w.index(s)
        i1 = i0 + int(sum(c["stages"]))
        if i0 < 0 or i1 > len(w.dates):
            continue
        g = gdd(w.tmax[i0:i1], w.tmin[i0:i1], c["t_base"])
        if np.isfinite(g).sum() > 0.9 * len(g):
            tot.append(np.nansum(g))
    return float(np.mean(tot)) if tot else float(sum(c["stages"]) * 10)


ANTECEDENT_DAYS = 180  # fallow water balance before sowing (EXP-12); 0 = FAO-56 default (deep soil at FC)
FALLOW_KC = 0.3  # bare soil / stubble evaporation coefficient between seasons (FAO-56 Kc_ini order)
FALLOW_START_DEPLETION = 0.6  # profile left near the end-of-season depletion by the previous crop


def antecedent_depletion(w: Weather, i0: int, days: int, taw_max: float) -> float:
    """Relative depletion (0 = field capacity, 1 = wilting point) of the full root zone at sowing, from a
    fallow bucket run over `days` before day index i0. Evaporation declines linearly with depletion
    (stage-2 drying, FAO-56 Ch. 7); rain refills; excess drains."""
    d = FALLOW_START_DEPLETION * taw_max
    for i in range(i0 - days, i0):
        et0 = w.et0[i] if np.isfinite(w.et0[i]) else 0.0
        p_mm = w.rain[i] if np.isfinite(w.rain[i]) else 0.0
        d = d - p_mm + FALLOW_KC * et0 * (1 - d / taw_max)
        d = min(max(d, 0.0), taw_max)
    return float(d / taw_max)


def simulate(
    crop_id: str,
    w: Weather,
    planting: dt.date,
    *,
    taw_per_m: float = 140.0,
    strategy: str = "full",
    method: str = "sprinkler",
    allocation_mm: float | None = None,
    gdd_req: float | None = None,
    initial_depletion_frac: float = 0.3,
    until: dt.date | None = None,
    known_irrigations: dict[dt.date, float] | None = None,
    assimilate: dict[dt.date, float] | None = None,
    assimilation_weight: float = 0.3,
    record_daily: bool = False,
    irrigate_until: tuple[int, int] | None = None,
    irrigate_until_date: dt.date | None = None,
    kc_scale: float = 1.0,
    kc_scale_from: dt.date | None = None,
    antecedent_days: int = ANTECEDENT_DAYS,
) -> SeasonResult:
    """Run one season from `planting`. `until` stops early (used for 'today' state).

    known_irrigations: farmer-reported gross irrigation amounts by date (replace the automatic schedule
    before `until`). assimilate: observed root-zone depletion (mm) by date for nudging (simple
    Newtonian relaxation, weight 0..1) — see docs/MODELS.md §Assimilation.
    """
    c = crop(crop_id)
    perennial = c["type"] == "perennial"
    eff = IRRIGATION_EFFICIENCY.get(method, 0.75) if strategy != "rainfed" else 1.0
    i0 = w.index(planting)
    if i0 < 0:
        raise ValueError("planting date before weather record")
    max_days = 365 if perennial else int(1.6 * sum(c["stages"]))
    i_end = min(len(w.dates), i0 + max_days)
    if until is not None:
        i_end = min(i_end, w.index(until) + 1)
    if gdd_req is None:
        gdd_req = float(sum(c["stages"]) * 10)

    zr_min, zr_max = c["root_m"]
    # soil water below the initial root zone: at field capacity (FAO-56 default), or, with
    # antecedent_days > 0, at the depletion left by a fallow water balance before sowing (EXP-12)
    deep_frac = 0.0
    if antecedent_days > 0 and not perennial and i0 - antecedent_days >= 0:
        deep_frac = antecedent_depletion(w, i0, antecedent_days, taw_per_m * zr_max)
        initial_depletion_frac = deep_frac
    dr = initial_depletion_frac * taw_per_m * zr_min
    zr_prev = zr_min
    g_sum = 0.0
    cycle_g = 0.0
    cuts = 0.0
    et = etm = irr = rain = dp = 0.0
    tr_norm = 0.0
    stress = heat = frost = 0
    frost_penalty = 0.0
    used_alloc = 0.0
    daily: dict[str, list[Any]] = {
        "date": [],
        "kc": [],
        "dr": [],
        "taw": [],
        "raw": [],
        "eta": [],
        "etc": [],
        "irr": [],
        "rain": [],
        "ks": [],
    }
    events: list[dict[str, Any]] = []
    stage = "initial"
    kc = c["kc_ini"]
    taw = raw = 0.0
    end_idx = i_end - 1
    matured = False

    for i in range(i0, i_end):
        d = w.dates[i]
        tmax, tmin = w.tmax[i], w.tmin[i]
        et0 = w.et0[i] if np.isfinite(w.et0[i]) else 0.0
        p_mm = w.rain[i] if np.isfinite(w.rain[i]) else 0.0
        g = (
            float(gdd(np.array([tmax]), np.array([tmin]), c["t_base"])[0])
            if np.isfinite(tmax) and np.isfinite(tmin)
            else 0.0
        )

        if perennial:
            # dormant when cold: no growth, small soil evaporation-only Kc
            active = np.isfinite(tmax) and (tmax + tmin) / 2 > c["t_base"]
            if c.get("evergreen"):
                # evergreen tree/fruit crop (coffee, banana): no cutting cycles; FAO-56 Table 12 mid-season Kc
                # all year while active, the end-season Kc when too cold to grow
                kc = c["kc_mid"] if active else c["kc_end"]
                stage = "evergreen" if active else "cold-rest"
            else:
                cycle_g += g
                if cycle_g >= c["cut_gdd"]:
                    cuts += 1
                    cycle_g = 0.0
                    events.append({"date": d.isoformat(), "type": "cut"})
                kc = kc_alfalfa(c, cycle_g / c["cut_gdd"]) if active else 0.3
                stage = "regrowth" if cycle_g / c["cut_gdd"] < 0.5 else "pre-cut"
            root_frac = 1.0
            # killing frost ends the season after the first two months
            if np.isfinite(tmin) and tmin <= c["t_kill"] and i - i0 > 60:
                end_idx = i
                events.append({"date": d.isoformat(), "type": "killing_frost"})
                break
        else:
            g_sum += g
            frac = min(1.0, g_sum / gdd_req)
            kc, stage, root_frac = kc_at(c, frac)
            hardy = c.get("winter_hardy", False) and stage in (
                "initial",
                "development",
            )  # hardened winter cereals
            t_kill = (
                c.get("t_kill_spring", c["t_kill"]) if c.get("winter_hardy") and not hardy else c["t_kill"]
            )
            if np.isfinite(tmin) and tmin <= t_kill and frac > 0.02 and not hardy:
                events.append({"date": d.isoformat(), "type": "frost", "tmin": round(float(tmin), 1)})
                if frac < 0.8:
                    frost += 1  # damaging frost (late killing frosts end the season instead)
                if frac >= 0.8:
                    # killing frost late in the season ends it: the crop is harvested at its current completion
                    end_idx = i
                    matured = True
                else:
                    # early frost: small loss (growing point protected / replant); mid-season frost at flowering is costly
                    frost_penalty += {"initial": 0.05, "development": 0.15}.get(stage, 0.35)
            if np.isfinite(tmax) and tmax >= c["t_heat"] and stage == "mid-season":
                heat += 1
            if frac >= 1.0:
                end_idx = i
                matured = True

        zr = zr_min + (zr_max - zr_min) * min(1.0, root_frac)
        if kc_scale != 1.0 and kc_scale_from is not None and d >= kc_scale_from:
            kc = (
                kc * kc_scale
            )  # satellite data fusion: observed canopy (Sentinel-2 Kcb) rescales crop water use
        etc = kc * et0
        p_adj = float(np.clip(c["p"] + 0.04 * (5 - etc), 0.1, 0.8))
        taw = taw_per_m * zr
        raw = p_adj * taw
        # root growth brings in soil below the old root front at field capacity (deep_frac = 0) or at
        # its antecedent depletion
        if zr > zr_prev:
            dr += deep_frac * taw_per_m * (zr - zr_prev)
            zr_prev = zr
        dr = min(dr, taw)

        # irrigation decision (net depth), made at the start of the day
        i_net = 0.0
        if known_irrigations and d in known_irrigations:
            i_net = known_irrigations[d] * eff
        elif (
            strategy != "rainfed"
            and (irrigate_until is None or (d.month, d.day) <= irrigate_until)
            and (irrigate_until_date is None or d <= irrigate_until_date)
        ):
            if dr >= raw:
                target = {"full": 0.0, "deficit_75": 0.25, "deficit_50": 0.5, "allocation": 0.0}.get(
                    strategy, 0.0
                )
                need = max(0.0, dr - target * taw)
                if strategy == "allocation" and allocation_mm is not None:
                    need = min(need, max(0.0, allocation_mm * eff - used_alloc))
                if strategy in ("deficit_75", "deficit_50"):
                    # deficit irrigation: let depletion reach a deeper level before irrigating
                    trigger = raw + (0.25 if strategy == "deficit_75" else 0.45) * (taw - raw)
                    need = need if dr >= trigger else 0.0
                i_net = need
                used_alloc += need
        if i_net > 0:
            events.append({"date": d.isoformat(), "type": "irrigation", "mm": round(i_net / eff, 1)})

        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / max(1e-6, taw - raw))
        eta = ks * etc
        dr = dr - p_mm - i_net + eta
        if dr < 0:
            dp += -dr
            dr = 0.0
        if assimilate and d in assimilate:
            dr = (1 - assimilation_weight) * dr + assimilation_weight * min(assimilate[d], taw)
        dr = min(dr, taw)

        et += eta
        etm += etc
        irr += i_net / eff
        rain += p_mm
        if et0 > 0:
            tr_norm += ks * max(0.0, kc - 0.15) * 1.0  # Tr/ET0 with ~0.15 soil-evaporation share removed
        if ks < 0.9 and kc > c["kc_ini"]:
            stress += 1
        if record_daily:
            daily["date"].append(d.isoformat())
            daily["kc"].append(round(kc, 3))
            daily["dr"].append(round(dr, 1))
            daily["taw"].append(round(taw, 1))
            daily["raw"].append(round(raw, 1))
            daily["eta"].append(round(eta, 2))
            daily["etc"].append(round(etc, 2))
            daily["irr"].append(round(i_net / eff, 1))
            daily["rain"].append(round(p_mm, 1))
            daily["ks"].append(round(ks, 3))
        if matured:
            break

    # ---- yield
    ratio = et / etm if etm > 0 else 1.0
    water_factor = max(0.0, 1 - c["ky"] * (1 - ratio))
    if perennial and c.get("evergreen"):
        # annual yield of an established stand, pro rata for the part of the year simulated
        ym = c["typical_yield_t_ha"] * min(1.0, (end_idx - i0 + 1) / 365.0)
    elif perennial:
        partial = cycle_g / c["cut_gdd"]
        cuts_eff = cuts + (partial if partial >= 0.7 else 0.0)
        ym = (
            c["typical_yield_t_ha"] / 4.5 * cuts_eff
        )  # typical yield corresponds to ~4.5 cuts in the U.S. West
        cuts = cuts_eff
    else:
        completion = min(1.0, g_sum / gdd_req) if gdd_req > 0 else 1.0
        ym = c["typical_yield_t_ha"] * (completion**2)
    heat_factor = max(0.5, 1 - 0.03 * heat)
    frost_factor = max(0.2, 1 - frost_penalty)
    # global calibration against FAOSTAT (ADR-022): potential-yield × regional management factor
    ya = ym * water_factor * heat_factor * frost_factor * w.yield_factor(crop_id, strategy != "rainfed")
    biomass = c["wp"] * tr_norm * c.get("calib", 1.0) / 100.0  # g/m2 -> t/ha

    end_date = w.dates[min(end_idx, len(w.dates) - 1)]
    return SeasonResult(
        crop=crop_id,
        start=planting,
        end=end_date,
        yield_t_ha=round(float(ya), 2),
        biomass_t_ha=round(float(biomass), 2),
        et_mm=round(et, 1),
        etm_mm=round(etm, 1),
        irrigation_mm=round(irr, 1),
        rain_mm=round(rain, 1),
        deep_perc_mm=round(dp, 1),
        stress_days=stress,
        heat_days=heat,
        frost_events=frost,
        cuts=round(cuts, 1),
        daily=daily if record_daily else {},
        events=events,
        final_depletion_mm=round(dr, 1),
        final_taw_mm=round(taw, 1),
        final_raw_mm=round(raw, 1),
        final_kc=round(kc, 3),
        final_stage=stage,
    )
