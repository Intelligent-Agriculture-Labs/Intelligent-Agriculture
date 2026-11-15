"""Build IA's offline country tables from official open data (ADR-027, docs/DATA.md "Country data").

Runs on the data box (VPS); the outputs are small and committed:

    backend/fieldshift/config/country_grid_5mn.npz   offline lat/lon → ISO 3166 country (5 arc-min, Natural Earth)
    backend/fieldshift/config/country_data.json      per country: currency + exchange rate, price level, diesel,
                                                       FAOSTAT producer prices and yields per IA crop,
                                                       Sacks et al. (2010) sowing day per crop; sub-region and
                                                       world medians
    backend/fieldshift/config/crop_calendar_30mn.npz  Sacks et al. (2010) 0.5° sowing day of year per calendar

    # tool venv (babel for ISO 4217 currencies, rasterio to rasterise the borders)
    uv venv ~/econbuild/.venv && uv pip install -p ~/econbuild/.venv numpy pyyaml babel rasterio openpyxl
    ~/econbuild/.venv/bin/python scripts/build_country_data.py download --raw ~/econbuild/raw
    ~/econbuild/.venv/bin/python scripts/build_country_data.py build --raw ~/econbuild/raw \
        --faostat-qcl ~/yieldbench/raw --sacks ~/yieldbench/raw
    # country yield factors (no downloads; uses country_data.json and the V10 benchmark results)
    python scripts/build_country_data.py yieldcal

Sources (all free, no key):
  * Natural Earth 1:10m Admin 0 – Countries v5 (public domain)
  * FAOSTAT Producer Prices (PP) and Crops and livestock products (QCL), FAO, CC BY 4.0
  * World Bank World Development Indicators (CC BY 4.0): PA.NUS.FCRF official exchange rate (LCU per USD,
    period average), PA.NUS.PPP PPP conversion factor (price level = PPP / exchange rate); WDI Database
    Archives EP.PMP.DESL.CD pump price for diesel fuel (USD per litre)
  * World Bank Commodity Price Data (Pink Sheet), annual: urea, Brent crude (CC BY 4.0)
  * Unicode CLDR via Babel: territory → ISO 4217 currency and symbol
  * UN M49 country table (lukes/ISO-3166-Countries-with-Regional-Codes, CC BY-SA 4.0)
  * Sacks, Deryng, Foley & Ramankutty 2010, crop calendar dataset (0.5°)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import statistics
import sys
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "backend" / "fieldshift" / "config"

NE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_admin_0_countries.geojson"
PP_URL = "https://bulks-faostat.fao.org/production/Prices_E_All_Data_(Normalized).zip"
M49_URL = "https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.csv"
WB_URL = "https://api.worldbank.org/v2/country/all/indicator/{}?format=json&per_page=4000&date=2015:2025"
WB_INDICATORS = ("PA.NUS.FCRF", "PA.NUS.PPP")
WB_CSV_URL = "https://api.worldbank.org/v2/en/indicator/{}?downloadformat=csv"
# EP.PMP.DESL.CD (pump price for diesel) was archived from the live WDI API: read it from the WDI Database
# Archives (source 57), version given by --diesel-version
WB_ARCHIVE_URL = (
    "https://api.worldbank.org/v2/sources/57/country/{}/series/EP.PMP.DESL.CD/version/{}/time/{}?format=json"
)
PINK_URL = "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Annual.xlsx"

RES_DEG = 1.0 / 12.0  # 5 arc-minutes

# IA crop -> Sacks et al. 2010 calendars, in order of preference
SACKS_MAP: dict[str, list[str]] = {
    "maize": ["Maize"],
    "maize_silage": ["Maize"],
    "sweet_corn": ["Maize"],
    "winter_wheat": ["Wheat.Winter"],
    "spelt": ["Wheat.Winter"],
    "spring_wheat": ["Wheat"],
    "durum_wheat": ["Wheat.Winter", "Wheat"],
    "barley": ["Barley"],
    "winter_barley": ["Barley.Winter"],
    "oats": ["Oats"],
    "winter_rye": ["Rye.Winter"],
    "triticale_forage": ["Wheat.Winter"],
    "rice": ["Rice"],
    "sorghum": ["Sorghum"],
    "sorghum_sudan": ["Sorghum"],
    "pearl_millet": ["Millet"],
    "soybean": ["Soybeans"],
    "dry_bean": ["Pulses"],
    "cowpea": ["Pulses"],
    "mung_bean": ["Pulses"],
    "pigeon_pea": ["Pulses"],
    "field_pea": ["Pulses"],
    "lentil": ["Pulses"],
    "chickpea": ["Pulses"],
    "faba_bean": ["Pulses"],
    "groundnut": ["Groundnuts"],
    "sunflower": ["Sunflower"],
    "winter_rapeseed": ["Rapeseed.Winter"],
    "cotton": ["Cotton"],
    "potato": ["Potatoes"],
    "sweet_potato": ["Sweet.Potatoes"],
    "cassava": ["Cassava"],
    "sugar_beet": ["Sugarbeets"],
}
SACKS_NAMES = sorted({n for v in SACKS_MAP.values() for n in v})


def _get(url: str, dest: Path, is_json: bool = False, tries: int = 8) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print("have", dest.name)
        return
    print("get", url)
    req = urllib.request.Request(url, headers={"User-Agent": "fieldshift-data-build/1.0"})
    last: Exception | None = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            if is_json:
                j = json.loads(data)
                if isinstance(j, list) and j and "message" in j[0]:
                    raise RuntimeError(str(j[0]["message"])[:200])
            dest.write_bytes(data)
            print("  ->", dest, len(data) // 1024, "KB")
            return
        except Exception as e:  # noqa: BLE001 — the World Bank API is flaky (502/503): retry
            last = e
            print("  retry", k + 1, e)
            time.sleep(5 + 5 * k)
    raise RuntimeError(f"{url}: {last}")


def download(raw: Path, diesel_version: str) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    _get(NE_URL, raw / "ne_10m_admin_0_countries.geojson")
    _get(PP_URL, raw / "faostat_pp.zip")
    _get(M49_URL, raw / "m49.csv")
    for ind in WB_INDICATORS:
        dest = raw / f"wb_{ind}.json"
        try:
            _get(WB_URL.format(ind), dest, is_json=True, tries=3)
        except RuntimeError:
            # the JSON API often answers 502 for all countries: use the bulk CSV of the same indicator
            _get(WB_CSV_URL.format(ind), raw / f"wb_{ind}.zip")
            dest.write_text(json.dumps(_wb_csv_rows(raw / f"wb_{ind}.zip")))
    # the archive API answers 502 for "all" and for multi-country batches: one country and year per request
    # (≈ 10 s each), 8 in parallel, latest of 2016/2014/2012 with a value
    dest = raw / "wb_diesel_archive.json"
    if not dest.exists():
        from concurrent.futures import ThreadPoolExecutor

        isos = sorted(
            {
                r["countryiso3code"]
                for r in json.loads((raw / "wb_PA.NUS.FCRF.json").read_text())[1]
                if r.get("countryiso3code")
            }
        )
        with open(raw / "m49.csv", encoding="utf-8") as fh:
            m49_isos = {r["alpha-3"] for r in csv.DictReader(fh)}
        isos = [i for i in isos if i in m49_isos]

        def one(iso: str) -> list[Any]:
            for yr in ("YR2016", "YR2014", "YR2012"):
                for k in range(4):
                    try:
                        with urllib.request.urlopen(
                            WB_ARCHIVE_URL.format(iso, diesel_version, yr), timeout=60
                        ) as r:
                            rows = [
                                x
                                for x in json.loads(r.read())["source"]["data"]
                                if x.get("value") is not None
                            ]
                        if rows:
                            return rows
                        break
                    except Exception:  # noqa: BLE001 — flaky API: retry, then try the next year
                        time.sleep(3 + 3 * k)
            return []

        with ThreadPoolExecutor(8) as ex:
            data = [x for rows in ex.map(one, isos) for x in rows]
        dest.write_text(json.dumps({"source": {"data": data}}))
    try:
        _get(PINK_URL, raw / "pink_annual.xlsx")
    except Exception as e:  # noqa: BLE001 — optional: economics.yaml keeps the documented values
        print("pink sheet not downloaded:", e)


# ---------------------------------------------------------------------------------------------------- helpers


def _wb_csv_rows(zp: Path) -> list[Any]:
    """World Bank bulk CSV (wide, one column per year) → the JSON API's [meta, rows] shape."""
    z = zipfile.ZipFile(zp)
    name = next(n for n in z.namelist() if n.startswith("API_"))
    lines = z.read(name).decode("utf-8-sig").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith('"Country Name"'))
    rows = []
    for r in csv.DictReader(lines[start:]):
        for k, v in r.items():
            if k and k.isdigit() and v:
                rows.append({"countryiso3code": r["Country Code"], "date": k, "value": float(v)})
    return [{"source": "bulk csv"}, rows]


