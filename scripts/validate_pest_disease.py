"""Validation of the global pest & disease risk models against documented outbreaks (docs/VALIDATION.md, V9).

Run on the data box (VPS):

    backend/.venv/bin/python scripts/validate_pest_disease.py            # all cases
    backend/.venv/bin/python scripts/validate_pest_disease.py locust     # subset

Weather is NASA POWER only (hourly T2M, RH2M, T2MDEW, PRECTOTCORR from 2001; daily from 1984). Every case
states its expectation *before* the result is computed (EXPECT strings) and the outcome is reported as
hit / partial / miss. Results go to docs/validation/pest_disease.json.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldshift.data.http import get_json  # noqa: E402
from fieldshift.science import disease, leafwet  # noqa: E402
from fieldshift.science import globalrisk as gr  # noqa: E402

OUT = ROOT / "docs" / "validation" / "pest_disease.json"


# --------------------------------------------------------------------------- NASA POWER access
LAPSE = -0.0065  # °C per m (ICAO standard atmosphere)


def grid_elevation(lat: float, lon: float) -> float:
    f = get_json(
        "https://power.larc.nasa.gov/api/temporal/daily/point",
        {
            "parameters": "PRECTOTCORR",
            "community": "AG",
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "start": "20100101",
            "end": "20100102",
            "format": "JSON",
        },
        ttl_s=365 * 86400,
    )
    return float(f.data["geometry"]["coordinates"][2])


def power_hourly(lat: float, lon: float, start: dt.date, end: dt.date) -> dict[str, list[Any]]:
    f = get_json(
        "https://power.larc.nasa.gov/api/temporal/hourly/point",
        {
            "parameters": "T2M,RH2M,T2MDEW,PRECTOTCORR",
            "community": "AG",
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": "LST",
        },
        ttl_s=365 * 86400,
        timeout_s=240,
    )
    p = f.data["properties"]["parameter"]
    keys = sorted(p["T2M"])

    def v(name: str, k: str) -> float | None:
        x = p.get(name, {}).get(k)
        return None if x is None or x <= -998 else float(x)

    return {
        "time": [f"{k[:4]}-{k[4:6]}-{k[6:8]}T{k[8:10]}:00" for k in keys],
        "temperature_2m": [v("T2M", k) for k in keys],
        "relative_humidity_2m": [v("RH2M", k) for k in keys],
        "dew_point_2m": [v("T2MDEW", k) for k in keys],
        "precipitation": [v("PRECTOTCORR", k) for k in keys],
    }


def power_daily(
    lat: float, lon: float, start: dt.date, end: dt.date
) -> tuple[list[dt.date], dict[str, np.ndarray]]:
    f = get_json(
        "https://power.larc.nasa.gov/api/temporal/daily/point",
        {
            "parameters": "T2M_MAX,T2M_MIN,PRECTOTCORR",
            "community": "AG",
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
        },
        ttl_s=365 * 86400,
        timeout_s=240,
    )
    p = f.data["properties"]["parameter"]
    keys = sorted(p["T2M_MAX"])
    dates = [dt.date(int(k[:4]), int(k[4:6]), int(k[6:8])) for k in keys]
    arr = {n: np.array([np.nan if p[n][k] <= -998 else p[n][k] for k in keys], dtype=float) for n in p}
    return dates, arr


def risk_input(
    lat: float, lon: float, start: dt.date, end: dt.date, hourly: bool = True, elev: float | None = None
) -> gr.RiskInput:
    """POWER weather for a site. With the site elevation given, temperatures and dew point are shifted by the
    standard lapse rate from the POWER grid-cell mean elevation to the site (RH unchanged): in mountains the
    ~50 km cell can be 500–1000 m off (Chinchiná: cell 2138 m, town 1360 m)."""
    d0 = start - dt.timedelta(days=40)
    dates, a = power_daily(lat, lon, d0, end)
    dT = 0.0 if elev is None else LAPSE * (elev - grid_elevation(lat, lon))
    h = None
    if hourly:
        raw = power_hourly(lat, lon, start, end)
        for k in ("temperature_2m", "dew_point_2m"):
            raw[k] = [None if x is None else x + dT for x in raw[k]]
        h = leafwet.from_dict(raw)
    return gr.RiskInput(
        lat,
        lon,
        end,
        dates,
        a["T2M_MAX"] + dT,
        a["T2M_MIN"] + dT,
        a["PRECTOTCORR"],
        hourly=h,
        elevation_m=elev,
    )


def season_stats(res: gr.RiskResult, start: dt.date, end: dt.date) -> dict[str, float]:
    v = [s for d, s in res.scores.items() if start <= d <= end]
    return {
        "days": len(v),
        "high_days": int(sum(s >= 0.55 for s in v)),
        "severe_days": int(sum(s >= 0.85 for s in v)),
        "moderate_days": int(sum(s >= 0.25 for s in v)),
        "mean_score": round(float(np.mean(v)), 3) if v else float("nan"),
    }


def rank_of(per_year: dict[int, dict[str, float]], year: int, key: str) -> int:
    order = sorted(per_year, key=lambda y: -per_year[y][key])
    return order.index(year) + 1


# --------------------------------------------------------------------------- cases
CASES: dict[str, Any] = {}


def case(fn: Any) -> Any:
    CASES[fn.__name__] = fn
    return fn


def yearly(
    model: str,
    lat: float,
    lon: float,
    years: range,
    m0: tuple[int, int],
    m1: tuple[int, int],
    elev: float | None = None,
) -> dict[int, dict[str, float]]:
    out = {}
    for y in years:
        a, b = dt.date(y, *m0), dt.date(y, *m1)
        x = risk_input(lat, lon, a, b, hourly=gr.MODELS[model].hourly, elev=elev)
        out[y] = season_stats(gr.MODELS[model].fn(x), a, b)
        print(model, y, out[y], flush=True)
    return out


@case
def locust() -> dict[str, Any]:
    """Desert locust: the 2018 cyclones Mekunu (landfall 26 May 2018) and Luban (Oct 2018) flooded the southern
    Empty Quarter and started the 2019–2020 upsurge (FAO Locust Watch); the Oct 2003 rains in NW Africa started
    the 2003–05 upsurge. Breeding-favourable days (score ≥ 0.55) per year at points in those areas, 2001–2022."""
    EXPECT = "2018 ranks 1st at the Empty Quarter point; 2003 ranks in the top 3 at the NW Mauritania/W Sahara point"
    out: dict[str, Any] = {"expect": EXPECT}
    for name, (lat, lon), yr in (
        ("empty_quarter", (18.5, 51.5), 2018),
        ("nw_africa", (21.5, -13.0), 2003),
        ("w_sahara", (24.5, -11.5), 2003),
    ):
        dates, a = power_daily(lat, lon, dt.date(2000, 11, 1), dt.date(2022, 12, 31))
        x = gr.RiskInput(lat, lon, dates[-1], dates, a["T2M_MAX"], a["T2M_MIN"], a["PRECTOTCORR"])
        res = gr.desert_locust(x)
        per = {}
        for y in range(2001, 2023):
            v = [s for d, s in res.scores.items() if d.year == y]
            per[y] = {
                "high_days": int(sum(s >= 0.55 for s in v)),
                "max": round(max(v), 2),
                "annual_rain_mm": round(
                    float(
                        np.nansum([r for d, r in zip(dates, a["PRECTOTCORR"], strict=True) if d.year == y])
                    ),
                    0,
                ),
            }
        first = sorted(d for d, s in res.scores.items() if d.year == yr and s >= 0.55)
        out[name] = {
            "lat": lat,
            "lon": lon,
            "per_year": per,
            "event_year": yr,
            "rank_event_year": rank_of(per, yr, "high_days"),
            "n_years": len(per),
            "first_favourable_day": first[0].isoformat() if first else None,
        }
    return out


@case
def coffee_rust() -> dict[str, Any]:
    """Coffee leaf rust, Colombia: the 2008–2011 epidemic (incidence > 40 % vs < 10 % before; Rozo et al. 2012,
    Avelino et al. 2015) followed La Niña rains and fewer sunshine hours. Chinchiná (Caldas, Cenicafé), 1360 m."""
    EXPECT = "mean infection-favourable days in 2008–2011 above the 2003–2007 and 2012–2016 means"
    lat, lon, elev = 4.98, -75.60, 1360.0
    per = yearly("coffee_leaf_rust", lat, lon, range(2003, 2017), (1, 1), (12, 31), elev)
    epi = [per[y]["high_days"] for y in range(2008, 2012)]
    other = [per[y]["high_days"] for y in per if y not in range(2008, 2012)]
    return {
        "expect": EXPECT,
        "site": "Chinchiná, Caldas, Colombia",
        "elev_m": elev,
        "per_year": per,
        "mean_epidemic": round(float(np.mean(epi)), 1),
        "mean_other": round(float(np.mean(other)), 1),
        "rank_2010": rank_of(per, 2010, "high_days"),
        "n_years": len(per),
    }


@case
def blight_tropical() -> dict[str, Any]:
    """Late blight in tropical highlands, where pressure is among the highest in the world (Toluca Valley, Mexico,
    2600 m — Grünwald et al. 2002; Ecuador highlands, Santa Catalina 3050 m — Pérez & Forbes 2010): the rainy
    season should be strongly favourable and the dry season much less. Compare the existing Hutton rule."""
    EXPECT = (
        "tropical model: rainy season ≥ 2× the dry-season favourable days at Toluca; "
        "Hutton finds few/no days because highland nights are < 10 °C"
    )
    out: dict[str, Any] = {"expect": EXPECT}
    sites = {
        "toluca_mx": (19.29, -99.66, 2600.0, ((7, 1), (9, 30)), ((1, 1), (3, 31))),
        "santa_catalina_ec": (-0.37, -78.55, 3050.0, ((2, 1), (5, 31)), ((7, 1), (9, 30))),
    }
    for name, (lat, lon, elev, wet, dry) in sites.items():
        rows = {}
        for y in range(2010, 2020):
            r = {}
            for lab, (m0, m1) in (("rainy", wet), ("dry", dry)):
                a, b = dt.date(y, *m0), dt.date(y, *m1)
                x = risk_input(lat, lon, a, b, elev=elev)
                trop = season_stats(gr.tropical_late_blight(x), a, b)
                assert x.hourly is not None
                raw = {
                    "time": [t.isoformat(timespec="minutes") for t in x.hourly.time],
                    "temperature_2m": list(x.hourly.t),
                    "relative_humidity_2m": list(x.hourly.rh),
                }
                hut = disease.daily_scores(disease.hourly_by_day(raw))["late_blight"]
                r[lab] = {
                    "tropical_sv_ge2_days": int(
                        sum(s >= 0.5 for d, s in gr.tropical_late_blight(x).scores.items() if a <= d <= b)
                    ),
                    "tropical_high_days": trop["high_days"],
                    "hutton_full_days": int(sum(v >= 1.0 for d, v in hut.items() if a <= d <= b)),
                    "hutton_any_days": int(sum(v >= 0.3 for d, v in hut.items() if a <= d <= b)),
                }
            rows[y] = r
            print(name, y, r, flush=True)
        out[name] = {
            "lat": lat,
            "lon": lon,
            "elev_m": elev,
            "per_year": rows,
            "rainy_mean_sv_ge2": round(
                float(np.mean([rows[y]["rainy"]["tropical_sv_ge2_days"] for y in rows])), 1
            ),
            "dry_mean_sv_ge2": round(
                float(np.mean([rows[y]["dry"]["tropical_sv_ge2_days"] for y in rows])), 1
            ),
            "rainy_mean_hutton_full": round(
                float(np.mean([rows[y]["rainy"]["hutton_full_days"] for y in rows])), 1
            ),
        }
    return out


@case
def rice_blast() -> dict[str, Any]:
    """BLASTAM in Tohoku (Osaki, Miyagi), Jul–Aug 2001–2015. 2003 was a cool, wet 'yamase' summer — the first
    cool-weather damage in Tohoku for ten years (NARO Tohoku), with conditions favouring panicle blast in northern Japan
    (Open Agric. J. 10:28, 2016, doi:10.2174/1874331501610010028). 2010 was Japan's record-hot summer."""
    EXPECT = "2003 ranks in the top 3 of 15 summers by BLASTAM favourable days; 2010 in the bottom half"
    lat, lon, elev = 38.58, 140.95, 40.0
    per = yearly("rice_blast", lat, lon, range(2001, 2016), (7, 1), (8, 31), elev)
    return {
        "expect": EXPECT,
        "site": "Osaki, Miyagi, Japan",
        "per_year": per,
        "rank_2003_favourable": rank_of(per, 2003, "severe_days"),
        "rank_2003_quasi_or_better": rank_of(per, 2003, "moderate_days"),
        "rank_2010_favourable": rank_of(per, 2010, "severe_days"),
        "n_years": len(per),
    }


