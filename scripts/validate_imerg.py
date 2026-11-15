"""V-IMERG: does NASA GPM IMERG rain (or a POWER/IMERG blend) beat NASA POWER rain against rain gauges?

    cd backend && .venv/bin/python ../scripts/validate_imerg.py          # writes docs/validation/imerg.json

Reference: GHCN-Daily station precipitation (NOAA NCEI, QC-flagged values dropped) at 18 stations on
6 continents, chosen near the demo fields (Fallon NV, Ames IA, Córdoba ES, Machakos/Nairobi KE) plus India,
West Africa, South-East Asia, northern Australia, Latin America and the Caribbean.

Products (all from the anonymous NASA POWER daily point API, so the app can use them worldwide):
  P_lst   PRECTOTCORR (MERRA-2 bias-corrected) in local solar time — what FieldShift uses today
  I       IMERG_PRECTOT (GPM IMERG Final, 0.1°) — UTC days only (POWER returns fill values for LST)
  B50     0.5 · (P_lst + I) daily blend
  MR      P_lst rescaled month by month to IMERG's monthly total (POWER timing, IMERG amounts)
  CR      P_lst × calendar-month climatological IMERG/POWER ratio
  CR50    P_lst × (0.5 + 0.5 · that ratio): the bridge the app serves after IMERG's ~2-month latency (same mean as B50)
  B30/B70 daily blends with 30 % / 70 % IMERG weight (sensitivity of the a-priori 50 % weight)
  BMR     B50 rescaled month by month to IMERG's monthly total

Metrics, 2001–2025, only on days with a valid gauge value:
  * daily Pearson r (best common lag of -1/0/+1 day, chosen on the mean of P and I so no product is favoured)
  * wet-day critical success index (≥ 1 mm)
  * matched monthly totals (months with ≥ 20 valid gauge days; product summed over the same days): r, bias, KGE
  * 3-month anomaly r: rolling 3-month matched totals minus their calendar-month mean (an SPI-3 proxy)

Caveat printed with the results: IMERG Final is calibrated to GPCC monthly gauge analyses and MERRA-2's corrected
rain to CPC gauges, and GHCN stations feed both, so this is not a fully independent test.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldshift.data.http import CACHE_DIR, get_json  # noqa: E402
from fieldshift.science import rainblend  # noqa: E402

START, END = dt.date(2001, 1, 1), dt.date(2025, 12, 31)
POWER = "https://power.larc.nasa.gov/api/temporal/daily/point"
GHCN = "https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/{}.csv"

# id, station, name, continent, lat, lon  (station coordinates are used for the product extraction)
SITES = [
    ("fallon_nv", "USC00262780", "Fallon Exp. Stn, Nevada (demo field)", "North America", 39.4567, -118.7781),
    ("ames_ia", "USC00130200", "Ames 8 WSW, Iowa (demo field)", "North America", 41.9894, -93.6883),
    ("cordoba_es", "SP000008410", "Córdoba airport, Spain (demo field)", "Europe", 37.8442, -4.8486),
    ("jaen_es", "SPE00120170", "Jaén, Spain", "Europe", 37.7781, -3.8092),
    ("nairobi_ke", "KE000063740", "Nairobi JKIA, Kenya (Machakos demo)", "Africa", -1.3190, 36.9280),
    ("niamey_ne", "NG000001052", "Niamey, Niger", "Africa", 13.4810, 2.1700),
    ("ouaga_bf", "UVM00065503", "Ouagadougou, Burkina Faso", "Africa", 12.3530, -1.5120),
    ("bamako_ml", "MLM00061291", "Bamako-Sénou, Mali", "Africa", 12.5340, -7.9500),
    ("dakar_sn", "SG000061641", "Dakar-Yoff, Senegal", "Africa", 14.7330, -17.5000),
    ("delhi_in", "IN022021900", "New Delhi Safdarjung, India", "Asia", 28.5830, 77.2000),
    ("pune_in", "IN012190100", "Pune, India", "Asia", 18.5330, 73.8500),
    ("hyderabad_in", "IN001080500", "Hyderabad Begumpet, India", "Asia", 17.4500, 78.4670),
    ("nagpur_in", "IN012141800", "Nagpur Sonegaon, India", "Asia", 21.1000, 79.0500),
    ("bangkok_th", "TH000048456", "Bangkok Don Muang, Thailand", "Asia", 13.9170, 100.6000),
    ("darwin_au", "ASN00014015", "Darwin airport, Australia", "Australia", -12.4239, 130.8925),
    ("wagga_au", "ASN00072150", "Wagga Wagga, Australia", "Australia", -35.1583, 147.4573),
    ("sanjuan_pr", "RQW00011641", "San Juan, Puerto Rico", "North America", 18.4319, -66.0106),
    ("bogota_co", "CO000080222", "Bogotá El Dorado, Colombia", "South America", 4.7010, -74.1500),
]
PRODUCTS = ["P_lst", "I", "B50", "MR", "CR", "CR50", "B30", "B70", "BMR"]


def ghcn(station: str) -> dict[dt.date, float]:
    """Daily PRCP in mm (GHCN 'access' CSV stores tenths of mm); QC-flagged values dropped."""
    f = CACHE_DIR / "ghcn" / f"{station}.csv"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(GHCN.format(station), timeout=120)
        r.raise_for_status()
        f.write_bytes(r.content)
    out: dict[dt.date, float] = {}
    for row in csv.DictReader(io.StringIO(f.read_text())):
        p = (row.get("PRCP") or "").strip()
        if not p:
            continue
        attrs = (row.get("PRCP_ATTRIBUTES") or "").split(",")
        if len(attrs) > 1 and attrs[1].strip():  # quality flag set -> failed a QC check
            continue
        d = dt.date.fromisoformat(row["DATE"])
        if START <= d <= END:
            out[d] = float(p) / 10.0
    return out


def power(lat: float, lon: float, params: str, ts: str) -> dict[str, np.ndarray]:
    q = {
        "parameters": params,
        "community": "AG",
        "latitude": round(lat, 3),
        "longitude": round(lon, 3),
        "start": START.strftime("%Y%m%d"),
        "end": END.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": ts,
    }
    p = get_json(POWER, q, ttl_s=60 * 86400, timeout_s=180).data["properties"]["parameter"]
    n = (END - START).days + 1
    out = {}
    for k, series in p.items():
        a = np.full(n, np.nan)
        for ds, v in series.items():
            i = (dt.date(int(ds[:4]), int(ds[4:6]), int(ds[6:8])) - START).days
            if 0 <= i < n and v is not None and v > -998:
                a[i] = v
        out[k] = a
    return out


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 10 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return float("nan")
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def kge(sim: np.ndarray, obs: np.ndarray) -> float:
    ok = np.isfinite(sim) & np.isfinite(obs)
    s, o = sim[ok], obs[ok]
    if len(s) < 10 or o.mean() == 0 or o.std() == 0:
        return float("nan")
    r = np.corrcoef(s, o)[0, 1]
    return float(1 - np.sqrt((r - 1) ** 2 + (s.std() / o.std() - 1) ** 2 + (s.mean() / o.mean() - 1) ** 2))


def csi(sim: np.ndarray, obs: np.ndarray, thr: float = 1.0) -> float:
    ok = np.isfinite(sim) & np.isfinite(obs)
    s, o = sim[ok] >= thr, obs[ok] >= thr
    hits, miss, fa = (s & o).sum(), (~s & o).sum(), (s & ~o).sum()
    return float(hits / (hits + miss + fa)) if hits + miss + fa else float("nan")


def evaluate(site: tuple[str, str, str, str, float, float]) -> dict[str, object]:
    sid, station, name, continent, lat, lon = site
    g = ghcn(station)
    n = (END - START).days + 1
    dates = [START + dt.timedelta(days=i) for i in range(n)]
    obs = np.array([g.get(d, np.nan) for d in dates])
    utc = power(lat, lon, "PRECTOTCORR,IMERG_PRECTOT", "UTC")
    lst = power(lat, lon, "PRECTOTCORR", "LST")
    p_lst, imerg = lst["PRECTOTCORR"], utc["IMERG_PRECTOT"]
    prods = {
        "P_lst": p_lst,
        "I": imerg,
        "B50": rainblend.blend_daily(p_lst, imerg, 0.5),
        "MR": rainblend.monthly_rescale(p_lst, imerg, dates),
        "CR": p_lst
        * rainblend.climatological_ratio(p_lst, imerg, dates)[np.array([d.month - 1 for d in dates])],
        "CR50": p_lst
        * rainblend.bridge_factor(rainblend.climatological_ratio(p_lst, imerg, dates))[
            np.array([d.month - 1 for d in dates])
        ],
        "B30": rainblend.blend_daily(p_lst, imerg, 0.3),
        "B70": rainblend.blend_daily(p_lst, imerg, 0.7),
        "BMR": rainblend.monthly_rescale(rainblend.blend_daily(p_lst, imerg, 0.5), imerg, dates),
    }

    # common lag (gauge day convention differs: many co-op/SYNOP gauges report the 24 h ending in the morning)
    def shifted(a: np.ndarray, lag: int) -> np.ndarray:
        return np.roll(a, lag) if lag else a

    lag = max(
        (-1, 0, 1),
        key=lambda k: np.nanmean([pearson(shifted(p_lst, k), obs), pearson(shifted(imerg, k), obs)]),
    )
    months = np.array([d.year * 12 + d.month - 1 for d in dates])
    valid = np.isfinite(obs)
    res: dict[str, object] = {
        "site": sid,
        "station": station,
        "name": name,
        "continent": continent,
        "lat": lat,
        "lon": lon,
        "zone": rainblend.zone(lat),
        "lag_days": lag,
        "gauge_days": int(valid.sum()),
    }
    mkeys = np.unique(months)
    mobs, mprod = [], {k: [] for k in prods}
    for m in mkeys:
        sel = (months == m) & valid
        if sel.sum() < 20:
            continue
        sh = {k: shifted(v, lag)[sel] for k, v in prods.items()}
        if any(not np.isfinite(x).all() for x in sh.values()):
            continue
        mobs.append(obs[sel].sum())
        for k in prods:
            mprod[k].append(float(sh[k].sum()))
    mo = np.array(mobs)
    res["months"] = len(mo)
    # 3-month rolling matched totals -> calendar-month anomalies (SPI-3 proxy); needs consecutive months
    metrics: dict[str, dict[str, float]] = {}
    for k, a in prods.items():
        s = shifted(a, lag)
        mp = np.array(mprod[k])
        metrics[k] = {
            "daily_r": round(pearson(s, obs), 3),
            "wet_day_csi": round(csi(s, obs), 3),
            "monthly_r": round(pearson(mp, mo), 3),
            "monthly_bias_pct": round(100 * (mp.sum() / mo.sum() - 1), 1) if len(mo) else float("nan"),
            "monthly_kge": round(kge(mp, mo), 3),
            "anom3_r": round(_anom3_r(mp, mo), 3),
        }
    res["metrics"] = metrics
    return res


def _anom3_r(mp: np.ndarray, mo: np.ndarray) -> float:
    if len(mo) < 24:
        return float("nan")
    k = np.ones(3)
    sp, so = np.convolve(mp, k, "valid"), np.convolve(mo, k, "valid")
    idx = np.arange(len(sp)) % 12  # matched months are mostly consecutive; position-in-year is approximate
    ap = sp - np.array([sp[idx == i].mean() for i in idx])
    ao = so - np.array([so[idx == i].mean() for i in idx])
    return pearson(ap, ao)


def main() -> None:
    rows = []
    for s in SITES:
        try:
            r = evaluate(s)
        except Exception as e:  # report and continue: one bad station must not hide the rest
            print(f"{s[0]}: FAILED {e}")
            continue
        rows.append(r)
        m = r["metrics"]
        print(
            f"{r['site']:<13} {r['zone']:<11} months={r['months']:<4} lag={r['lag_days']:+d}  "
            + "  ".join(
                f"{k}: d{m[k]['daily_r']:.2f} m{m[k]['monthly_r']:.2f} kge{m[k]['monthly_kge']:.2f} b{m[k]['monthly_bias_pct']:+.0f}%"
                for k in ("P_lst", "I", "B50", "MR")
            )
        )
    summary = rainblend.summarise(rows, PRODUCTS)
    out = {
        "generated": dt.date.today().isoformat(),
        "period": [START.isoformat(), END.isoformat()],
        "reference": "GHCN-Daily (NOAA NCEI), QC-flagged values dropped",
        "caveat": "IMERG Final is calibrated with GPCC monthly gauge analyses and MERRA-2 corrected precipitation with CPC gauges; "
        "GHCN stations contribute to both, so the test is not fully independent.",
        "sites": rows,
        "summary": summary,
    }
    path = ROOT / "docs" / "validation" / "imerg.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
