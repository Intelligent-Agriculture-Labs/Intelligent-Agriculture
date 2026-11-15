"""Rotation strategy explorer.

For each candidate rotation (the farmer's current one + templates from config/rotations.yaml) we
simulate every crop slot over the last N seasons of NASA POWER weather with the IA season model,
then score 7 indicators on a 0–100 scale (higher = better for the farmer):

  water     mean gross irrigation (irrigated) or ET deficit (rainfed), mm/yr
  income    mean gross margin, USD/ha/yr with the field's country prices and costs (science/economics.py,
            ADR-027; rotation effects applied)
  soil      soil-health index: living-root months, residue return, N fixation, rooting-depth diversity
  erosion   RUSLE-inspired relative index Σ_month (bare_fraction × erosive-rain share) × slope factor
  pests     pest-cycle disruption: family diversity, longest same-family run, host breaks
  risk      climate risk: coefficient of variation of margin + share of failed seasons + heat/frost events
  nitrogen  biological N credit, kg N/ha/yr

All formulas and weights are in docs/MODELS.md §Rotations. This is decision *support*: the outputs are
relative comparisons under past weather, not forecasts of profit.
"""

from __future__ import annotations

import datetime as dt
import math
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import yaml

from .cropmodel import Weather, crop, gdd_requirement, simulate

CONFIG = Path(__file__).resolve().parents[1] / "config"
N_PRICE_USD_KG = 1.3  # reference fertilizer-N price (only without a country: see economics.Econ.n_price)
SAME_FAMILY_PENALTY = 0.08  # monoculture yield penalty (literature range ~5–15 %)
AFTER_LEGUME_BONUS = 0.05
SMALLHOLDER_INPUT_SHARE = 0.3  # share of gross revenue spent on inputs in low-input tropical systems (indicative)  # "rotation effect" after a legume (literature range ~5–15 %)


@lru_cache
def rotation_config() -> dict[str, Any]:
    with open(CONFIG / "rotations.yaml") as f:
        cfg: dict[str, Any] = yaml.safe_load(f)
    extra = CONFIG / "crops_extra.yaml"
    if extra.exists():  # sowing dates of the expanded crop set
        with open(extra) as f:
            dp = (yaml.safe_load(f) or {}).get("default_planting") or {}
        cfg["default_planting"] = {**dp, **cfg["default_planting"]}
    return cfg


def climate_zone(lat: float) -> str:
    return "tropical" if abs(lat) < 20 else ("south" if lat < 0 else "north")


# Mediterranean (winter-rain) calendar: spring crops sown in late winter, small grains in autumn
MEDITERRANEAN_PLANTING = {
    "barley": "11-15",
    "safflower": "02-15",
    "sunflower": "03-01",
    "dry_bean": "03-15",
    "potato": "02-15",
    "teff": "04-01",
}


def default_sowing(crop_id: str) -> str:
    """Fallback sowing date (northern temperate calendar) from crop traits when not configured."""
    c = crop(crop_id)
    if c.get("winter_hardy"):
        return "10-01"
    if c["type"] == "perennial":
        return "03-20"
    tb = float(c.get("t_base", 8))
    return "03-25" if tb <= 3 else ("04-20" if tb <= 7 else "05-15")


def is_mediterranean(normals: list[dict[str, float]], lat: float) -> bool:
    cool = [1, 2, 3, 10, 11, 12] if lat >= 0 else [4, 5, 6, 7, 8, 9]
    p_cool = sum(n["precip"] for n in normals if n["month"] in cool)
    p_warm = sum(n["precip"] for n in normals if n["month"] not in cool)
    mild_winter = (
        min(n["tmin"] for n in normals) > 0.0
    )  # Köppen Cs: winter-wet *and* mild (excludes Great Basin)
    return abs(lat) >= 20 and p_cool > 2 * p_warm and p_cool + p_warm < 1000 and mild_winter


