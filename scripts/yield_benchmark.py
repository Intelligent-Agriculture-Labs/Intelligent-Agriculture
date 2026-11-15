"""Global yield benchmark and calibration (docs/VALIDATION.md V10, EXPERIMENTS EXP-12, ADR-022).

Runs on the data box (VPS). Three steps, each reproducible from open data:

    # 0. open data (≈ 250 MB): FAOSTAT QCL bulk, MIRCA2000 v1.1 (Zenodo 10.5281/zenodo.7422506),
    #    UN M49 country→region table
    python scripts/yield_benchmark.py download --raw ~/yieldbench/raw
    # 1. benchmark sites: country × crop pairs, 1–3 MIRCA2000 cropland cells each, sowing months and
    #    irrigated share from MIRCA2000; FAOSTAT yields 2000→latest; 0.5° region grid for the app
    python scripts/yield_benchmark.py prepare --raw ~/yieldbench/raw
    # 2. FieldShift season model at every site, rain-fed and irrigated, every season, NASA POWER weather
    python scripts/yield_benchmark.py simulate
    # 3. level + anomaly metrics, leave-one-country-out calibration, tables; --write-config updates
    #    backend/fieldshift/config/yield_calibration.yaml (single-threaded BLAS: ~10 s instead of minutes)
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python scripts/yield_benchmark.py evaluate --write-config
    # EXP-12 comparison without the antecedent soil-water spin-up (writes *_nospin outputs)
    python scripts/yield_benchmark.py simulate --tag nospin --spinup 0
    python scripts/yield_benchmark.py evaluate --tag nospin

Use the backend venv for every step; `download` also needs network access (≈ 1 GB unpacked, kept outside
the repo). NASA POWER responses are cached by the backend's HTTP layer (FIELDSHIFT_CACHE_DIR).

Outputs live in docs/validation/yield_benchmark/ (sites.csv, faostat.csv, sims.csv.gz, results.json,
tables.md). The simulation is uncalibrated (Weather has no region); calibration is a multiplicative
factor on the attainable yield, so it is applied after the fact here exactly as the app applies it.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import math
import os
import sys
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("FIELDSHIFT_CIRCUIT_BREAKER", "0")

OUT = ROOT / "docs" / "validation" / "yield_benchmark"
CONFIG = ROOT / "backend" / "fieldshift" / "config"
FIRST_YEAR = 2000
# A 250 m SoilGrids point is arbitrary for a 0.5° benchmark cell (and the API timed out for most cells),
# so the app's documented loam default (140 mm/m) is used unless --soil is given.
USE_SOIL = False
SIM_KW: dict[str, Any] = {}  # extra simulate() options for model experiments (EXP-12)
TAG = ""  # output suffix for experiment runs

ZENODO = "https://zenodo.org/api/records/7422506/files/{}.zip/content"
FAOSTAT_URL = (
    "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)
M49_URL = "https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.csv"

# Sacks et al. (2010) crop-calendar names: key -> (main calendar, winter-type calendar or None)
SACKS = {
    "wheat": ("Wheat", "Wheat.Winter"),
    "maize": ("Maize", None),
    "rice": ("Rice", None),
    "barley": ("Barley", "Barley.Winter"),
    "millet": ("Millet", None),
    "sorghum": ("Sorghum", None),
    "soybean": ("Soybeans", None),
    "potato": ("Potatoes", None),
    "cassava": ("Cassava", None),
    "groundnut": ("Groundnuts", None),
    "beans": ("Pulses", None),
    "cotton": ("Cotton", None),
    # sugarcane: not in Sacks; MIRCA2000 lists it Jan–Dec -> planting rule in _sugarcane_month()
}
SACKS_URL = "https://sage-public-files.s3.amazonaws.com/crop-calendar-dataset/arcgis0.5deg/ALL_CROPS_ArcINFO_0.5deg_{}.tar"
WINTER_KILL_T = -10.0  # coldest-month mean below which wheat/barley are spring-sown (winter-kill risk)

# Benchmark crops: key -> (MIRCA2000 crop class, FAOSTAT item code, FieldShift crop or rule)
CROPS: dict[str, tuple[int, int, str]] = {
    "wheat": (1, 15, "winter_wheat|spring_wheat"),
    "maize": (2, 56, "maize"),
    "rice": (3, 27, "rice"),
    "barley": (4, 44, "winter_barley|barley"),
    "millet": (6, 79, "pearl_millet"),
    "sorghum": (7, 83, "sorghum"),
    "soybean": (8, 236, "soybean"),
    "potato": (10, 116, "potato"),
    "cassava": (11, 125, "cassava"),
    "sugarcane": (12, 156, "sugarcane"),
    "groundnut": (16, 242, "groundnut"),
    "beans": (17, 176, "dry_bean"),  # MIRCA 'pulses' areas locate the sites; FAOSTAT 'Beans, dry' yields
    "cotton": (21, 767, "cotton"),  # FAOSTAT cotton lint (FieldShift cotton yields are lint)
}
COTTON_LINT, COTTON_SEED = 767, 328
# Alfalfa: FAOSTAT publishes no alfalfa/forage yields, so it cannot be benchmarked here.

# Main producers across Köppen zones (ISO 3166 numeric = UN M49 = MIRCA2000 unit code // 1000)
COUNTRIES: dict[int, str] = {
    840: "United States",
    124: "Canada",
    484: "Mexico",
    76: "Brazil",
    32: "Argentina",
    600: "Paraguay",
    250: "France",
    276: "Germany",
    724: "Spain",
    380: "Italy",
    616: "Poland",
    826: "United Kingdom",
    804: "Ukraine",
    643: "Russia",
    398: "Kazakhstan",
    860: "Uzbekistan",
    792: "Türkiye",
    504: "Morocco",
    818: "Egypt",
    364: "Iran",
    586: "Pakistan",
    356: "India",
    50: "Bangladesh",
    156: "China",
    360: "Indonesia",
    704: "Viet Nam",
    764: "Thailand",
    608: "Philippines",
    36: "Australia",
    710: "South Africa",
    566: "Nigeria",
    231: "Ethiopia",
    404: "Kenya",
    834: "Tanzania",
    562: "Niger",
    466: "Mali",
    854: "Burkina Faso",
    894: "Zambia",
    454: "Malawi",
    288: "Ghana",
    716: "Zimbabwe",
}
MIN_AREA_HA = 100_000  # FAOSTAT mean harvested area for a country × crop pair to be benchmarked
MAX_SITES = 3
MIN_SEP_DEG = 2.5

# UN M49 sub-region -> FieldShift macro region
M49_REGION = {
    "Northern America": "northern_america",
    "Latin America and the Caribbean": "latin_america",
    "Western Europe": "western_europe",
    "Northern Europe": "western_europe",
    "Southern Europe": "southern_europe",
    "Eastern Europe": "eastern_europe_central_asia",
    "Central Asia": "eastern_europe_central_asia",
    "Northern Africa": "middle_east_north_africa",
    "Western Asia": "middle_east_north_africa",
    "Sub-Saharan Africa": "sub_saharan_africa",
    "Southern Asia": "south_asia",
    "Eastern Asia": "east_asia",
    "South-eastern Asia": "southeast_asia",
    "Australia and New Zealand": "oceania",
    "Melanesia": "oceania",
    "Micronesia": "oceania",
    "Polynesia": "oceania",
}
REGIONS = sorted(set(M49_REGION.values()))

# Documented national drought / heat seasons (harvest year) used for the anomaly check.
DROUGHT_EVENTS: list[tuple[int, str, int, str]] = [
    (840, "maize", 2012, "2012 U.S. Corn Belt drought (USDA ERS)"),
    (840, "soybean", 2012, "2012 U.S. drought (USDA ERS)"),
    (643, "wheat", 2010, "2010 Russian heatwave and drought (FAO GIEWS)"),
    (398, "wheat", 2012, "2012 Kazakhstan drought (FAO GIEWS)"),
    (36, "wheat", 2006, "2006 Millennium Drought (ABARES)"),
    (36, "wheat", 2019, "2018–19 eastern Australia drought (ABARES)"),
    (710, "maize", 2016, "2015–16 El Niño drought, southern Africa (FAO GIEWS)"),
    (894, "maize", 2016, "2015–16 El Niño drought (FAO GIEWS)"),
    (716, "maize", 2016, "2015–16 El Niño drought (FAO GIEWS)"),
    (454, "maize", 2016, "2015–16 El Niño drought (FAO GIEWS)"),
    (32, "soybean", 2009, "2008–09 Pampas drought (Bolsa de Cereales)"),
    (32, "soybean", 2018, "2017–18 Pampas drought (Bolsa de Cereales)"),
    (32, "soybean", 2023, "2022–23 Pampas drought (Bolsa de Cereales)"),
    (504, "wheat", 2016, "2015–16 Morocco drought (FAO GIEWS)"),
    (504, "wheat", 2007, "2007 Morocco drought (FAO GIEWS)"),
    (724, "barley", 2005, "2004–05 Iberian drought (AEMET)"),
    (724, "barley", 2012, "2011–12 Iberian drought (AEMET)"),
    (724, "wheat", 2023, "2022–23 Iberian drought (AEMET)"),
    (276, "wheat", 2018, "2018 central-European drought (DWD)"),
    (250, "wheat", 2003, "2003 European heatwave (Ciais et al., 2005)"),
    (356, "rice", 2002, "2002 monsoon failure (IMD)"),
    (356, "rice", 2009, "2009 monsoon failure (IMD)"),
    (484, "maize", 2011, "2011 Mexico drought and Sinaloa freeze (SIAP)"),
    (804, "maize", 2020, "2020 Ukraine drought (FAO GIEWS)"),
    (404, "maize", 2009, "2008–09 Kenya long-rains failure (FEWS NET)"),
]


# =========================================================================== helpers
def _r(p: Path) -> Path:
    return p.expanduser().resolve()


def read_asc(path: Path, dtype: Any = float) -> np.ndarray:
    with gzip.open(path, "rt") as f:
        hdr = [next(f) for _ in range(6)]
        nodata = float(hdr[5].split()[1])
        arr = np.loadtxt(f, dtype=dtype)
    arr = arr.astype(float)
    arr[arr == nodata] = np.nan
    return arr


def cell_center(row: int, col: int) -> tuple[float, float]:
    return 90.0 - (row + 0.5) * 0.5, -180.0 + (col + 0.5) * 0.5


def months_len(start: int, end: int) -> int:
    return (end - start) % 12 + 1


# =========================================================================== 0. download
def cmd_download(a: argparse.Namespace) -> None:
    import httpx

    raw = _r(Path(a.raw))
    raw.mkdir(parents=True, exist_ok=True)
    jobs = {
        f"{n}.zip": ZENODO.format(n)
        for n in ("condensed_cropping_calendars", "unit_code_grid", "harvested_area_grids")
    }
    jobs["faostat_qcl.zip"] = FAOSTAT_URL
    jobs["m49.csv"] = M49_URL
    for kind in ("unfilled", "filled"):
        jobs[f"sacks_{kind}.tar"] = SACKS_URL.format(kind)
    for name, url in jobs.items():
        dst = raw / name
        if dst.exists():
            continue
        print("download", url)
        with httpx.stream("GET", url, follow_redirects=True, timeout=600) as r:
            r.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        if name.endswith(".zip"):
            with zipfile.ZipFile(dst) as z:
                z.extractall(raw / name[:-4])
        if name.endswith(".tar"):  # Sacks: a tar of per-crop .tar.gz
            import tarfile

            sub = raw / ("sacks" if "unfilled" in name else "sacks_fill")
            sub.mkdir(exist_ok=True)
            with tarfile.open(dst) as t:
                t.extractall(sub, filter="data")
            for tgz in sub.glob("*.tar.gz"):
                d = sub / tgz.name[: -len(".tar.gz")]
                d.mkdir(exist_ok=True)
                with tarfile.open(tgz) as t:
                    t.extractall(d, filter="data")


def _find(raw: Path, pattern: str) -> Path:
    hits = sorted(raw.rglob(pattern))
    if not hits:
        raise FileNotFoundError(f"{pattern} under {raw}")
    return hits[0]


# =========================================================================== 1. prepare
def load_faostat(raw: Path) -> dict[tuple[int, str], dict[int, dict[str, float]]]:
    """{(m49, crop_key): {year: {'yield': t/ha, 'area': ha}}} for the benchmark countries and crops."""
    item2crop = {v[1]: k for k, v in CROPS.items()}
    item2crop[COTTON_SEED] = "cotton"
    out: dict[tuple[int, str], dict[int, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    lint: dict[tuple[int, int], float] = {}
    path = _find(raw, "Production_Crops_Livestock_E_All_Data_(Normalized).csv")
    with open(path, encoding="latin-1") as f:
        for row in csv.DictReader(f):
            if row["Element"] not in ("Yield", "Area harvested", "Production"):
                continue
            item = int(row["Item Code"])
            if item not in item2crop:
                continue
            # cotton: lint yield = lint production / seed-cotton harvested area (FAOSTAT has no lint yield)
            if row["Element"] == "Production" and item != COTTON_LINT:
                continue
            if item == COTTON_SEED and row["Element"] != "Area harvested":
                continue
            m49 = int(row["Area Code (M49)"].strip("'"))
            if m49 not in COUNTRIES:
                continue
            year = int(row["Year"])
            if year < FIRST_YEAR or not row["Value"]:
                continue
            v = float(row["Value"])
            if row["Element"] == "Production":
                lint[(m49, year)] = v  # tonnes
                continue
            if row["Element"] == "Yield":
                unit = row["Unit"]
                v = v / 1000.0 if unit == "kg/ha" else (v / 10000.0 if unit == "hg/ha" else v)
                out[(m49, item2crop[item])][year]["yield"] = v
            else:
                out[(m49, item2crop[item])][year]["area"] = v
    for (m49, year), prod in lint.items():
        a = out.get((m49, "cotton"), {}).get(year, {}).get("area")
        if a and a > 0:
            out[(m49, "cotton")][year]["yield"] = prod / a
    return out


def load_m49(raw: Path) -> dict[int, str]:
    """ISO numeric -> FieldShift macro region (UN M49 sub-region; intermediate region for Latin America)."""
    out: dict[int, str] = {}
    with open(raw / "m49.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row["country-code"]:
                continue
            sub = row["sub-region"]
            if sub in M49_REGION:
                out[int(row["country-code"])] = M49_REGION[sub]
    return out


def load_calendars(raw: Path) -> dict[str, dict[tuple[int, int], list[tuple[float, int, int]]]]:
    """MIRCA2000 condensed crop calendars: {'irc'|'rfc': {(unit, class): [(area, start, end), ...]}}."""
    out: dict[str, dict[tuple[int, int], list[tuple[float, int, int]]]] = {}
    for tag, fname in (
        ("irc", "cropping_calendar_irrigated.txt.gz"),
        ("rfc", "cropping_calendar_rainfed.txt.gz"),
    ):
        d: dict[tuple[int, int], list[tuple[float, int, int]]] = {}
        with gzip.open(_find(raw, fname), "rt") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3 or not parts[0].isdigit():
                    continue
                unit, cls, n = int(parts[0]), int(parts[1]), int(parts[2])
                subs = []
                for k in range(n):
                    a_, s_, e_ = parts[3 + 3 * k : 6 + 3 * k]
                    subs.append((float(a_), int(s_), int(e_)))
                d[(unit, cls)] = subs
        out[tag] = d
    return out


def unit_grid_30mn(raw: Path) -> np.ndarray:
    """Majority MIRCA2000 calendar unit per 0.5° cell (from the 5' unit grid)."""
    u = read_asc(_find(raw, "unit_code.asc.gz"))
    u = np.nan_to_num(u, nan=0).astype(np.int64)
    blocks = u.reshape(360, 6, 720, 6).transpose(0, 2, 1, 3).reshape(360, 720, 36)
    out = np.zeros((360, 720), np.int64)
    for r in range(360):
        for c in range(720):
            b = blocks[r, c]
            b = b[b > 0]
            if b.size:
                vals, cnt = np.unique(b, return_counts=True)
                out[r, c] = vals[np.argmax(cnt)]
    return out


def pick_sites(total: np.ndarray, mask: np.ndarray) -> list[tuple[int, int, float]]:
    """Up to MAX_SITES cells with the largest harvested area, ≥ MIN_SEP_DEG apart, ≥ 10 % of the top cell."""
    a = np.where(mask, np.nan_to_num(total), 0.0)
    order = np.argsort(a, axis=None)[::-1]
    chosen: list[tuple[int, int, float]] = []
    top = None
    for idx in order[:5000]:
        r, c = divmod(int(idx), a.shape[1])
        v = float(a[r, c])
        if v <= 0:
            break
        top = top or v
        if v < 0.1 * top:
            break
        lat, lon = cell_center(r, c)
        if any(
            max(
                abs(lat - cell_center(rr, cc)[0]),
                abs(lon - cell_center(rr, cc)[1]) * math.cos(math.radians(lat)),
            )
            < MIN_SEP_DEG
            for rr, cc, _ in chosen
        ):
            continue
        chosen.append((r, c, v))
        if len(chosen) >= MAX_SITES:
            break
    return chosen


def calendar_for(
    cal: dict[tuple[int, int], list[tuple[float, int, int]]], unit: int, cls: int, country: int
) -> tuple[int, int] | None:
    """MIRCA2000 condensed calendar: dominant sub-crop (largest area) in the unit, else in the country."""
    subs = [s for s in cal.get((unit, cls), []) if s[0] > 0]
    if not subs:
        subs = [s for (u, k), v in cal.items() if k == cls and u // 1000 == country for s in v if s[0] > 0]
    if not subs:
        return None
    a, s, e = max(subs, key=lambda x: x[0])
    return s, e


def read_sacks(raw: Path, name: str, filled: bool) -> tuple[np.ndarray, np.ndarray] | None:
    """Sacks et al. (2010) 0.5° mean planting and harvest day of year (NaN where no data)."""
    d = f"{name}.crop.calendar" + (".fill" if filled else "")
    base = raw / ("sacks_fill" if filled else "sacks") / d / d
    out = []
    for var in ("plant", "harvest"):
        f = base / f"{var}.asc"
        if not f.exists():
            return None
        txt = f.read_text().split("\n", 6)[6]
        a = np.array(txt.split(), float).reshape(360, 720)
        a[a > 1e19] = np.nan
        out.append(a)
    return out[0], out[1]


def sacks_at(
    grid: tuple[np.ndarray, np.ndarray] | None, r: int, c: int, search: int = 1
) -> tuple[int, int] | None:
    """Value at the cell, else the nearest cell with data within `search` cells."""
    if grid is None:
        return None
    plant, harv = grid
    for k in range(search + 1):
        best = None
        for rr in range(r - k, r + k + 1):
            for cc in range(c - k, c + k + 1):
                if 0 <= rr < 360 and np.isfinite(plant[rr, cc % 720]) and np.isfinite(harv[rr, cc % 720]):
                    best = (int(round(plant[rr, cc % 720])), int(round(harv[rr, cc % 720])))
                    break
            if best:
                return best
    return None


def season_days(plant: int, harvest: int) -> int:
    return (harvest - plant) % 365 or 365


def fs_crop(rule: str, plant: int, harvest: int) -> str:
    """FieldShift crop for a calendar: winter_* (≥ 200-day season, overwintering) or the short-season type."""
    if "|" not in rule:
        return rule
    winter, spring = rule.split("|")
    return winter if season_days(plant, harvest) >= 200 else spring


def month_mid_doy(m: int) -> int:
    return dt.date(2001, m, 15).timetuple().tm_yday


def site_calendar(
    ck: str,
    rule: str,
    sacks: dict[str, tuple[Any, Any]],
    cals: dict[str, Any],
    r: int,
    c: int,
    unit: int,
    cls: int,
    cc: int,
) -> dict[str, Any]:
    """Sowing/harvest day of year for a site. Order: Sacks et al. 2010 observed calendar (cell or neighbour),
    Sacks climate-extrapolated ('filled'), MIRCA2000 condensed calendar (mid-month). Wheat/barley keep
    both the winter- and spring-type calendar when the source is ambiguous; the simulate step then
    applies the coldest-month rule on the site's NASA POWER climate."""
    out: dict[str, Any] = {
        "plant_doy": "",
        "harvest_doy": "",
        "cal_source": "",
        "alt_plant_doy": "",
        "alt_harvest_doy": "",
    }
    if ck == "sugarcane":
        out["cal_source"] = "planting rule (MIRCA2000 lists Jan–Dec)"
        return out
    main = sacks.get("main")
    winter = sacks.get("winter")
    m_obs = sacks_at(main[0], r, c) if main else None
    w_obs = sacks_at(winter[0], r, c) if winter else None
    if m_obs and w_obs:
        out.update(
            plant_doy=w_obs[0],
            harvest_doy=w_obs[1],
            alt_plant_doy=m_obs[0],
            alt_harvest_doy=m_obs[1],
            cal_source="Sacks 2010 (winter and spring types: coldest-month rule)",
        )
    elif w_obs or m_obs:
        p, h = w_obs or m_obs  # type: ignore[misc]
        out.update(plant_doy=p, harvest_doy=h, cal_source="Sacks 2010")
    elif winter:
        wf = sacks_at(winter[1], r, c, 0)
        mf = sacks_at(main[1], r, c, 0) if main else None
        if wf and mf:
            out.update(
                plant_doy=wf[0],
                harvest_doy=wf[1],
                alt_plant_doy=mf[0],
                alt_harvest_doy=mf[1],
                cal_source="Sacks 2010 filled (winter and spring types: coldest-month rule)",
            )
    elif main:
        mf = sacks_at(main[1], r, c, 0)
        if mf:
            out.update(plant_doy=mf[0], harvest_doy=mf[1], cal_source="Sacks 2010 filled")
    if out["plant_doy"] == "":
        cal = calendar_for(cals["rfc"], unit, cls, cc) or calendar_for(cals["irc"], unit, cls, cc)
        if cal:
            out.update(
                plant_doy=month_mid_doy(cal[0]),
                harvest_doy=month_mid_doy(cal[1]),
                cal_source="MIRCA2000 unit",
            )
    return out


def cmd_prepare(a: argparse.Namespace) -> None:
    raw = _r(Path(a.raw))
    OUT.mkdir(parents=True, exist_ok=True)
    fao = load_faostat(raw)
    m49 = load_m49(raw)
    cals = load_calendars(raw)
    units = unit_grid_30mn(raw)
    country = units // 1000

    # ---- 0.5° region grid for the app (region index + 1; 0 = water / unknown)
    reg = np.zeros(units.shape, np.uint8)
    for code in np.unique(country):
        if code > 0 and int(code) in m49:
            reg[country == code] = REGIONS.index(m49[int(code)]) + 1
    np.savez_compressed(CONFIG / "region_grid_30mn.npz", region=reg, names=np.array(REGIONS))
    print("region grid:", {n: int((reg == i + 1).sum()) for i, n in enumerate(REGIONS)})

    # ---- FAOSTAT table
    with open(OUT / "faostat.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["m49", "country", "crop", "year", "yield_t_ha", "area_ha"])
        for (cc, ck), years in sorted(fao.items()):
            for y, v in sorted(years.items()):
                if "yield" in v:
                    w.writerow(
                        [
                            cc,
                            COUNTRIES[cc],
                            ck,
                            y,
                            round(v["yield"], 4),
                            round(v.get("area", float("nan")), 1),
                        ]
                    )

    # ---- sites
    rows = []
    for ck, (cls, _item, rule) in CROPS.items():
        sk = SACKS.get(ck)
        sacks = {
            kind: (read_sacks(raw, name, False), read_sacks(raw, name, True))
            for kind, name in (("main", sk[0] if sk else None), ("winter", sk[1] if sk else None))
            if name
        }
        irc = read_asc(_find(raw, f"annual_area_harvested_irc_crop{cls:02d}_ha_30mn.asc.gz"))
        rfc = read_asc(_find(raw, f"annual_area_harvested_rfc_crop{cls:02d}_ha_30mn.asc.gz"))
        tot = np.nan_to_num(irc) + np.nan_to_num(rfc)
        for cc in COUNTRIES:
            years = fao.get((cc, ck), {})
            areas = [v["area"] for v in years.values() if "area" in v]
            ylds = [v for v in years.values() if "yield" in v]
            if not areas or np.mean(areas) < MIN_AREA_HA or len(ylds) < 10:
                continue
            for r, c, area in pick_sites(tot, country == cc):
                lat, lon = cell_center(r, c)
                unit = int(units[r, c])
                share = float(np.nan_to_num(irc[r, c]) / max(area, 1e-9))
                row: dict[str, Any] = {
                    "m49": cc,
                    "country": COUNTRIES[cc],
                    "region": m49.get(cc, ""),
                    "crop": ck,
                    "lat": round(lat, 3),
                    "lon": round(lon, 3),
                    "mirca_unit": unit,
                    "area_ha": round(area, 1),
                    "irrigated_share": round(share, 3),
                }
                row.update(site_calendar(ck, rule, sacks, cals, r, c, unit, cls, cc))
                row["rfc"] = int(np.nan_to_num(rfc[r, c]) > 0)
                row["irc"] = int(np.nan_to_num(irc[r, c]) > 0)
                rows.append(row)
    with open(OUT / "sites.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    pairs = {(r["m49"], r["crop"]) for r in rows}
    print(f"{len(rows)} sites, {len(pairs)} country×crop pairs, {len({r['m49'] for r in rows})} countries")


# =========================================================================== 2. simulate
def _weather(lat: float, lon: float) -> tuple[Any, float, dict[str, Any]]:
    from fieldshift.data import sources
    from fieldshift.science import et0 as et0mod
    from fieldshift.science.cropmodel import Weather

    start, end = dt.date(1990, 1, 1), dt.date(2025, 9, 30)
    power = sources.power_daily(lat, lon, start, end)
    elev = power.meta.get("power_elevation_m") or 0.0
    doy = np.array([d.timetuple().tm_yday for d in power.dates])
    et0 = et0mod.et0_pm(
        power["T2M_MAX"],
        power["T2M_MIN"],
        power["ALLSKY_SFC_SW_DWN"],
        power["WS2M"],
        lat,
        elev,
        doy,
        tdew=power["T2MDEW"],
    )
    hs = et0mod.et0_hargreaves(power["T2M_MAX"], power["T2M_MIN"], lat, doy)
    et0 = np.where(np.isfinite(et0), et0, hs)
    rain = power["PRECTOTCORR"]
    w = Weather(
        list(power.dates), power["T2M_MAX"], power["T2M_MIN"], np.where(np.isfinite(rain), rain, 0.0), et0
    )
    soil = None
    if USE_SOIL:
        try:
            soil = sources.soil(lat, lon)
        except Exception as e:  # SoilGrids is best effort; loam default as in the app
            print("soil unavailable", lat, lon, e)
    taw = float(soil["taw_mm_per_m"]) if soil else 140.0
    return w, taw, {"texture": soil["texture"] if soil else "loam (default)", "elev": elev}


def _sugarcane_month(w: Any) -> int:
    """Sugarcane planting month: rainy-season onset where rain-fed cane is possible (≥ 600 mm/yr), else the
    month after the coldest month (spring planting of irrigated cane, e.g. Egypt, Pakistan)."""
    months = np.array([d.month for d in w.dates])
    years = len(w.dates) / 365.25
    if float(np.nansum(w.rain)) / years >= 600:
        return _wettest_start(w)
    t = (w.tmax + w.tmin) / 2
    coldest = int(np.argmin([np.nanmean(t[months == m]) for m in range(1, 13)])) + 1
    return coldest % 12 + 1


def _wettest_start(w: Any) -> int:
    """Start month of the wettest 3-month window (rainy-season onset; used for sugarcane, which MIRCA2000
    lists as Jan–Dec)."""
    months = np.array([d.month for d in w.dates])
    pm = np.array([np.nanmean(w.rain[months == m]) for m in range(1, 13)])
    s3 = [pm[m] + pm[(m + 1) % 12] + pm[(m + 2) % 12] for m in range(12)]
    return int(np.argmax(s3)) + 1


def _coldest_month(w: Any) -> float:
    months = np.array([d.month for d in w.dates])
    t = (w.tmax + w.tmin) / 2
    return float(min(np.nanmean(t[months == m]) for m in range(1, 13)))


def doy_date(year: int, doy: int) -> dt.date:
    return dt.date(year, 1, 1) + dt.timedelta(days=min(max(int(doy), 1), 365) - 1)


def simulate_site(site: dict[str, Any], years: list[int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from fieldshift.science.cropmodel import crop, gdd_requirement, simulate
    from fieldshift.science.yieldcal import climate_zone

    lat, lon = float(site["lat"]), float(site["lon"])
    w, taw, meta = _weather(lat, lon)
    hist = [i for i, d in enumerate(w.dates) if d.year <= 2024]
    zone = climate_zone([w.dates[i] for i in hist], w.tmax[hist], w.tmin[hist], w.rain[hist])
    meta.update({"zone": zone, "taw_mm_per_m": taw})
    rule = CROPS[site["crop"]][2]
    if site["crop"] == "sugarcane":
        m = _sugarcane_month(w)
        plant, harvest = month_mid_doy(m), month_mid_doy((m + 8) % 12 or 12)
    elif site["plant_doy"] == "":
        return [], meta | {"error": "no calendar"}
    else:
        plant, harvest = int(site["plant_doy"]), int(site["harvest_doy"])
        if site["alt_plant_doy"] != "":  # winter vs spring type ambiguous: winter-kill rule on POWER climate
            tc = _coldest_month(w)
            meta["coldest_month_c"] = round(tc, 1)
            if tc < WINTER_KILL_T:
                plant, harvest = int(site["alt_plant_doy"]), int(site["alt_harvest_doy"])
    cid = fs_crop(rule, plant, harvest)
    meta.update({"plant_doy": plant, "harvest_doy": harvest, "fs_crop": cid})
    c = crop(cid)
    crosses = harvest < plant  # harvest in the following calendar year (FAOSTAT counts the harvest year)
    req = gdd_requirement(c, w, doy_date(2001, plant), list(range(2000, 2021)))
    out = []
    for tag, strategy in (("irc", "full"), ("rfc", "rainfed")):
        if str(site.get(tag, "1")) != "1":
            continue
        for y in years:
            p = doy_date(y - 1 if crosses else y, plant)
            try:
                r = simulate(
                    cid, w, p, taw_per_m=taw, strategy=strategy, method="sprinkler", gdd_req=req, **SIM_KW
                )
            except (ValueError, IndexError):
                continue
            if r.end > w.dates[-1] - dt.timedelta(days=1):
                continue
            out.append(
                {
                    "site": site["site_id"],
                    "setting": tag,
                    "fs_crop": cid,
                    "year": y,
                    "yield": r.yield_t_ha,
                    "eta_etm": round(r.et_mm / r.etm_mm, 3) if r.etm_mm > 0 else 1.0,
                    "heat_days": r.heat_days,
                    "frost": r.frost_events,
                    "harvest": r.end.isoformat(),
                    "irr_mm": r.irrigation_mm,
                }
            )
    return out, meta


def read_sites() -> list[dict[str, Any]]:
    with open(OUT / "sites.csv") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):
        r["site_id"] = i
    return rows


def _set_tag(a: argparse.Namespace) -> None:
    global TAG
    TAG = f"_{a.tag}" if a.tag else ""
    if a.spinup is not None:
        SIM_KW["antecedent_days"] = a.spinup


def cmd_simulate(a: argparse.Namespace) -> None:
    global USE_SOIL
    USE_SOIL = a.soil
    _set_tag(a)
    sites = read_sites()
    years = list(range(FIRST_YEAR, 2025))
    res: list[dict[str, Any]] = []
    meta: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(simulate_site, s, years): s for s in sites}
        for k, fut in enumerate(as_completed(futs), 1):
            s = futs[fut]
            try:
                rows, m = fut.result()
            except Exception as e:  # keep going; failures are listed in results.json
                print("FAILED", s["country"], s["crop"], s["lat"], s["lon"], repr(e)[:200], flush=True)
                meta[s["site_id"]] = {"error": repr(e)[:200]}
                continue
            res.extend(rows)
            meta[s["site_id"]] = m
            if k % 10 == 0:
                print(f"{k}/{len(sites)} sites", flush=True)
    with gzip.open(OUT / f"sims{TAG}.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0]))
        w.writeheader()
        w.writerows(sorted(res, key=lambda r: (r["site"], r["setting"], r["year"])))
    with open(OUT / f"site_meta{TAG}.json", "w") as f:
        json.dump({str(k): v for k, v in sorted(meta.items())}, f, indent=1)
    print(f"{len(res)} simulated seasons")


# =========================================================================== 3. evaluate
def national_series(
    sites: list[dict[str, Any]], sims: list[dict[str, Any]], meta: dict[str, Any]
) -> list[dict[str, Any]]:
    """Per country × crop: area-weighted (irrigated/rain-fed mixed by MIRCA share) simulated yield per year."""
    by_site: dict[int, dict[str, dict[int, dict[str, Any]]]] = defaultdict(lambda: defaultdict(dict))
    for r in sims:
        by_site[int(r["site"])][r["setting"]][int(r["year"])] = r
    pairs: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for s in sites:
        pairs[(int(s["m49"]), s["crop"])].append(s)
    out = []
    for (cc, ck), ss in sorted(pairs.items()):
        years: dict[int, float] = {}
        irr_part: dict[int, float] = {}
        for y in range(FIRST_YEAR, 2025):
            num = den = num_i = 0.0
            for s in ss:
                sim = by_site.get(int(s["site_id"]), {})
                share = float(s["irrigated_share"])
                yi = sim.get("irc", {}).get(y)
                yr = sim.get("rfc", {}).get(y)
                if yi is None and yr is None:
                    continue
                if yi is None:
                    v, vi = float(yr["yield"]), 0.0  # type: ignore[index]
                elif yr is None:
                    v = vi = float(yi["yield"])
                else:
                    vi = share * float(yi["yield"])
                    v = vi + (1 - share) * float(yr["yield"])
                wgt = float(s["area_ha"])
                num += wgt * v
                num_i += wgt * vi
                den += wgt
            if den > 0:
                years[y] = num / den
                irr_part[y] = num_i / den
        # pair attributes: dominant FieldShift crop and climate zone (largest site / setting)
        main = max(ss, key=lambda s: float(s["area_ha"]))
        dom = meta.get(str(main["site_id"]), {}).get("fs_crop", "")
        zone = meta.get(str(main["site_id"]), {}).get("zone", "")
        irr = sum(float(s["irrigated_share"]) * float(s["area_ha"]) for s in ss) / sum(
            float(s["area_ha"]) for s in ss
        )
        out.append(
            {
                "m49": cc,
                "country": main["country"],
                "region": main["region"],
                "crop": ck,
                "fs_crop": dom,
                "zone": zone,
                "irrigated_share": irr,
                "n_sites": len(ss),
                "sim": years,
                "sim_irr": irr_part,
            }
        )
    return out


def _detrended(years: list[int], v: np.ndarray) -> np.ndarray:
    x = np.array(years, float)
    b = np.polyfit(x, v, 1)
    return np.asarray(v - np.polyval(b, x))


def fit_rank1(
    rows: list[dict[str, Any]], lam_crop: float, lam_group: float, lam_sens: float, anchored: bool = False
) -> dict[str, dict[str, float]]:
    """log(obs/sim) = a_crop + s_crop · b_region: one regional yield-gap factor b, scaled per crop by a
    'gap sensitivity' s (shrunk towards 1); alternating ridge least squares.

    anchored (two-stage): a_crop is first fixed from the reference regions alone (where the crops.yaml
    typical yields come from: the potential-yield factor), and those regions get no gap term (b = 0).
    Crops never grown in a reference region keep a free a_crop in the second stage."""
    crops_ = sorted({r["fs_crop"] for r in rows})
    fixed: dict[str, float] = {}
    if anchored:
        ref: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            if r["region"] in REFERENCE_REGIONS:
                ref[r["fs_crop"]].append(r["log_ratio"])
        fixed = {c: float(np.sum(v) / (len(v) + lam_crop)) for c, v in ref.items()}
        rows = [r for r in rows if r["region"] not in REFERENCE_REGIONS]
    free = [c for c in crops_ if c not in fixed]
    regs = sorted({r["region"] for r in rows})
    fi_ = {c: i for i, c in enumerate(free)}
    si = {c: i for i, c in enumerate(crops_)}
    ri = {g: i for i, g in enumerate(regs)}
    n = len(rows)
    y = np.array([r["log_ratio"] - fixed.get(r["fs_crop"], 0.0) for r in rows])
    F = np.zeros((n, len(free)))
    S = np.zeros((n, len(crops_)))
    R = np.zeros((n, len(regs)))
    for k, r in enumerate(rows):
        if r["fs_crop"] in fi_:
            F[k, fi_[r["fs_crop"]]] = 1
        S[k, si[r["fs_crop"]]] = 1
        R[k, ri[r["region"]]] = 1
    sens = np.ones(len(crops_))
    a = np.zeros(len(free))
    b = np.zeros(len(regs))
    for _ in range(200):
        X = np.hstack([F, R * (S @ sens)[:, None]])
        lam = np.r_[np.full(len(free), lam_crop), np.full(len(regs), lam_group)]
        beta = np.linalg.solve(X.T @ X + np.diag(lam), X.T @ y)
        a, b = beta[: len(free)], beta[len(free) :]
        rb = R @ b
        X = np.hstack([F, S * rb[:, None]])
        lam = np.r_[np.full(len(free), lam_crop), np.full(len(crops_), lam_sens)]
        beta = np.linalg.solve(X.T @ X + np.diag(lam), X.T @ (y - rb))
        a, sens_new = beta[: len(free)], 1 + beta[len(free) :]
        done = np.max(np.abs(sens_new - sens)) < 1e-7
        sens = sens_new
        if done:
            break
    region = dict(zip(regs, map(float, b), strict=True))
    if anchored:
        region |= {g: 0.0 for g in sorted(REFERENCE_REGIONS)}
    return {
        "fs_crop": fixed | dict(zip(free, map(float, a), strict=True)),
        "sens": dict(zip(crops_, map(float, sens), strict=True)),
        "region": region,
    }


def fit_factors(
    rows: list[dict[str, Any]], groups: list[str], lam_crop: float, lam_group: float
) -> dict[str, dict[str, float]]:
    """Ridge least squares on log(obs/sim) = a_crop + Σ b_group; each pair weighs 1. Returns log factors."""
    names: list[tuple[str, str]] = []
    for r in rows:
        for key in ["fs_crop", *groups]:
            if (key, r[key]) not in names:
                names.append((key, r[key]))
    ix = {n: i for i, n in enumerate(names)}
    X = np.zeros((len(rows), len(names)))
    y = np.zeros(len(rows))
    for k, r in enumerate(rows):
        y[k] = r["log_ratio"]
        for key in ["fs_crop", *groups]:
            X[k, ix[(key, r[key])]] = 1.0
    lam = np.array(
        [
            lam_crop if key == "fs_crop" else (LAM_INT if key == "crop_region" else lam_group)
            for key, _ in names
        ]
    )
    beta = np.linalg.solve(X.T @ X + np.diag(lam), X.T @ y)
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for (key, val), b in zip(names, beta, strict=True):
        out[key][val] = float(b)
    return out


ADOPTED_MODEL = "anchored crop+region×sensitivity"
ANCHOR = "anchored"  # pseudo-group: no gap term in the reference regions
REFERENCE_REGIONS = {"northern_america", "western_europe", "southern_europe"}
SENS = "gap_sensitivity"  # pseudo-group: rank-1 crop × region interaction (fit_rank1)
LAM_SENS = 1.0
LAM_INT = 4.0
IRR = "irrigation"  # pseudo-group: one multiplicative factor on the irrigated part of the national mix
IRR_GRID = np.exp(np.linspace(math.log(0.6), math.log(2.5), 39))


def _sim_with_irr(r: dict[str, Any], fi: float) -> float:
    return fi * r["sim_irr_mean"] + (r["sim_mean"] - r["sim_irr_mean"])


def fit_model(
    rows: list[dict[str, Any]], groups: list[str], lam_crop: float, lam_group: float
) -> tuple[dict[str, dict[str, float]], float]:
    """Ridge fit of the log factors; with the irrigation pseudo-group, the irrigated factor is chosen by
    grid search (minimum training sum of squared log errors) and the rest refitted for each value."""
    plain = [g for g in groups if g not in (IRR, SENS, ANCHOR)]

    def fit(rr: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        if SENS in groups:
            return fit_rank1(rr, lam_crop, lam_group, LAM_SENS, ANCHOR in groups)
        return fit_factors(rr, plain, lam_crop, lam_group)

    if IRR not in groups:
        return fit(rows), 1.0
    best: tuple[float, dict[str, dict[str, float]], float] | None = None
    for fi in IRR_GRID:
        rr = [dict(r, log_ratio=math.log(r["obs_mean"] / _sim_with_irr(r, fi))) for r in rows]
        fac = fit(rr)
        sse = sum((r["log_ratio"] - predict_log(r, fac, plain)) ** 2 for r in rr)
        if best is None or sse < best[0]:
            best = (sse, fac, float(fi))
    assert best is not None
    return best[1], best[2]


def calibrated_mean(
    r: dict[str, Any], fac: dict[str, dict[str, float]], groups: list[str], fi: float
) -> float:
    plain = [g for g in groups if g not in (IRR, SENS, ANCHOR)]
    return _sim_with_irr(r, fi) * math.exp(predict_log(r, fac, plain))


def predict_log(r: dict[str, Any], fac: dict[str, dict[str, float]], groups: list[str]) -> float:
    v = fac.get("fs_crop", {}).get(r["fs_crop"], 0.0)
    if "sens" in fac:  # rank-1 model: region effect scaled by the crop's gap sensitivity
        return float(
            np.clip(
                v + fac["sens"].get(r["fs_crop"], 1.0) * fac["region"].get(r["region"], 0.0),
                math.log(0.1),
                math.log(2.0),
            )
        )
    for g in groups:
        v += fac.get(g, {}).get(r[g], 0.0)
    return float(np.clip(v, math.log(0.1), math.log(2.0)))


def level_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """rows carry 'obs_mean', 'sim_mean' (already calibrated if wanted). Ratio = sim/obs."""
    if not rows:
        return {}
    ratio = np.array([r[key] / r["obs_mean"] for r in rows])
    lr = np.log(ratio)
    bias = np.array([r[key] - r["obs_mean"] for r in rows])
    return {
        "n_pairs": len(rows),
        "median_ratio": round(float(np.median(ratio)), 2),
        "bias_t_ha": round(float(np.mean(bias)), 2),
        "rmsle": round(float(np.sqrt(np.mean(lr**2))), 3),
        "mape_pct": round(float(np.mean(np.abs(ratio - 1)) * 100), 1),
        "within_30pct": round(float(np.mean(np.abs(ratio - 1) <= 0.3)), 2),
    }


def cmd_evaluate(a: argparse.Namespace) -> None:
    global LAM_SENS, LAM_INT
    _set_tag(a)
    LAM_SENS, LAM_INT = a.lam_sens, a.lam_int
    sites = read_sites()
    with gzip.open(OUT / f"sims{TAG}.csv.gz", "rt") as f:
        sims = list(csv.DictReader(f))
    meta = json.loads((OUT / f"site_meta{TAG}.json").read_text())
    obs: dict[tuple[int, str], dict[int, float]] = defaultdict(dict)
    with open(OUT / "faostat.csv") as f:
        for r in csv.DictReader(f):
            obs[(int(r["m49"]), r["crop"])][int(r["year"])] = float(r["yield_t_ha"])
    rows = []
    for p in national_series(sites, sims, meta):
        o = obs.get((p["m49"], p["crop"]), {})
        yrs = sorted(set(o) & set(p["sim"]))
        if len(yrs) < 10:
            continue
        ov = np.array([o[y] for y in yrs])
        sv = np.array([p["sim"][y] for y in yrs])
        if ov.mean() <= 0 or sv.mean() <= 0:
            continue
        p.update(
            {
                "years": yrs,
                "obs": ov.tolist(),
                "sim_series": sv.tolist(),
                "obs_mean": float(ov.mean()),
                "sim_mean": float(sv.mean()),
                "sim_irr_mean": float(np.mean([p["sim_irr"][y] for y in yrs])),
                "crop_region": f"{p['fs_crop']}|{p['region']}",
                "log_ratio": float(np.log(ov.mean() / sv.mean())),
            }
        )
        # anomaly correlation on linearly detrended series (FAOSTAT trends are mostly technology)
        if sv.std() > 1e-6:
            p["anom_r"] = float(np.corrcoef(_detrended(yrs, ov), _detrended(yrs, sv))[0, 1])
        else:
            p["anom_r"] = float("nan")
        rows.append(p)
    print(f"{len(rows)} pairs evaluated")

    # ---- candidate calibration structures, leave-one-country-out
    candidates = {
        "crop": [],
        "crop+zone": ["zone"],
        "crop+region": ["region"],
        "crop+region+zone": ["region", "zone"],
        "crop+region+irrigation": ["region", IRR],
        "crop+region×crop (ridge)+irrigation": ["region", "crop_region", IRR],
        "crop+region×sensitivity": [SENS],
        "crop+region×sensitivity+irrigation": [SENS, IRR],
        "anchored crop+region×sensitivity": [SENS, ANCHOR],
        "anchored crop+region×sensitivity+irrigation": [SENS, ANCHOR, IRR],
    }
    lam_c, lam_g = a.lam_crop, a.lam_group
    countries = sorted({r["m49"] for r in rows})
    cv: dict[str, dict[str, Any]] = {}
    held: dict[str, list[dict[str, Any]]] = {}
    for name, groups in candidates.items():
        preds = []
        for cc in countries:
            train = [r for r in rows if r["m49"] != cc]
            fac, fi = fit_model(train, groups, lam_c, lam_g)
            for r in rows:
                if r["m49"] == cc:
                    q = dict(r)
                    q["cal_mean"] = calibrated_mean(r, fac, groups, fi)
                    preds.append(q)
        held[name] = preds
        cv[name] = level_metrics(preds, "cal_mean")
    before = level_metrics(rows, "sim_mean")
    # Adopted structure (ADR-022): not simply the lowest RMSLE. The best five structures are within
    # 0.015 RMSLE of each other on held-out countries; the anchored one keeps the crop potential factors
    # tied to the reference regions where crops.yaml typical yields come from, so high-input systems
    # are not pulled down by low-input ones (unanchored fits put Iowa maize at ~0.7 of observed).
    best = a.model or ADOPTED_MODEL
    print("before", before)
    for k, v in cv.items():
        print(f"LOCO {k:18s}", v)
    print("selected:", best)

    groups = candidates[best]
    final, final_fi = fit_model(rows, groups, lam_c, lam_g)

    def breakdown(key: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for val in sorted({r[key] for r in rows}):
            b = [r for r in rows if r[key] == val]
            h = [r for r in held[best] if r[key] == val]
            out[val] = {
                "before": level_metrics(b, "sim_mean"),
                "after_loco": level_metrics(h, "cal_mean"),
                "median_anom_r": round(float(np.nanmedian([r["anom_r"] for r in b])), 2),
                "share_anom_r_pos": round(float(np.nanmean([r["anom_r"] > 0 for r in b])), 2),
            }
        return out

    # ---- documented drought years: rank of the event year in the simulated (detrended) series
    events = []
    for cc, ck, y, label in DROUGHT_EVENTS:
        r = next((r for r in rows if r["m49"] == cc and r["crop"] == ck), None)
        if r is None or y not in r["years"]:
            events.append(
                {
                    "event": label,
                    "country": COUNTRIES[cc],
                    "crop": ck,
                    "year": y,
                    "status": "not in benchmark",
                }
            )
            continue
        yrs = r["years"]
        sa = _detrended(yrs, np.array(r["sim_series"]))
        oa = _detrended(yrs, np.array(r["obs"]))
        rank_s = int(np.argsort(np.argsort(sa))[yrs.index(y)]) + 1
        rank_o = int(np.argsort(np.argsort(oa))[yrs.index(y)]) + 1
        events.append(
            {
                "event": label,
                "country": COUNTRIES[cc],
                "crop": ck,
                "year": y,
                "n_years": len(yrs),
                "rank_simulated": rank_s,
                "rank_faostat": rank_o,
                "sim_anomaly_pct": round(float(sa[yrs.index(y)] / np.mean(r["sim_series"]) * 100), 1),
                "obs_anomaly_pct": round(float(oa[yrs.index(y)] / np.mean(r["obs"]) * 100), 1),
            }
        )

    results = {
        "generated": dt.date.today().isoformat(),
        "n_pairs": len(rows),
        "n_countries": len(countries),
        "n_sites": len(sites),
        "ridge": {
            "lambda_crop": lam_c,
            "lambda_group": lam_g,
            "lambda_sensitivity": LAM_SENS,
            "lambda_interaction": LAM_INT,
        },
        "before": before,
        "loco_after": cv,
        "selected_model": best,
        "factors": {
            k: {kk: round(vv if k == "sens" else math.exp(vv), 3) for kk, vv in v.items()}
            for k, v in final.items()
        }
        | {"irrigated": round(final_fi, 3)},
        "by_crop": breakdown("fs_crop"),
        "by_zone": breakdown("zone"),
        "by_region": breakdown("region"),
        "anomaly": {
            "median_r": round(float(np.nanmedian([r["anom_r"] for r in rows])), 2),
            "share_r_pos": round(float(np.nanmean([r["anom_r"] > 0 for r in rows])), 2),
            "share_r_gt_0_4": round(float(np.nanmean([r["anom_r"] > 0.4 for r in rows])), 2),
        },
        "drought_events": events,
        "pairs": [
            {
                k: (round(v, 3) if isinstance(v, float) else v)
                for k, v in r.items()
                if k not in ("sim", "obs", "sim_series", "years")
            }
            | {
                "cal_mean_loco": round(
                    next(
                        h["cal_mean"] for h in held[best] if h["m49"] == r["m49"] and h["crop"] == r["crop"]
                    ),
                    3,
                )
            }
            for r in rows
        ],
    }
    (OUT / f"results{TAG}.json").write_text(json.dumps(results, indent=1, default=float))
    (OUT / f"tables{TAG}.md").write_text(tables_md(results))
    print((OUT / f"tables{TAG}.md").read_text())
    if a.write_config:
        write_config(results, final, groups, rows, final_fi)


def tables_md(res: dict[str, Any]) -> str:
    sel = res["selected_model"]
    lines = [
        f"Pairs: {res['n_pairs']} country × crop, {res['n_countries']} countries, {res['n_sites']} sites. "
        f"Adopted structure: **{sel}** (ADR-022). After = leave-one-country-out (factors fitted without the country).",
        "",
    ]
    lines += [
        "| Calibration | RMSLE | median sim/obs | mean bias (t/ha) | within ±30 % |",
        "|---|---|---|---|---|",
    ]
    b = res["before"]
    lines.append(
        f"| none (before) | {b['rmsle']} | {b['median_ratio']} | {b['bias_t_ha']} | {b['within_30pct']:.0%} |"
    )
    for k, v in res["loco_after"].items():
        lines.append(
            f"| {k} (held-out) | {v['rmsle']} | {v['median_ratio']} | {v['bias_t_ha']} | {v['within_30pct']:.0%} |"
        )
    for title, key in (("crop", "by_crop"), ("climate zone", "by_zone"), ("region", "by_region")):
        lines += [
            "",
            f"By {title} (after = held-out country, model '{sel}'):",
            "",
            "| | pairs | sim/obs before | RMSLE before | sim/obs after | RMSLE after | within ±30 % after | anomaly r (median) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for val, m in res[key].items():
            bb, aa = m["before"], m["after_loco"]
            lines.append(
                f"| {val} | {bb['n_pairs']} | {bb['median_ratio']} | {bb['rmsle']} | {aa['median_ratio']} | "
                f"{aa['rmsle']} | {aa['within_30pct']:.0%} | {m['median_anom_r']} |"
            )
    lines += [
        "",
        "Documented drought seasons (rank 1 = worst of the detrended series):",
        "",
        "| Event | Country | Crop | Year | Rank simulated | Rank FAOSTAT | Sim. anomaly | FAOSTAT anomaly |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in res["drought_events"]:
        if "rank_simulated" not in e:
            lines.append(f"| {e['event']} | {e['country']} | {e['crop']} | {e['year']} | – | – | – | – |")
            continue
        lines.append(
            f"| {e['event']} | {e['country']} | {e['crop']} | {e['year']} | {e['rank_simulated']}/{e['n_years']} | "
            f"{e['rank_faostat']}/{e['n_years']} | {e['sim_anomaly_pct']:+.0f} % | {e['obs_anomaly_pct']:+.0f} % |"
        )
    return "\n".join(lines) + "\n"


def write_config(
    res: dict[str, Any],
    fac: dict[str, dict[str, float]],
    groups: list[str],
    rows: list[dict[str, Any]],
    fi: float,
) -> None:
    def n_c(key: str, val: str) -> int:
        return len({r["m49"] for r in rows if r[key] == val})

    cfg: dict[str, Any] = {
        "version": "1.0.0",
        "generated": res["generated"],
        "model": res["selected_model"],
        "method": (
            f"Structure '{res['selected_model']}'. log(FAOSTAT mean yield / simulated mean yield) per country × crop "
            "pair (2000→latest) = log(crop factor) + gap_sensitivity(crop) × log(region factor). Two stages: crop "
            "factors from the reference regions (Northern America, Western and Southern Europe, where crops.yaml "
            "typical yields come from; region factor fixed at 1), then region gap factors and crop sensitivities on "
            "all other pairs by alternating ridge least squares "
            f"(lambda_crop={res['ridge']['lambda_crop']}, lambda_region={res['ridge']['lambda_group']}, "
            f"lambda_sensitivity={res['ridge']['lambda_sensitivity']}). Validated leave-one-country-out "
            "(docs/VALIDATION.md V10)."
        ),
        "sources": [
            "FAOSTAT Crops and livestock products (QCL), national yields, FAO 2025 (CC BY 4.0)",
            "MIRCA2000 v1.1 harvested areas and crop calendars, Portmann, Siebert & Döll 2010, doi:10.1029/2008GB003435; data doi:10.5281/zenodo.7422506",
            "Sacks, Deryng, Foley & Ramankutty 2010, Crop planting dates: an analysis of global patterns, Global Ecol. Biogeogr. 19:607–620 (sowing and harvest dates)",
            "UN M49 standard country/area codes and sub-regions (UN Statistics Division)",
            "NASA POWER daily agroclimatology (weather driving the simulations)",
        ],
        "bounds": [0.1, 2.0],
        "reference_regions": sorted(REFERENCE_REGIONS) if ANCHOR in groups else [],
        **({"irrigated_factor": round(fi, 3)} if IRR in groups else {}),
        "crops": {},
        "regions": {},
        "zones": {},
    }
    for cid, v in sorted(fac.get("fs_crop", {}).items()):
        cfg["crops"][cid] = {"factor": round(math.exp(v), 3), "n_countries": n_c("fs_crop", cid)}
        if "sens" in fac:
            cfg["crops"][cid]["gap_sensitivity"] = round(fac["sens"][cid], 3)
    for rg, v in sorted(fac.get("region", {}).items()):
        cfg["regions"][rg] = {"factor": round(math.exp(v), 3), "n_countries": n_c("region", rg)}
    for z, v in sorted(fac.get("zone", {}).items()):
        cfg["zones"][z] = {"factor": round(math.exp(v), 3), "n_countries": n_c("zone", z)}
    import yaml

    header = (
        "# FieldShift global yield calibration — generated by scripts/yield_benchmark.py evaluate --write-config.\n"
        "# Y = Y_model × crops[c].factor × regions[r].factor ** crops[c].gap_sensitivity (clipped to bounds).\n"
        "# Crops not listed are not calibrated (factor 1).\n"
        "# Do not hand-edit factors: re-run the benchmark. See ADR-022 and docs/VALIDATION.md V10.\n"
    )
    buf = io.StringIO()
    yaml.safe_dump(cfg, buf, sort_keys=False, allow_unicode=True, width=200)
    (CONFIG / "yield_calibration.yaml").write_text(header + buf.getvalue())
    print("wrote", CONFIG / "yield_calibration.yaml")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("download", "prepare"):
        p = sub.add_parser(name)
        p.add_argument("--raw", default="~/yieldbench/raw")
    p = sub.add_parser("simulate")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--soil", action="store_true")
    for p in (sub.choices["simulate"],):
        p.add_argument("--tag", default="")
        p.add_argument(
            "--spinup",
            type=int,
            default=None,
            help="antecedent water-balance days (EXP-12; model default 180)",
        )
    p = sub.add_parser("evaluate")
    p.add_argument("--write-config", action="store_true")
    p.add_argument("--model", default="")
    p.add_argument("--lam-crop", type=float, default=0.5)
    p.add_argument("--lam-group", type=float, default=2.0)
    p.add_argument("--lam-sens", type=float, default=LAM_SENS)
    p.add_argument("--lam-int", type=float, default=LAM_INT)
    p.add_argument("--tag", default="")
    p.add_argument("--spinup", type=int, default=None)
    a = ap.parse_args()
    {"download": cmd_download, "prepare": cmd_prepare, "simulate": cmd_simulate, "evaluate": cmd_evaluate}[
        a.cmd
    ](a)


if __name__ == "__main__":
    main()