def load_m49(raw: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with open(raw / "m49.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row["alpha-3"]:
                continue
            sub = row["intermediate-region"] if row["sub-region"] == "Latin America and the Caribbean" else ""
            out[row["alpha-3"]] = {
                "name": row["name"],
                "iso2": row["alpha-2"],
                "m49": int(row["country-code"]),
                "region": row["region"],
                "sub_region": row["sub-region"] or row["region"],
                "intermediate_region": sub or None,
            }
    return out


def wb_latest(raw: Path, ind: str, min_year: int = 2005) -> dict[str, tuple[float, int]]:
    rows = json.loads((raw / f"wb_{ind}.json").read_text())[1] or []
    out: dict[str, tuple[float, int]] = {}
    for r in rows:
        iso3 = r.get("countryiso3code")
        if not iso3 or r.get("value") is None:
            continue
        y = int(r["date"])
        if y < min_year:
            continue
        if iso3 not in out or y > out[iso3][1]:
            out[iso3] = (float(r["value"]), y)
    return out


def wb_archive_latest(raw: Path) -> dict[str, tuple[float, int]]:
    """Latest non-null value per country from a WDI Database Archives (source 57) series download."""
    p = raw / "wb_diesel_archive.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    out: dict[str, tuple[float, int]] = {}
    for x in d["source"]["data"]:
        if x.get("value") is None:
            continue
        var = {v["concept"]: v["id"] for v in x["variable"]}
        iso3, y = var.get("Country"), int(str(var.get("Time", "YR0"))[2:])
        if iso3 and (iso3 not in out or y > out[iso3][1]):
            out[iso3] = (float(x["value"]), y)
    return out


def pink_sheet(raw: Path) -> dict[str, dict[int, float]]:
    """Annual nominal USD prices for urea and Brent from the Pink Sheet workbook (empty if unavailable)."""
    p = raw / "pink_annual.xlsx"
    if not p.exists():
        return {}
    import openpyxl

    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    ws = wb["Annual Prices (Nominal)"]
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows) if r and any(isinstance(c, str) and "Urea" in c for c in r))
    hdr = rows[hdr_i]
    want = {"urea": None, "brent": None}
    for j, c in enumerate(hdr):
        if isinstance(c, str):
            if c.strip().lower().startswith("urea"):
                want["urea"] = j
            if "brent" in c.lower():
                want["brent"] = j
    out: dict[str, dict[int, float]] = {k: {} for k in want}
    for r in rows[hdr_i + 1 :]:
        if not r or r[0] is None:
            continue
        try:
            y = int(str(r[0])[:4])
        except ValueError:
            continue
        for k, j in want.items():
            if j is not None and isinstance(r[j], (int, float)):
                out[k][y] = float(r[j])
    return out