# Sacks et al. (2010) calendars used for each IA crop (same table as scripts/build_country_data.py)
SACKS_CALENDARS: dict[str, tuple[str, ...]] = {
    "maize": ("Maize",),
    "maize_silage": ("Maize",),
    "sweet_corn": ("Maize",),
    "winter_wheat": ("Wheat_Winter",),
    "spelt": ("Wheat_Winter",),
    "spring_wheat": ("Wheat",),
    "durum_wheat": ("Wheat_Winter", "Wheat"),
    "barley": ("Barley",),
    "winter_barley": ("Barley_Winter",),
    "oats": ("Oats",),
    "winter_rye": ("Rye_Winter",),
    "triticale_forage": ("Wheat_Winter",),
    "rice": ("Rice",),
    "sorghum": ("Sorghum",),
    "sorghum_sudan": ("Sorghum",),
    "pearl_millet": ("Millet",),
    "soybean": ("Soybeans",),
    "dry_bean": ("Pulses",),
    "cowpea": ("Pulses",),
    "mung_bean": ("Pulses",),
    "pigeon_pea": ("Pulses",),
    "field_pea": ("Pulses",),
    "lentil": ("Pulses",),
    "chickpea": ("Pulses",),
    "faba_bean": ("Pulses",),
    "groundnut": ("Groundnuts",),
    "sunflower": ("Sunflower",),
    "winter_rapeseed": ("Rapeseed_Winter",),
    "cotton": ("Cotton",),
    "potato": ("Potatoes",),
    "sweet_potato": ("Sweet_Potatoes",),
    "cassava": ("Cassava",),
    "sugar_beet": ("Sugarbeets",),
}


@lru_cache
def _sacks_grids() -> dict[str, np.ndarray]:
    path = CONFIG / "crop_calendar_30mn.npz"
    if not path.exists():
        return {}
    z = np.load(path, allow_pickle=False)
    return {k: z[k] for k in z.files}


def local_sowing(crop_id: str, lat: float, lon: float) -> tuple[str, str] | None:
    """Observed sowing date ("MM-DD", source) for a crop at a location (ADR-027); see local_calendar."""
    cal = local_calendar(crop_id, lat, lon)
    return (cal[0], cal[1]) if cal else None