@case
def coffee_tmax_band() -> dict[str, Any]:
    """Avelino et al. 2015 reference numbers for Chinchiná (1430 m): 78 % of days with Tmax 22–28 °C in 2008–2011 vs
    67 % in 1991–1994. Reproduced from NASA POWER daily Tmax, lapse-corrected from the grid cell to 1430 m."""
    EXPECT = "share of days with Tmax 22–28 °C higher in 2008–2011 than in 1991–1994 (paper: 78 % vs 67 %)"
    lat, lon, elev = 4.98, -75.60, 1430.0
    dates, a = power_daily(lat, lon, dt.date(1991, 1, 1), dt.date(2011, 12, 31))
    dT = LAPSE * (elev - grid_elevation(lat, lon))
    tx = a["T2M_MAX"] + dT
    out: dict[str, Any] = {"expect": EXPECT, "lapse_shift_c": round(dT, 2)}
    for lab, (y0, y1) in (("1991_1994", (1991, 1994)), ("2008_2011", (2008, 2011))):
        m = np.array([y0 <= d.year <= y1 for d in dates]) & np.isfinite(tx)
        out[lab] = {
            "share_tmax_22_28": round(float(np.mean((tx[m] >= 22) & (tx[m] <= 28))), 3),
            "mean_tmax": round(float(np.mean(tx[m])), 2),
            "mean_dtr": round(float(np.mean(a["T2M_MAX"][m] - a["T2M_MIN"][m])), 2),
        }
    return out


