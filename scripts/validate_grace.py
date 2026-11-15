"""V14: does IA's GRACE/GRACE-FO water-storage indicator agree with groundwater wells?

    cd backend && .venv/bin/python ../scripts/validate_grace.py        # writes docs/validation/grace.json

Reference: USGS groundwater-level field measurements (parameter 72019, depth to water below land surface) from the
USGS Water Data OGC API (anonymous), in a 2° × 2° box (≈ one GRACE mascon) around 12 U.S. aquifer regions,
including the Fallon NV and Ames IA demo fields. Wells with ≥ 12 years of data in 2003–2025 are kept; each well
becomes annual median water-level anomalies (m, sign flipped so up = more water); the regional index is the
median across wells per year (≥ 5 wells).

Compared with IA's indicator at the box centre (data/grace.py + science/groundwater.py):
  * Pearson r of annual GRACE water storage (cm) vs. the regional well index (m) — wells measure head, GRACE
    measures mass, so only co-variation and trend sign are comparable, not magnitude (specific yield unknown);
  * trend sign agreement, and whether IA's class (declining / likely / stable / rising) matches the wells'
    trend class (OLS on the annual index with the same p-value thresholds).
Plus a literature check outside the U.S. (published GRACE trends; Rodell et al. 2009, 2018; Voss et al. 2013;
Feng et al. 2013) — sign and order of magnitude only.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import httpx
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldshift.data import grace  # noqa: E402
from fieldshift.data.http import CACHE_DIR  # noqa: E402
from fieldshift.science import groundwater as gw  # noqa: E402

API = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items"
REGIONS = [
    ("fallon_nv", "Fallon / Carson Desert, NV (demo field)", 39.44, -118.83),
    ("ames_ia", "Ames, IA (demo field)", 42.01, -93.72),
    ("tulare_ca", "Tulare Basin, Central Valley, CA", 36.3, -119.5),
    ("southern_high_plains_tx", "Southern High Plains (Ogallala), TX", 33.8, -101.9),
    ("central_high_plains_ks", "Central High Plains (Ogallala), KS", 37.8, -100.8),
    ("platte_ne", "Platte valley / northern High Plains, NE", 40.8, -98.4),
    ("embayment_ar", "Mississippi Embayment (Delta), AR", 34.8, -91.2),
    ("phoenix_az", "Phoenix basins, AZ", 33.4, -112.2),
    ("snake_river_id", "Eastern Snake River Plain, ID", 43.0, -114.5),
    ("columbia_wa", "Columbia Plateau, WA", 46.9, -119.0),
    ("central_fl", "Central Florida (Floridan aquifer)", 28.3, -81.7),
    ("long_island_ny", "Long Island, NY", 40.8, -73.0),
]
LITERATURE = [
    # id, name, lat, lon, published TWS trend (cm/yr), period, reference
    (
        "nw_india",
        "NW India (Punjab, Haryana, Rajasthan)",
        29.5,
        76.0,
        -4.0,
        "2002–2008",
        "Rodell et al. 2009, Nature",
    ),
    (
        "north_china_plain",
        "North China Plain",
        37.5,
        115.5,
        -2.2,
        "2003–2010",
        "Feng et al. 2013, WRR (groundwater)",
    ),
    (
        "tigris_euphrates",
        "Tigris–Euphrates–western Iran",
        34.0,
        47.0,
        -2.7,
        "2003–2009",
        "Voss et al. 2013, WRR",
    ),
    (
        "nw_saudi",
        "Northern Saudi Arabia aquifers",
        29.0,
        38.0,
        -0.9,
        "2002–2016",
        "Rodell et al. 2018, Nature",
    ),
    (
        "niger_sahel",
        "Niger / central Sahel",
        13.5,
        2.1,
        1.0,
        "2002–2016",
        "Rodell et al. 2018, Nature (wetting)",
    ),
    (
        "central_valley",
        "California Central Valley",
        36.5,
        -119.8,
        -2.0,
        "2003–2010",
        "Famiglietti et al. 2011, GRL",
    ),
]
FIRST, LAST = dt.date(2003, 1, 1), dt.date(2025, 12, 31)


def fetch_wells(rid: str, lat: float, lon: float, half: float = 1.0) -> list[dict[str, str]]:
    f = CACHE_DIR / "usgs_gw" / f"{rid}.json.gz"
    if f.exists():
        with gzip.open(f, "rt") as fh:
            return json.load(fh)
    params: dict[str, str | int] = {
        "f": "json",
        "bbox": f"{lon - half},{lat - half},{lon + half},{lat + half}",
        "parameter_code": "72019",
        "datetime": f"{FIRST.isoformat()}T00:00:00Z/{LAST.isoformat()}T23:59:59Z",
        "limit": 10000,
        "skipGeometry": "true",
        "properties": "monitoring_location_id,time,value",
    }
    out: list[dict[str, str]] = []
    url: str | None = API
    c = httpx.Client(timeout=240, headers={"User-Agent": "IA-Intelligent-Agriculture/1.0 validation"})
    pages = 0
    while url and pages < 40:
        r = c.get(url, params=params if pages == 0 else None)
        r.raise_for_status()
        d = r.json()
        out.extend(x["properties"] for x in d.get("features", []))
        url = next((lk["href"] for lk in d.get("links", []) if lk.get("rel") == "next"), None)
        pages += 1
    f.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(f, "wt") as fh:
        json.dump(out, fh)
    return out


def well_index(rows: list[dict[str, str]]) -> tuple[dict[int, float], int]:
    by_well: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        try:
            v = float(r["value"])
        except (TypeError, ValueError):
            continue
        y = int(r["time"][:4])
        if FIRST.year <= y <= LAST.year:
            by_well[r["monitoring_location_id"]][y].append(v * 0.3048)  # ft -> m depth
    anoms: dict[int, list[float]] = defaultdict(list)
    n_wells = 0
    for yrs in by_well.values():
        if len(yrs) < 12:
            continue
        ann = {y: float(np.median(v)) for y, v in yrs.items()}
        mu = float(np.mean(list(ann.values())))
        n_wells += 1
        for y, v in ann.items():
            anoms[y].append(-(v - mu))  # up = more water
    idx = {y: float(np.median(v)) for y, v in anoms.items() if len(v) >= 5}
    return idx, n_wells


def annual_grace(lat: float, lon: float) -> tuple[dict[int, float], gw.StorageTrend | None]:
    r = grace.tws_at(lat, lon)
    assert r is not None
    by: dict[int, list[float]] = defaultdict(list)
    for d, v in zip(r["dates"], r["tws_cm"], strict=True):
        by[d.year].append(float(v))
    return {y: float(np.mean(v)) for y, v in by.items() if len(v) >= 8}, gw.analyse(r["dates"], r["tws_cm"])


def ols_class(years: list[int], vals: list[float]) -> tuple[float, float, str]:
    res = stats.linregress(years, vals)
    return (
        float(res.slope),
        float(res.pvalue),
        ("declining" if res.slope < 0 else "rising") if res.pvalue < 0.2 else "stable",
    )


def main() -> None:
    rows = []
    for rid, name, lat, lon in REGIONS:
        try:
            idx, n_wells = well_index(fetch_wells(rid, lat, lon))
        except httpx.HTTPError as e:
            print(f"{rid}: USGS fetch failed: {e}")
            continue
        ga, tr = annual_grace(lat, lon)
        common = sorted(set(idx) & set(ga))
        if len(common) < 8 or tr is None:
            print(f"{rid}: too few common years ({len(common)}), wells={n_wells}")
            rows.append(
                {"region": rid, "name": name, "wells": n_wells, "years": len(common), "usable": False}
            )
            continue
        wv = [idx[y] for y in common]
        gv = [ga[y] for y in common]
        r = float(np.corrcoef(wv, gv)[0, 1])
        w_slope, w_p, w_cls = ols_class(common, wv)
        g_slope, g_p, _ = ols_class(common, gv)
        fs_dir = tr.status.replace("likely_", "")
        row = {
            "region": rid,
            "name": name,
            "lat": lat,
            "lon": lon,
            "usable": True,
            "wells": n_wells,
            "years": len(common),
            "r_annual": round(r, 2),
            "well_trend_m_per_yr": round(w_slope, 3),
            "well_trend_p": round(w_p, 4),
            "well_class": w_cls,
            "grace_trend_cm_per_yr_common_years": round(g_slope, 2),
            "fieldshift_status": tr.status,
            "fieldshift_slope_cm_yr": tr.slope_cm_yr,
            "fieldshift_p": tr.p_value,
            "sign_agrees": bool(np.sign(w_slope) == np.sign(g_slope)),
            "class_agrees": fs_dir == w_cls,
        }
        rows.append(row)
        print(
            f"{rid:<24} wells={n_wells:<4} yrs={len(common):<3} r={r:+.2f}  wells {w_slope:+.3f} m/yr ({w_cls}, p={w_p:.3f})  "
            f"GRACE {tr.slope_cm_yr:+.2f} cm/yr ({tr.status}, p={tr.p_value:.3f})"
        )
    lit = []
    for lid, name, lat, lon, pub, period, ref in LITERATURE:
        r = grace.tws_at(lat, lon)
        assert r is not None
        y0, y1 = (int(x) for x in period.split("–"))
        sel = [k for k, d in enumerate(r["dates"]) if y0 <= d.year <= y1]
        tr_p = gw.analyse([r["dates"][k] for k in sel], r["tws_cm"][sel])
        tr_all = gw.analyse(r["dates"], r["tws_cm"])
        assert tr_p is not None and tr_all is not None
        lit.append(
            {
                "id": lid,
                "name": name,
                "published_cm_yr": pub,
                "period": period,
                "reference": ref,
                "fieldshift_same_period_cm_yr": tr_p.slope_cm_yr,
                "fieldshift_full_record_cm_yr": tr_all.slope_cm_yr,
                "fieldshift_status": tr_all.status,
                "sign_agrees": bool(np.sign(pub) == np.sign(tr_p.slope_cm_yr)),
            }
        )
        print(
            f"{lid:<20} published {pub:+.1f} ({period})  IA same period {tr_p.slope_cm_yr:+.2f}, full record {tr_all.slope_cm_yr:+.2f} ({tr_all.status})"
        )
    usable = [x for x in rows if x.get("usable")]
    summary = {
        "regions_usable": len(usable),
        "median_r_annual": round(float(np.median([x["r_annual"] for x in usable])), 2) if usable else None,
        "r_positive": f"{sum(x['r_annual'] > 0 for x in usable)}/{len(usable)}",
        "trend_sign_agrees": f"{sum(x['sign_agrees'] for x in usable)}/{len(usable)}",
        "class_agrees": f"{sum(x['class_agrees'] for x in usable)}/{len(usable)}",
        "literature_sign_agrees": f"{sum(x['sign_agrees'] for x in lit)}/{len(lit)}",
    }
    out = {
        "generated": dt.date.today().isoformat(),
        "grace_asset": grace.tws_at(0.0, 20.0)["meta"] if grace.tws_at(0.0, 20.0) else {},
        "reference": "USGS groundwater-level field measurements (72019) via api.waterdata.usgs.gov; published GRACE studies",
        "regions": rows,
        "literature": lit,
        "summary": summary,
    }
    p = ROOT / "docs" / "validation" / "grace.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