def _find(base: Path, name: str) -> Path:
    hits = list(base.rglob(name))
    if not hits:
        raise FileNotFoundError(f"{name} under {base}")
    return hits[0]


def _csv_from_zip(zp: Path, suffix: str) -> io.TextIOWrapper:
    z = zipfile.ZipFile(zp)
    name = next(n for n in z.namelist() if n.endswith(suffix))
    return io.TextIOWrapper(z.open(name), encoding="latin-1")


# ------------------------------------------------------------------------------------------------- country grid


def build_grid(raw: Path, known: set[str]) -> tuple[np.ndarray, list[str], dict[str, str]]:
    from rasterio import features
    from rasterio.transform import from_origin

    gj = json.loads((raw / "ne_10m_admin_0_countries.geojson").read_text())
    feats = []
    names: dict[str, str] = {}
    for ft in gj["features"]:
        p = ft["properties"]
        code = next(
            (
                c
                for c in (p.get("ISO_A3"), p.get("ISO_A3_EH"), p.get("ADM0_A3"))
                if c and c != "-99" and c in known
            ),
            None,
        )
        if code is None:
            code = p.get("ADM0_A3")  # e.g. Kosovo, Somaliland, N. Cyprus: no UN M49 row
        if not code or code == "-99":
            continue
        feats.append((code, ft["geometry"], float(p.get("POP_EST") or 0)))
        names.setdefault(code, p.get("NAME_EN") or p.get("NAME") or code)
    codes = sorted({c for c, _, _ in feats})
    if len(codes) > 254:
        raise SystemExit("too many codes for uint8")
    idx = {c: i + 1 for i, c in enumerate(codes)}
    w, h = int(round(360 / RES_DEG)), int(round(180 / RES_DEG))
    tr = from_origin(-180.0, 90.0, RES_DEG, RES_DEG)
    # pass 1: every touched cell (small islands survive); pass 2: cell-centre rule overrides along borders
    grid = features.rasterize(
        ((g, idx[c]) for c, g, _ in feats),
        out_shape=(h, w),
        transform=tr,
        fill=0,
        all_touched=True,
        dtype="uint8",
    )
    inner = features.rasterize(
        ((g, idx[c]) for c, g, _ in feats), out_shape=(h, w), transform=tr, fill=0, dtype="uint8"
    )
    grid = np.where(inner > 0, inner, grid).astype(np.uint8)
    print("country grid:", grid.shape, "land cells", int((grid > 0).sum()), "countries", len(codes))
    return grid, codes, names