@lru_cache(maxsize=4096)
def local_calendar(crop_id: str, lat: float, lon: float) -> tuple[str, str, int | None] | None:
    """Observed sowing date ("MM-DD", source, season length in days or None) for a crop at a location.

    Sacks et al. (2010) 0.5° crop calendar at the field's cell (or a neighbour within one cell), else the
    median of the field's country (country_data.json), else None (the climate rules below apply). The season
    length (harvest − sowing) sets the thermal-time target, so a late local sowing is not stretched over the
    FAO-56 default season into midsummer."""
    names = SACKS_CALENDARS.get(crop_id)
    if not names or not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    grids = _sacks_grids()
    row = int(np.clip((90.0 - lat) // 0.5, 0, 359))
    col = int(np.clip((lon + 180.0) // 0.5, 0, 719))
    for n in names:
        g = grids.get(n)
        if g is None:
            continue
        for dr, dc in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            r, c = row + dr, (col + dc) % 720
            if 0 <= r < 360 and 0 < int(g[r, c]) <= 366:
                d = dt.date(2001, 1, 1) + dt.timedelta(days=min(364, int(g[r, c]) - 1))
                h = grids.get(n + "_h")
                season = int((int(h[r, c]) - int(g[r, c])) % 365) if h is not None and int(h[r, c]) > 0 else 0
                return (
                    d.strftime("%m-%d"),
                    f"Sacks et al. 2010 crop calendar ({n.replace('_', ' ')}, 0.5° cell)",
                    season if season > 30 else None,
                )
    from .economics import country_of, data

    iso = country_of(lat, lon)
    e = (data()["countries"].get(iso or "") or {}).get("sowing", {}).get(crop_id) if iso else None
    if e:
        d = dt.date(2001, 1, 1) + dt.timedelta(days=min(364, int(e["doy"]) - 1))
        name = data()["countries"][iso]["name"]
        return d.strftime("%m-%d"), f"Sacks et al. 2010 crop calendar, median of {name}", e.get("season_days")
    return None


def _field_rule(crop_id: str, lat: float, rainy_onset_month: int | None, mediterranean: bool) -> str | None:
    """The field-weather sowing rule that applies, if any: these are derived from the field's own NASA rainfall
    (tropical rainy-season onset; Mediterranean winter-rain calendar) and are kept over the observed calendar,
    whose tropical entries are often national-level (Sacks et al. 2010 `political.level`)."""
    if climate_zone(lat) == "tropical" and rainy_onset_month and crop(crop_id)["type"] != "perennial":
        return "IA rainy-season onset rule (field's NASA rainfall)"
    if mediterranean and crop_id in MEDITERRANEAN_PLANTING:
        return "Mediterranean calendar rule (field's NASA rainfall)"
    return None


def observed_calendar(
    crop_id: str,
    lat: float,
    lon: float | None,
    rainy_onset_month: int | None = None,
    mediterranean: bool = False,
) -> tuple[str, str, int | None] | None:
    """The observed local calendar where it replaces the generic temperate default (ADR-027), else None.

    The season length is used only within 0.5–1.15 × the FAO-56 season (calendar cells can mix
    sowing and harvest of different crop types)."""
    if (
        lon is None
        or crop(crop_id)["type"] == "perennial"
        or _field_rule(crop_id, lat, rainy_onset_month, mediterranean)
    ):
        return None
    cal = local_calendar(crop_id, lat, lon)
    if not cal:
        return None
    fao = sum(crop(crop_id)["stages"])
    season = cal[2] if cal[2] and 0.5 * fao <= cal[2] <= 1.15 * fao else None
    return cal[0], cal[1], season


def planting_source(
    crop_id: str,
    lat: float,
    lon: float | None,
    override: str | None = None,
    mediterranean: bool = False,
    rainy_onset_month: int | None = None,
) -> str:
    obs = observed_calendar(crop_id, lat, lon, rainy_onset_month, mediterranean)
    if obs:
        return obs[1]
    rule = _field_rule(crop_id, lat, rainy_onset_month, mediterranean)
    if rule:
        return rule
    if override:
        return "rotation template"
    return "IA temperate calendar (shifted by hemisphere); no observed calendar for this crop here"


def planting_date_for(
    crop_id: str,
    year: int,
    lat: float,
    rainy_onset_month: int | None,
    override: str | None = None,
    mediterranean: bool = False,
    lon: float | None = None,
) -> dt.date:
    # observed local calendar where it replaces the generic temperate default — also over a template's generic
    # "10-01", so templates and the farmer's rotation are compared on the same local sowing date
    obs = observed_calendar(crop_id, lat, lon, rainy_onset_month, mediterranean)
    if obs:
        m, d = (int(x) for x in obs[0].split("-"))
        return dt.date(year, m, min(d, 28))
    md = (
        override
        or (MEDITERRANEAN_PLANTING.get(crop_id) if mediterranean else None)
        or rotation_config()["default_planting"].get(crop_id)
        or default_sowing(crop_id)
    )
    m, d = (int(x) for x in md.split("-"))
    zone = climate_zone(lat)
    if zone == "south":
        m = (m + 5) % 12 + 1
    elif zone == "tropical" and rainy_onset_month and crop(crop_id)["type"] != "perennial":
        winter_crop = crop_id in ("winter_wheat", "triticale_forage", "cover_rye_vetch")
        m = ((rainy_onset_month + (4 if winter_crop else 0)) - 1) % 12 + 1
    return dt.date(year, m, min(d, 28))


def rainy_onset(normals: list[dict[str, float]]) -> int:
    """Month that starts the wettest 4-month window (tropical planting)."""
    p = [n["precip"] for n in normals]
    best = max(range(12), key=lambda i: sum(p[(i + k) % 12] for k in range(4)))
    return best + 1


def _cover_from_kc(c: dict[str, Any], kc: float) -> float:
    span = max(0.05, c["kc_mid"] - 0.15)
    return float(np.clip((kc - 0.15) / span, 0.0, 1.0))


class SlotStats:
    def __init__(self, crop_id: str, results: list[Any], plant: dt.date) -> None:
        self.crop_id = crop_id
        self.results = results
        self.plant = plant
        self.plant_source = ""
        self.c = crop(crop_id)
        ok = [r for r in results if r is not None]
        self.n = len(ok)
        self.yields = [r.yield_t_ha for r in ok]
        self.irr = [r.irrigation_mm for r in ok]
        self.et = [r.et_mm for r in ok]
        self.deficit = [max(0.0, r.etm_mm - r.et_mm) for r in ok]
        self.heat = [r.heat_days for r in ok]
        self.frost = [r.frost_events for r in ok]
        self.length = int(median([(r.end - r.start).days for r in ok])) if ok else 0
        self.kc_daily = ok[len(ok) // 2].daily.get("kc", []) if ok else []
        med = median(self.yields) if self.yields else 0
        self.fail_share = (
            float(np.mean([y < 0.5 * med for y in self.yields])) if self.yields and med > 0 else 0.0
        )


def evaluate_slot(
    crop_id: str,
    w: Weather,
    years: list[int],
    lat: float,
    onset: int | None,
    taw_per_m: float,
    strategy: str,
    method: str,
    allocation_mm: float | None,
    plant_override: str | None,
    irrigate_until: str | None,
    mediterranean: bool = False,
    lon: float | None = None,
) -> SlotStats:
    c = crop(crop_id)
    first = planting_date_for(crop_id, years[0], lat, onset, plant_override, mediterranean, lon)
    # with an observed local calendar the thermal-time target spans the observed sowing → harvest season
    obs = observed_calendar(crop_id, lat, lon, onset, mediterranean)
    req = gdd_requirement(c, w, first, years, obs[2] if obs else None)
    iu: tuple[int, int] | None = None
    if irrigate_until:
        mm, dd = (int(x) for x in irrigate_until.split("-"))
        iu = (mm, dd)
    res: list[Any] = []
    for y in years:
        p = planting_date_for(crop_id, y, lat, onset, plant_override, mediterranean, lon)
        if w.index(p) < 0 or w.index(p) + 30 >= len(w.dates):
            res.append(None)
            continue
        try:
            res.append(
                simulate(
                    crop_id,
                    w,
                    p,
                    taw_per_m=taw_per_m,
                    strategy=strategy,
                    method=method,
                    allocation_mm=allocation_mm,
                    gdd_req=req,
                    record_daily=(y == years[len(years) // 2]),
                    irrigate_until=iu,
                )
            )
        except (ValueError, IndexError):
            res.append(None)
    out = SlotStats(crop_id, res, first)
    out.plant_source = planting_source(crop_id, lat, lon, plant_override, mediterranean, onset)
    return out


def _calendar(slots: list[dict[str, Any]], stats: list[SlotStats], n_years: int) -> list[dict[str, Any]]:
    """Month × year grid of dominant crop and ground cover (0..1)."""
    cal: dict[tuple[int, int], dict[str, Any]] = {
        (y, m): {"crop": None, "cover": 0.0} for y in range(1, n_years + 1) for m in range(1, 13)
    }
    for s, st in zip(slots, stats, strict=True):
        if not st.kc_daily:
            continue
        start = dt.date(2001, st.plant.month, st.plant.day)
        for k, kc in enumerate(st.kc_daily):
            d = start + dt.timedelta(days=k)
            y = s["year"] + (d.year - 2001)
            if y > n_years:
                y -= n_years  # wrap into year 1 (rotation repeats)
            cell = cal[(y, d.month)]
            cov = _cover_from_kc(st.c, kc)
            if st.c["type"] == "perennial":
                cov = max(cov, 0.55)  # established stand protects soil even when dormant
            if cov >= cell["cover"]:
                cell["cover"] = round(cov, 2)
                cell["crop"] = s["crop"]
    # perennial stands occupy the whole year
    for s in slots:
        if crop(s["crop"])["type"] == "perennial":
            for m in range(1, 13):
                cell = cal[(s["year"], m)]
                if cell["crop"] is None:
                    cell["crop"] = s["crop"]
                    cell["cover"] = 0.55
    return [{"year": y, "month": m, **v} for (y, m), v in sorted(cal.items())]


def score_strategy(
    tpl: dict[str, Any],
    stats: list[SlotStats],
    erosive_share: list[float],
    slope_pct: float | None,
    irrigated: bool,
    smallholder: bool = False,
    econ: Any | None = None,
) -> dict[str, Any]:
    """Score one rotation. `econ` (economics.Econ) supplies the field's country prices and costs; without it the
    crop-table reference values are used (and `smallholder` switches to a revenue-share cost, legacy)."""
    slots = tpl["slots"]
    n_years = max(s["year"] for s in slots)
    cal = _calendar(slots, stats, n_years)

    # --- yields with rotation effects, margins per rotation-year
    margins_by_year: list[float] = []
    water_total = 0.0
    deficit_total = 0.0
    n_credit_total = 0.0
    heat = frost = 0.0
    fail = 0.0
    prev_family = None
    prev_legume = False
    alfalfa_run = 0
    for s, st in zip(slots, stats, strict=True):
        c = st.c
        if not st.yields:
            continue
        factor = 1.0
        if prev_family and prev_family == c["family"] and c["type"] != "perennial":
            factor -= SAME_FAMILY_PENALTY
        if prev_legume and c["family"] != "Fabaceae":
            factor += AFTER_LEGUME_BONUS
        if c["type"] == "perennial":
            alfalfa_run += 1
            if alfalfa_run == 1:
                factor *= 0.7  # seeding year
            elif alfalfa_run > 4:
                factor *= max(0.6, 1 - 0.1 * (alfalfa_run - 4))  # stand decline / autotoxicity
        else:
            alfalfa_run = 0
        n_credit = c["n_fix_kg_ha"]
        yld = (
            np.array(st.yields) * factor
        )  # typical yields in config are already in marketed (fresh/hay) weight
        price = econ.price_usd_t(s["crop"]) if econ is not None else c["price_usd_t"]
        n_price = econ.n_price_usd_kg() if econ is not None else N_PRICE_USD_KG
        # fertilizer saved on a non-legume following a legume (≈ 40 kg N/ha credit, valued at N price)
        n_saving = n_price * 40 if (prev_legume and c["family"] != "Fabaceae") else 0.0
        if econ is not None:
            margin = yld * price - econ.cost_usd_ha(s["crop"]) + n_saving
        elif smallholder:
            # config costs are U.S. high-input budgets; for tropical smallholder systems use a uniform
            # input-cost share instead so crops are compared on one basis (documented in MODELS.md §Rotations)
            margin = yld * price * (1 - SMALLHOLDER_INPUT_SHARE) + n_saving
        else:
            margin = yld * price - c["cost_usd_ha"] + n_saving
        margins_by_year.append(float(np.mean(margin)))
        water_total += float(np.mean(st.irr)) if irrigated else 0.0
        deficit_total += float(np.mean(st.deficit))
        n_credit_total += n_credit
        heat += float(np.mean(st.heat))
        frost += float(np.mean(st.frost))
        fail = max(fail, st.fail_share)
        prev_family = c["family"]
        prev_legume = c["family"] == "Fabaceae" or s["crop"] == "cover_rye_vetch"

    margin_yr = sum(margins_by_year) / n_years
    water_yr = water_total / n_years
    deficit_yr = deficit_total / n_years
    n_yr = n_credit_total / n_years

    covers = [c["cover"] for c in cal]
    living_months = sum(1 for c in covers if c >= 0.3) / len(covers)
    bare_days = (1 - living_months) * 365
    residue_score = np.mean(
        [{"high": 1.0, "medium": 0.6, "low": 0.3}[crop(s["crop"])["residue"]] for s in slots]
    )
    roots = [crop(s["crop"])["root_m"][1] for s in slots]
    root_div = min(1.0, (max(roots) - min(roots)) / 1.2) if roots else 0.0
    soil_index = 100 * (
        0.4 * living_months + 0.3 * residue_score + 0.2 * min(1.0, n_yr / 100) + 0.1 * root_div
    )

    # erosion (relative RUSLE-style): bare fraction × erosive-rain share, scaled by slope factor
    ls = 1.0 + (min(slope_pct or 0.0, 20.0) / 5.0)
    erosion_idx = 0.0
    for cell in cal:
        erosion_idx += (1 - cell["cover"]) * erosive_share[cell["month"] - 1]
    erosion_idx = erosion_idx / n_years * ls  # 0 (always covered) .. ~ls (always bare)
    erosion_score = 100 * max(0.0, 1 - erosion_idx / 1.5)

    families = [crop(s["crop"])["family"] for s in slots]
    run = best_run = 1
    for a, b in zip(families, families[1:], strict=False):
        run = run + 1 if a == b else 1
        best_run = max(best_run, run)
    distinct = len(set(families))
    pest_score = 100 * (0.5 * min(1.0, (distinct - 1) / 2) + 0.5 * max(0.0, 1 - (best_run - 1) / 3))

    cv = (
        float(np.std(margins_by_year) / max(1.0, abs(np.mean(margins_by_year))))
        if len(margins_by_year) > 1
        else 0.0
    )
    risk_raw = 0.5 * fail + 0.3 * min(1.0, (heat + frost) / (8 * n_years)) + 0.2 * min(1.0, cv)
    risk_score = 100 * (1 - risk_raw)

    return {
        "calendar": cal,
        "raw": {
            "water": water_yr if irrigated else deficit_yr,
            "income": margin_yr,
            "soil": soil_index,
            "erosion": erosion_idx,
            "pests": pest_score,
            "risk": risk_raw,
            "nitrogen": n_yr,
            "bare_days": bare_days,
        },
        "fixed_scores": {
            "soil": soil_index,
            "erosion": erosion_score,
            "pests": pest_score,
            "risk": risk_score,
        },
        "n_years": n_years,
    }


def relative_scores(
    raws: list[dict[str, float]], key: str, higher_better: bool, floor: float | None = None
) -> list[float]:
    vals = [r[key] for r in raws]
    lo, hi = min(vals), max(vals)
    if floor is not None:
        lo = min(lo, floor)
    if math.isclose(hi, lo):
        return [70.0 for _ in vals]
    out = []
    for v in vals:
        f = (v - lo) / (hi - lo)
        out.append(round(100 * (f if higher_better else 1 - f), 1))
    return out