@case
def sigatoka_season() -> dict[str, Any]:
    """Black Sigatoka in Urabá, Colombia (Apartadó, 7.88 N, 76.63 W, 30 m): disease pressure is highest in the rainy
    season (Apr–Nov) and lowest in the Dec–Mar dry season."""
    EXPECT = "mean daily score in Apr–Nov above Jan–Mar in most years"
    lat, lon, elev = 7.88, -76.63, 30.0
    rows = {}
    for y in range(2010, 2020):
        r = {}
        for lab, (m0, m1) in (("dry_jan_mar", ((1, 1), (3, 31))), ("rainy_apr_nov", ((4, 1), (11, 30)))):
            a, b = dt.date(y, *m0), dt.date(y, *m1)
            r[lab] = season_stats(gr.black_sigatoka(risk_input(lat, lon, a, b, elev=elev)), a, b)
        rows[y] = r
        print("sigatoka", y, r, flush=True)
    hits = sum(rows[y]["rainy_apr_nov"]["mean_score"] > rows[y]["dry_jan_mar"]["mean_score"] for y in rows)
    return {"expect": EXPECT, "per_year": rows, "years_rainy_gt_dry": hits, "n_years": len(rows)}


@case
def gls_predictors() -> dict[str, Any]:
    """Paul & Munkvold 2005 observed, V4–V12 in Iowa 1998–2002: 85.5–230.5 h at 22–30 °C and 122–330 humid night
    hours (RH ≥ 90 %). POWER hourly exists from 2001: does POWER reproduce values inside those ranges at Ames for
    2001–2002 (V4–V12 ≈ 1 Jun – 5 Jul for early-May planting)?"""
    EXPECT = "both predictor totals fall inside the published ranges in 2001 and 2002"
    lat, lon = 42.03, -93.62
    out: dict[str, Any] = {"expect": EXPECT}
    for y in (2001, 2002):
        h = leafwet.from_dict(power_hourly(lat, lon, dt.date(y, 6, 1), dt.date(y, 7, 5)))
        night = np.array([t.hour >= 20 or t.hour < 8 for t in h.time])
        out[str(y)] = {
            "hours_22_30": int(((h.t >= 22) & (h.t <= 30)).sum()),
            "night_hours_rh90": int(((h.rh >= 90) & night).sum()),
        }
    return out


def main() -> None:
    want = sys.argv[1:] or list(CASES)
    results = json.loads(OUT.read_text()) if OUT.exists() else {}
    for k in want:
        print(f"== {k}", flush=True)
        try:
            results[k] = CASES[k]()
        except Exception as e:  # report failures honestly
            results[k] = {"status": f"failed: {type(e).__name__}: {e}"}
        results[k]["run_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        print(json.dumps(results[k], default=str)[:3000], flush=True)
        OUT.write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