# --------------------------------------------------------------------------------------------- FAOSTAT tables


def faostat_prices(
    raw: Path,
    items: set[int],
    min_year: int,
    n_years: int,
    fx_by_m49: dict[int, dict[int, float]],
) -> dict[tuple[int, int], dict[str, Any]]:
    """{(m49, item): {'usd_t', 'years', 'method'}} from FAOSTAT PP.

    Mean of the latest `n_years` USD prices (≥ min_year). Where a country stopped reporting prices (e.g. India
    after 2008) but still reports the FAOSTAT producer price index of the item, the last local-currency price is
    carried forward with that index and converted at the World Bank exchange rate of the index year."""
    usd: dict[tuple[int, int], dict[int, float]] = defaultdict(dict)
    lcu: dict[tuple[int, int], dict[int, float]] = defaultdict(dict)
    ppi: dict[tuple[int, int], dict[int, float]] = defaultdict(dict)
    f = _csv_from_zip(raw / "faostat_pp.zip", "Prices_E_All_Data_(Normalized).csv")
    for row in csv.DictReader(f):
        if row.get("Months") and row["Months"] != "Annual value":
            continue
        el = row["Element"]
        target = (
            usd
            if el == "Producer Price (USD/tonne)"
            else lcu
            if el == "Producer Price (LCU/tonne)"
            else ppi
            if el.startswith("Producer Price Index")
            else None
        )
        if target is None or not row["Value"]:
            continue
        item = int(row["Item Code"])
        if item not in items:
            continue
        m49 = int(row["Area Code (M49)"].strip("'"))
        target[(m49, item)][int(row["Year"])] = float(row["Value"])
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for k in set(usd) | set(ppi):
        s = {y: v for y, v in usd.get(k, {}).items() if y >= min_year and v > 0}
        if s:
            ys = sorted(s)[-n_years:]
            out[k] = {"usd_t": statistics.mean(s[y] for y in ys), "years": ys, "method": "usd"}
            continue
        lc, pi, fx = lcu.get(k, {}), ppi.get(k, {}), fx_by_m49.get(k[0], {})
        base_years = [y for y in sorted(lc) if y in pi and lc[y] > 0 and pi[y] > 0]
        idx_years = [y for y in sorted(pi) if y >= min_year and y in fx and pi[y] > 0]
        if not base_years or not idx_years:
            continue
        y0 = base_years[-1]
        ys = idx_years[-n_years:]
        vals = [lc[y0] * pi[y] / pi[y0] / fx[y] for y in ys]
        out[k] = {
            "usd_t": statistics.mean(vals),
            "years": ys,
            "method": f"lcu{y0}_ppi",
            "base_year": y0,
        }
    return out


def faostat_yields(
    qcl_raw: Path, items: set[int], first_year: int = 2019
) -> dict[tuple[int, int], dict[str, Any]]:
    """{(m49, item): {'t_ha': mean yield, 'years': [first, last]}}; cotton lint = lint production / seed-cotton area."""
    path = _find(qcl_raw, "Production_Crops_Livestock_E_All_Data_(Normalized).csv")
    yld: dict[tuple[int, int], dict[int, float]] = defaultdict(dict)
    lint_prod: dict[tuple[int, int], float] = {}
    cot_area: dict[tuple[int, int], float] = {}
    with open(path, encoding="latin-1") as f:
        for row in csv.DictReader(f):
            el = row["Element"]
            if el not in ("Yield", "Production", "Area harvested") or not row["Value"]:
                continue
            item = int(row["Item Code"])
            y = int(row["Year"])
            if y < first_year:
                continue
            m49 = int(row["Area Code (M49)"].strip("'"))
            v = float(row["Value"])
            if item == 767 and el == "Production":
                lint_prod[(m49, y)] = v
            elif item == 328 and el == "Area harvested":
                cot_area[(m49, y)] = v
            elif el == "Yield" and item in items:
                unit = row["Unit"]
                v = v / 1000.0 if unit == "kg/ha" else (v / 10000.0 if unit == "hg/ha" else v)
                if v > 0:
                    yld[(m49, item)][y] = v
    for (m49, y), prod in lint_prod.items():
        a = cot_area.get((m49, y))
        if a and a > 0 and prod > 0:
            yld[(m49, 767)][y] = prod / a
    return {k: {"t_ha": statistics.mean(s.values()), "years": [min(s), max(s)]} for k, s in yld.items() if s}


# ----------------------------------------------------------------------------------------------------- Sacks


def read_sacks(sacks_raw: Path, name: str, var: str = "plant") -> np.ndarray | None:
    d = f"{name}.crop.calendar"
    f = sacks_raw / "sacks" / d / d / f"{var}.asc"
    if not f.exists():
        hits = list((sacks_raw / "sacks").rglob(f"{d}/{var}.asc"))
        if not hits:
            return None
        f = hits[0]
    txt = f.read_text().split("\n", 6)[6]
    a = np.array(txt.split(), float).reshape(360, 720)
    a[a > 1e19] = np.nan
    a[(a < 1) | (a > 366)] = np.nan
    return a


def circ_median_doy(v: np.ndarray) -> int:
    """Median day of year robust to the Dec/Jan wrap: rotate so the sparsest month is the cut."""
    hist = np.histogram(v, bins=12, range=(0, 366))[0]
    cut = int(np.argmin(hist)) * 30.5
    w = (v - cut) % 366
    return int(round((float(np.median(w)) + cut) % 366)) or 1


# ------------------------------------------------------------------------------------------------------ build


def build(raw: Path, qcl_raw: Path, sacks_raw: Path) -> None:
    cfg = yaml.safe_load((CONFIG / "economics.yaml").read_text())
    m49 = load_m49(raw)
    grid, codes, ne_names = build_grid(raw, set(m49))
    np.savez_compressed(CONFIG / "country_grid_5mn.npz", country=grid, codes=np.array(codes))

    from babel.numbers import get_currency_symbol, get_territory_currencies

    fx = wb_latest(raw, "PA.NUS.FCRF")
    # price level ratio = PPP conversion factor (LCU per international $) / market exchange rate (LCU per US$),
    # same year (the WDI series PA.NUS.PPPC.RF itself was archived)
    ppp_rows = json.loads((raw / "wb_PA.NUS.PPP.json").read_text())[1] or []
    fx_rows = json.loads((raw / "wb_PA.NUS.FCRF.json").read_text())[1] or []
    fxy = {(r["countryiso3code"], int(r["date"])): float(r["value"]) for r in fx_rows if r.get("value")}
    plr: dict[str, tuple[float, int]] = {}
    for r in ppp_rows:
        k = (r.get("countryiso3code"), int(r["date"]))
        if r.get("value") is None or k not in fxy or not k[0]:
            continue
        if k[0] not in plr or k[1] > plr[k[0]][1]:
            plr[k[0]] = (float(r["value"]) / fxy[k], k[1])
    diesel = wb_archive_latest(raw)
    pink = pink_sheet(raw)
    brent = {int(k): float(v) for k, v in cfg["diesel"]["brent_usd_bbl"].items()}
    brent.update(pink.get("brent") or {})
    target = int(cfg["diesel"]["target_year"])
    if target not in brent:
        target = max(brent)

    items_cfg = cfg["faostat_items"]
    price_items = {int(v["item"]) for v in items_cfg.values()}
    yield_items = {int(v.get("yield_item", v["item"])) for v in items_cfg.values()}
    fx_rows = json.loads((raw / "wb_PA.NUS.FCRF.json").read_text())[1] or []
    iso_to_m49 = {k: v["m49"] for k, v in m49.items()}
    fx_by_m49: dict[int, dict[int, float]] = defaultdict(dict)
    for r in fx_rows:
        if r.get("value") and r.get("countryiso3code") in iso_to_m49:
            fx_by_m49[iso_to_m49[r["countryiso3code"]]][int(r["date"])] = float(r["value"])
    pp = faostat_prices(
        raw, price_items, int(cfg["prices"]["min_year"]), int(cfg["prices"]["n_years"]), fx_by_m49
    )
    qy = faostat_yields(qcl_raw, yield_items)

    sacks = {n: read_sacks(sacks_raw, n) for n in SACKS_NAMES}
    harvest = {n: read_sacks(sacks_raw, n, "harvest") for n in SACKS_NAMES}
    sacks = {n: a for n, a in sacks.items() if a is not None}
    print("sacks calendars:", sorted(sacks))
    # 0.5° cell → country: majority of the 6×6 five-minute cells
    g6 = grid.reshape(360, 6, 720, 6).transpose(0, 2, 1, 3).reshape(360, 720, 36)
    cell_country = np.zeros((360, 720), np.uint8)
    for r in range(360):
        for c in range(720):
            v = g6[r, c][g6[r, c] > 0]
            if v.size:
                cell_country[r, c] = np.bincount(v).argmax()
    cal_grid = {n: np.nan_to_num(a, nan=0).round().astype(np.uint16) for n, a in sacks.items()}
    # harvest day of year under "<name>_h" (season length = harvest − sowing, used for the thermal-time target)
    for n, a in harvest.items():
        if a is not None and n in sacks:
            cal_grid[n + "_h"] = np.where(np.isfinite(sacks[n]), np.nan_to_num(a, nan=0), 0).round().astype(np.uint16)
    np.savez_compressed(
        CONFIG / "crop_calendar_30mn.npz", **{n.replace(".", "_"): a for n, a in cal_grid.items()}
    )

    countries: dict[str, Any] = {}
    for code in codes:
        meta = m49.get(code)
        name = meta["name"] if meta else ne_names.get(code, code)
        iso2 = meta["iso2"] if meta else None
        cur = None
        if iso2:
            try:
                cs = get_territory_currencies(iso2, start_date=dt.date(2025, 1, 1), tender=True)
                cur = cs[0] if cs else None
            except Exception:  # noqa: BLE001
                cur = None
        rate = fx.get(code)
        entry: dict[str, Any] = {
            "name": name,
            "iso2": iso2,
            "m49": meta["m49"] if meta else None,
            "region": meta["region"] if meta else None,
            "sub_region": (meta["intermediate_region"] or meta["sub_region"]) if meta else None,
            "m49_sub_region": meta["sub_region"] if meta else None,
        }
        if cur and cur == "USD":
            entry["currency"] = {
                "code": "USD",
                "symbol": "$",
                "per_usd": 1.0,
                "year": None,
                "source": "currency is the US dollar",
            }
        elif cur and rate:
            entry["currency"] = {
                "code": cur,
                "symbol": get_currency_symbol(cur, locale="en"),
                "per_usd": round(rate[0], 6),
                "year": rate[1],
                "source": "World Bank WDI PA.NUS.FCRF (official exchange rate, period average)",
            }
        elif cur:
            entry["currency"] = {
                "code": cur,
                "symbol": get_currency_symbol(cur, locale="en"),
                "per_usd": None,
                "year": None,
                "source": None,
            }
        if code in plr:
            entry["price_level"] = {"value": round(plr[code][0], 4), "year": plr[code][1]}
        if code in diesel:
            v, y = diesel[code]
            adj = (brent.get(target, 0) - brent.get(y, brent.get(target, 0))) / 159.0
            entry["diesel"] = {
                "usd_l": round(max(0.05, v + adj), 3),
                "reported_usd_l": v,
                "reported_year": y,
                "year": target,
            }
        prices: dict[str, Any] = {}
        yields: dict[str, Any] = {}
        if meta:
            for cid, ic in items_cfg.items():
                p = pp.get((meta["m49"], int(ic["item"])))
                if p:
                    prices[cid] = {
                        "usd_t": round(p["usd_t"] * float(ic.get("price_factor", 1.0)), 1),
                        "years": [p["years"][0], p["years"][-1]],
                    }
                    if p.get("base_year"):
                        prices[cid]["indexed_from"] = p["base_year"]
                yv = qy.get((meta["m49"], int(ic.get("yield_item", ic["item"]))))
                if yv:
                    yields[cid] = {"t_ha": round(yv["t_ha"], 3), "years": yv["years"]}
        entry["prices"] = prices
        entry["yields"] = yields
        # Sacks sowing day: country median of 0.5° cells
        k = codes.index(code) + 1
        mask = cell_country == k
        sow = {}
        if mask.any():
            for cid, names in SACKS_MAP.items():
                for n in names:
                    a = sacks.get(n)
                    if a is None:
                        continue
                    v = a[mask]
                    ok = np.isfinite(v)
                    v = v[ok]
                    if v.size >= 1:
                        sow[cid] = {"doy": circ_median_doy(v), "calendar": n, "cells": int(v.size)}
                        h = harvest.get(n)
                        if h is not None:
                            hv = h[mask][ok]
                            season = (hv - v) % 365
                            season = season[np.isfinite(season) & (season > 30)]
                            if season.size:
                                sow[cid]["season_days"] = int(round(float(np.median(season))))
                        break
        entry["sowing"] = sow
        countries[code] = entry

    # sub-region / world medians and per-country farm-price index vs. the crop table references
    from_crops = {}
    for fname in ("crops.yaml", "crops_extra.yaml"):
        from_crops.update((yaml.safe_load((CONFIG / fname).read_text()) or {}).get("crops") or {})

    def med(vals: list[float]) -> float | None:
        return round(statistics.median(vals), 1) if vals else None

    subs: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    world: dict[str, list[float]] = defaultdict(list)
    for e in countries.values():
        for cid, p in e["prices"].items():
            world[cid].append(p["usd_t"])
            if e.get("sub_region"):
                subs[e["sub_region"]][cid].append(p["usd_t"])
    world_med = {cid: med(v) for cid, v in world.items()}
    for e in countries.values():
        ratios = [
            p["usd_t"] / world_med[cid]
            for cid, p in e["prices"].items()
            if world_med.get(cid) and cid in from_crops and not items_cfg[cid].get("proxy")
        ]
        if len(ratios) >= 3:
            e["farm_price_index"] = {"value": round(statistics.median(ratios), 3), "n_crops": len(ratios)}
        yr = [
            y["t_ha"] / float(from_crops[cid]["typical_yield_t_ha"])
            for cid, y in e["yields"].items()
            if cid in from_crops and float(from_crops[cid].get("typical_yield_t_ha") or 0) > 0
        ]
        if len(yr) >= 2:
            e["yield_index"] = {"value": round(statistics.median(yr), 3), "n_crops": len(yr)}
    plr_vals = [e["price_level"]["value"] for e in countries.values() if "price_level" in e]
    # the crop table's reference prices are U.S. prices → farm-price index of the USA, to scale forages
    us_idx = (countries.get("USA", {}).get("farm_price_index") or {}).get("value", 1.0)

    urea = pink.get("urea") or {}
    nitro = dict(cfg["nitrogen"])
    if urea:
        y = max(urea)
        nitro["urea_usd_t"], nitro["urea_year"] = round(urea[y], 1), y

    out = {
        "version": "1.0.0",
        "generated": dt.date.today().isoformat(),
        "sources": {
            "borders": "Natural Earth 1:10m Admin 0 – Countries v5.1.2 (public domain), rasterised at 5 arc-min",
            "prices": "FAOSTAT Producer Prices (PP), element 5532 Producer Price (USD/tonne), annual; FAO, CC BY 4.0",
            "yields": "FAOSTAT Crops and livestock products (QCL), national yields 2019→latest; FAO, CC BY 4.0",
            "exchange_rates": "World Bank WDI PA.NUS.FCRF, official exchange rate (LCU per US$, period average); CC BY 4.0",
            "price_level": "World Bank WDI PA.NUS.PPP (PPP conversion factor, GDP) ÷ PA.NUS.FCRF, same year = price level "
            "ratio to the US; CC BY 4.0",
            "diesel": "World Bank WDI Database Archives (source 57) EP.PMP.DESL.CD, pump price for diesel fuel "
            "(US$ per litre; GIZ International Fuel Prices), "
            "brought to the target year by the change in Brent crude cost per litre (World Bank Pink Sheet); CC BY 4.0",
            "urea": "World Bank Commodity Price Data (Pink Sheet), urea annual average; CC BY 4.0",
            "currencies": "Unicode CLDR territory currencies via Babel (ISO 4217)",
            "regions": "UN M49 (lukes/ISO-3166-Countries-with-Regional-Codes, CC BY-SA 4.0)",
            "sowing": "Sacks, Deryng, Foley & Ramankutty 2010, Global Ecol. Biogeogr. 19:607–620, 0.5° crop calendars",
        },
        "nitrogen": nitro,
        "us_farm_price_index": us_idx,
        "world_price_level_median": round(statistics.median(plr_vals), 4) if plr_vals else None,
        "world_prices": world_med,
        "region_prices": {s: {cid: med(v) for cid, v in d.items()} for s, d in sorted(subs.items())},
        "countries": countries,
    }
    (CONFIG / "country_data.json").write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )
    n_p = sum(1 for e in countries.values() if e["prices"])
    n_fx = sum(1 for e in countries.values() if (e.get("currency") or {}).get("per_usd"))
    print(
        f"countries {len(countries)}; with FAOSTAT prices {n_p}; with exchange rate {n_fx}; "
        f"with diesel {sum('diesel' in e for e in countries.values())}; price level {len(plr_vals)}; "
        f"with sowing {sum(bool(e['sowing']) for e in countries.values())}"
    )
    print("pink:", {k: (max(v), v[max(v)]) for k, v in pink.items() if v})
    for c in ("DEU", "KEN", "USA", "ESP", "IND", "BRA"):
        e = countries.get(c, {})
        print(
            c,
            e.get("currency"),
            e.get("price_level"),
            e.get("diesel"),
            e.get("farm_price_index"),
            e.get("yield_index"),
            {k: e["prices"].get(k) for k in ("winter_wheat", "maize")},
            {k: e["sowing"].get(k) for k in ("winter_wheat", "maize")},
        )


# ------------------------------------------------------------------------------------- country yield factors

# UN M49 sub-region → IA macro region of the yield calibration (same table as scripts/yield_benchmark.py)
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
SHRINK = 2.0  # ridge: a country's factor counts as n / (n + 2) of its evidence (n crops or benchmark pairs)


def yield_factors() -> None:
    """Country yield factors on top of the crop × region calibration (config/yield_country_factors.yaml).

    * Benchmarked countries (41, docs/VALIDATION.md V10): the mean residual log(FAOSTAT / calibrated simulation)
      over the country's benchmark pairs, shrunk by n / (n + 2), clipped to [0.5, 2].
    * Every other country with FAOSTAT yields: half the median log ratio of its national yields to the median of
      its macro region's countries (same crop), shrunk by n / (n + 2), clipped to [0.67, 1.5]. Half, because part
      of a national yield difference is climate, which the season model already simulates from NASA POWER.
    """
    import math

    res = json.loads((ROOT / "docs" / "validation" / "yield_benchmark" / "results.json").read_text())
    fac = res["factors"]
    cd = json.loads((CONFIG / "country_data.json").read_text())["countries"]
    cal = yaml.safe_load((CONFIG / "yield_calibration.yaml").read_text())
    calibrated = set(cal["crops"])
    m49_to_iso = {e["m49"]: k for k, e in cd.items() if e.get("m49") is not None}
    out: dict[str, Any] = {}
    resid: dict[str, list[float]] = defaultdict(list)
    for r in res["pairs"]:
        # results.json stores the factors themselves (not logs)
        v = math.log(fac["fs_crop"].get(r["fs_crop"], 1.0)) + fac["sens"].get(r["fs_crop"], 1.0) * math.log(
            fac["region"].get(r["region"], 1.0)
        )
        v = min(max(v, math.log(0.1)), math.log(2.0))
        iso = m49_to_iso.get(int(r["m49"]))
        if iso:
            resid[iso].append(float(r["log_ratio"]) - v)
    for iso, rs in resid.items():
        n = len(rs)
        lf = sum(rs) / (n + SHRINK)
        out[iso] = {
            "factor": round(min(2.0, max(0.5, math.exp(lf))), 3),
            "n": n,
            "method": "benchmark",
        }
    # FAOSTAT national yield vs. macro-region median
    region_of_iso = {k: M49_REGION.get(e.get("m49_sub_region") or "") for k, e in cd.items()}
    by_region_crop: dict[tuple[str, str], list[float]] = defaultdict(list)
    for iso, e in cd.items():
        reg = region_of_iso.get(iso)
        for cid, y in (e.get("yields") or {}).items():
            if reg and cid in calibrated:
                by_region_crop[(reg, cid)].append(float(y["t_ha"]))
    for iso, e in cd.items():
        if iso in out:
            continue
        reg = region_of_iso.get(iso)
        logs = []
        for cid, y in (e.get("yields") or {}).items():
            base = by_region_crop.get((reg, cid)) if reg else None
            if base and len(base) >= 3 and cid in calibrated and float(y["t_ha"]) > 0:
                logs.append(math.log(float(y["t_ha"]) / statistics.median(base)))
        if not logs:
            continue
        n = len(logs)
        lf = 0.5 * statistics.median(logs) * n / (n + SHRINK)
        out[iso] = {
            "factor": round(min(1.5, max(0.67, math.exp(lf))), 3),
            "n": n,
            "method": "faostat_relative",
        }
    doc = {
        "version": "1.0.0",
        "generated": dt.date.today().isoformat(),
        "method": yield_factors.__doc__.strip().replace("\n    ", "\n"),
        "sources": [
            "FAOSTAT QCL national yields 2019→latest (FAO, CC BY 4.0)",
            "IA global yield benchmark, docs/validation/yield_benchmark/results.json (V10, ADR-022)",
        ],
        "countries": dict(sorted(out.items())),
    }
    head = "# Generated by scripts/build_country_data.py yieldcal — do not hand-edit (ADR-027).\n"
    (CONFIG / "yield_country_factors.yaml").write_text(
        head + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)
    )
    print("country factors:", len(out), "benchmark", sum(v["method"] == "benchmark" for v in out.values()))
    for k in ("USA", "DEU", "KEN", "ESP", "IND", "BRA", "ETH", "EGY", "NLD"):
        print(k, out.get(k))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["download", "build", "yieldcal"])
    ap.add_argument("--raw", default=str(Path.home() / "econbuild" / "raw"))
    ap.add_argument("--faostat-qcl", default=str(Path.home() / "yieldbench" / "raw"))
    ap.add_argument("--sacks", default=str(Path.home() / "yieldbench" / "raw"))
    ap.add_argument(
        "--diesel-version", default="202407"
    )  # last archive version that still carries the series
    a = ap.parse_args()
    raw = Path(a.raw).expanduser()
    if a.step == "download":
        download(raw, a.diesel_version)
    elif a.step == "yieldcal":
        yield_factors()
    else:
        build(raw, Path(a.faostat_qcl).expanduser(), Path(a.sacks).expanduser())


if __name__ == "__main__":
    sys.exit(main())
