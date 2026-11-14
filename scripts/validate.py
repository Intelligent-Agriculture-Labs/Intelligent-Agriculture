"""FieldShift validation suite — run on the data box (VPS):

    backend/.venv/bin/python scripts/validate.py            # all experiments
    backend/.venv/bin/python scripts/validate.py et0 usdm   # subset

Writes docs/validation/results.json and PNG figures to docs/validation/. Every experiment compares a
FieldShift output with an *independent* reference dataset. Results are reported as they come out,
including weak ones (see docs/VALIDATION.md).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("FIELDSHIFT_ORNL_RETRIES", "5")

from fieldshift.data import sources  # noqa: E402
from fieldshift.data.http import DataUnavailable, get_json  # noqa: E402
from fieldshift.engine.context import build  # noqa: E402
from fieldshift.science import disease, drought  # noqa: E402
from fieldshift.science.cropmodel import gdd_requirement, simulate  # noqa: E402

OUT = ROOT / "docs" / "validation"
OUT.mkdir(parents=True, exist_ok=True)
SITES = {
    "fallon_nv": (39.472, -118.777),
    "ames_ia": (42.03, -93.62),
    "cordoba_es": (37.885, -4.779),
    "machakos_ke": (-1.517, 37.263),
}
AS_OF = dt.date(2025, 6, 30)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:  # figures are optional
    plt = None


def metrics(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    r = float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else float("nan")
    return {
        "n": int(m.sum()),
        "bias": round(float(np.mean(a - b)), 3),
        "rmse": round(float(np.sqrt(np.mean((a - b) ** 2))), 3),
        "mae": round(float(np.mean(np.abs(a - b))), 3),
        "r": round(r, 3),
        "r2": round(r * r, 3),
        "mean_model": round(float(np.mean(a)), 3),
        "mean_ref": round(float(np.mean(b)), 3),
    }


def era5_daily(lat: float, lon: float, start: dt.date, end: dt.date, daily: str) -> dict[str, Any]:
    f = get_json(
        "https://archive-api.open-meteo.com/v1/archive",
        {
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": daily,
            "timezone": "auto",
        },
        ttl_s=30 * 86400,
        timeout_s=180,
    )
    return f.data["daily"]


# --------------------------------------------------------------------------- 1. ET0
def exp_et0() -> dict[str, Any]:
    """FieldShift FAO-56 PM ET0 from NASA POWER vs. FAO-56 ET0 computed by Open-Meteo from ERA5 (independent reanalysis)."""
    res = {}
    for sid, (lat, lon) in SITES.items():
        ctx = build(lat, lon, AS_OF)
        s, e = dt.date(2015, 1, 1), dt.date(2024, 12, 31)
        ref = era5_daily(lat, lon, s, e, "et0_fao_evapotranspiration")
        i0, i1 = ctx.idx(s), ctx.idx(e) + 1
        model = ctx.weather.et0[i0:i1]
        refv = np.array([np.nan if v is None else v for v in ref["et0_fao_evapotranspiration"]], float)
        daily = metrics(model, refv)
        # monthly totals
        months = np.array([(d.year, d.month) for d in ctx.weather.dates[i0:i1]])
        keys = sorted({tuple(m) for m in months})
        mm = np.array([np.nansum(model[(months[:, 0] == y) & (months[:, 1] == mo)]) for y, mo in keys])
        mr = np.array([np.nansum(refv[(months[:, 0] == y) & (months[:, 1] == mo)]) for y, mo in keys])
        res[sid] = {"daily_mm": daily, "monthly_mm": metrics(mm, mr)}
        if plt is not None:
            fig, ax = plt.subplots(figsize=(4, 4))
            ax.scatter(mr, mm, s=6, alpha=0.6)
            lim = max(mm.max(), mr.max()) * 1.05
            ax.plot([0, lim], [0, lim], "k--", lw=0.8)
            ax.set_xlabel("ERA5 FAO-56 ET₀ (mm/month)")
            ax.set_ylabel("FieldShift ET₀ from NASA POWER (mm/month)")
            ax.set_title(
                f"ET₀ monthly, {sid} 2015–2024\nr={res[sid]['monthly_mm']['r']}, bias={res[sid]['monthly_mm']['bias']} mm"
            )
            fig.tight_layout()
            fig.savefig(OUT / f"et0_{sid}.png", dpi=110)
            plt.close(fig)
    return res


# --------------------------------------------------------------------------- 2. soil water vs ERA5-Land
def exp_soil_water() -> dict[str, Any]:
    """Rain-fed FieldShift root-zone relative water (1 − Dr/TAW) vs. ERA5-Land 7–100 cm soil moisture, growing seasons."""
    cases = {
        "ames_ia": ("maize", "05-01"),
        "cordoba_es": ("winter_wheat", "11-15"),
        "machakos_ke": ("maize", "10-20"),
    }
    res = {}
    for sid, (cid, md) in cases.items():
        lat, lon = SITES[sid]
        ctx = build(lat, lon, AS_OF)
        rs = []
        all_m, all_r = [], []
        for y in range(2015, 2024):
            p = dt.date(y, int(md[:2]), int(md[3:]))
            req = gdd_requirement(
                __import__("fieldshift.science.cropmodel", fromlist=["crop"]).crop(cid),
                ctx.weather,
                p,
                list(range(2005, 2020)),
            )
            r = simulate(
                cid,
                ctx.weather,
                p,
                taw_per_m=ctx.taw_per_m,
                strategy="rainfed",
                gdd_req=req,
                record_daily=True,
            )
            dates = [dt.date.fromisoformat(x) for x in r.daily["date"]]
            rel = 1 - np.array(r.daily["dr"]) / np.maximum(1, np.array(r.daily["taw"]))
            era = sources.era5_soil_moisture(lat, lon, dates[0], dates[-1])
            ref = 0.3 * era["SM_7_28"] + 0.7 * era["SM_28_100"]
            n = min(len(rel), len(ref))
            m = metrics(rel[:n], ref[:n])
            rs.append(m["r"])
            all_m.append((rel[:n] - np.nanmean(rel[:n])) / (np.nanstd(rel[:n]) or 1))
            all_r.append((ref[:n] - np.nanmean(ref[:n])) / (np.nanstd(ref[:n]) or 1))
        pooled = metrics(np.concatenate(all_m), np.concatenate(all_r))
        res[sid] = {
            "crop": cid,
            "seasons": len(rs),
            "median_r_per_season": round(float(np.nanmedian(rs)), 3),
            "pooled_standardized_r": pooled["r"],
            "per_season_r": rs,
        }
    return res


# --------------------------------------------------------------------------- 3. drought vs U.S. Drought Monitor
def exp_usdm() -> dict[str, Any]:
    """Weekly FieldShift drought indicators vs. USDM county Drought Severity & Coverage Index (DSCI = Σ cumulative % area D0–D4)."""
    counties = {"fallon_nv": "32001", "ames_ia": "19169"}
    res = {}
    for sid, fips in counties.items():
        lat, lon = SITES[sid]
        ctx = build(lat, lon, AS_OF)
        f = get_json(
            "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent",
            {"aoi": fips, "startdate": "1/1/2005", "enddate": "12/31/2024", "statisticsType": 1},
            ttl_s=60 * 86400,
            timeout_s=120,
        )
        rows = f.data
        w = ctx.weather
        n = ctx.idx(AS_OF) + 1
        dates = w.dates[:n]
        dsci, spi90, spei90, lvl, lvl_v2 = [], [], [], [], []
        extra: dict[str, list[float]] = {"spi180": [], "spi365": [], "spei180": [], "spei365": []}
        for r in rows:
            d = dt.date.fromisoformat(r["mapDate"][:10])
            score = sum(float(r[k]) for k in ("d0", "d1", "d2", "d3", "d4"))
            s9 = drought.spi_at(w.rain[:n], dates, d, 90)
            se = drought.standardized_at((w.rain - w.et0)[:n], dates, d, 90)
            s3 = drought.spi_at(w.rain[:n], dates, d, 30)
            s18 = drought.spi_at(w.rain[:n], dates, d, 180)
            s36 = drought.spi_at(w.rain[:n], dates, d, 365)
            e18 = drought.standardized_at((w.rain - w.et0)[:n], dates, d, 180)
            e36 = drought.standardized_at((w.rain - w.et0)[:n], dates, d, 365)
            if None in (s9, se, s18, s36, e18, e36):
                continue
            dsci.append(score)
            spi90.append(s9)
            spei90.append(se)
            for k, v in (("spi180", s18), ("spi365", s36), ("spei180", e18), ("spei365", e36)):
                extra[k].append(v)
            lvl.append(drought.combined_level(s3, s9, se, None, None)[0])
            lvl_v2.append(drought.combined_level(s3, s9, se, None, None, spei365=e36)[0])
        dsci_a = np.array(dsci)
        rho_spi = stats.spearmanr(-np.array(spi90), dsci_a)
        rho_spei = stats.spearmanr(-np.array(spei90), dsci_a)
        rho_lvl = stats.spearmanr(np.array(lvl), dsci_a)
        rho_v2 = stats.spearmanr(np.array(lvl_v2), dsci_a)

        def det(levels: list[int], dsci_a: np.ndarray = dsci_a) -> dict[str, Any]:
            usdm_d1 = dsci_a >= 200  # ≥ D1 over (roughly) the whole county
            fs_d1 = np.array(levels) >= 2
            tp = int(np.sum(usdm_d1 & fs_d1))
            fp = int(np.sum(~usdm_d1 & fs_d1))
            fn = int(np.sum(usdm_d1 & ~fs_d1))
            return {
                "hit_rate": round(tp / max(1, tp + fn), 3),
                "false_alarm_ratio": round(fp / max(1, tp + fp), 3),
                "tp": tp,
                "fp": fp,
                "fn": fn,
            }

        res[sid] = {
            "weeks": len(dsci),
            "spearman_spi90": round(float(rho_spi.statistic), 3),
            "spearman_spei90": round(float(rho_spei.statistic), 3),
            "spearman_level_v1": round(float(rho_lvl.statistic), 3),
            "spearman_level_v2": round(float(rho_v2.statistic), 3),
            **{
                f"spearman_{k}": round(float(stats.spearmanr(-np.array(v), dsci_a).statistic), 3)
                for k, v in extra.items()
            },
            "d1_detection_v1": det(lvl),
            "d1_detection_v2": det(lvl_v2),
        }
        if plt is not None:
            fig, ax = plt.subplots(figsize=(8, 3))
            dd = [dt.date.fromisoformat(r["mapDate"][:10]) for r in rows][: len(dsci)]
            ax.plot(dd, dsci_a, label="USDM DSCI (0–500)", color="#b45309")
            ax2 = ax.twinx()
            ax2.plot(dd, spei90, label="FieldShift SPEI-90 (NASA POWER)", color="#2563eb", lw=0.8)
            ax2.invert_yaxis()
            ax.set_title(
                f"Drought: FieldShift vs U.S. Drought Monitor — {sid} (ρ = {res[sid]['spearman_spei90']})"
            )
            fig.legend(loc="upper left", fontsize=7)
            fig.tight_layout()
            fig.savefig(OUT / f"usdm_{sid}.png", dpi=110)
            plt.close(fig)
    return res


# --------------------------------------------------------------------------- 4. drought-year yield signal
def exp_yield_signal() -> dict[str, Any]:
    """Rain-fed maize at Ames 1985–2024: do documented drought years (1988, 2012) come out among the worst simulated seasons?"""
    from fieldshift.science.cropmodel import crop

    lat, lon = SITES["ames_ia"]
    ctx = build(lat, lon, AS_OF)
    years = list(range(1985, 2025))
    req = gdd_requirement(crop("maize"), ctx.weather, dt.date(2000, 5, 1), years)
    ys = {}
    for y in years:
        r = simulate(
            "maize", ctx.weather, dt.date(y, 5, 1), taw_per_m=ctx.taw_per_m, strategy="rainfed", gdd_req=req
        )
        ys[y] = r.yield_t_ha
    order = sorted(ys, key=lambda k: ys[k])
    out = {
        "simulated_yield_t_ha": ys,
        "rank_of_1988": order.index(1988) + 1,
        "rank_of_2012": order.index(2012) + 1,
        "n_years": len(years),
        "median": round(float(np.median(list(ys.values()))), 2),
    }
    # Kenya: documented drought seasons (short rains OND) 2016 and 2005 — FEWS NET / Kenya NDMA
    lat, lon = SITES["machakos_ke"]
    ctx = build(lat, lon, AS_OF)
    yk = {}
    reqk = gdd_requirement(crop("maize"), ctx.weather, dt.date(2000, 10, 20), list(range(1990, 2020)))
    for y in range(1990, 2024):
        r = simulate(
            "maize",
            ctx.weather,
            dt.date(y, 10, 20),
            taw_per_m=ctx.taw_per_m,
            strategy="rainfed",
            gdd_req=reqk,
        )
        yk[y] = r.yield_t_ha
    ok = sorted(yk, key=lambda k: yk[k])
    out["kenya_short_rains"] = {
        "simulated_yield_t_ha": yk,
        "rank_of_2016": ok.index(2016) + 1,
        "rank_of_2005": ok.index(2005) + 1,
        "n_years": len(yk),
    }
    return out


# --------------------------------------------------------------------------- 5. ET vs MODIS MOD16
def exp_mod16() -> dict[str, Any]:
    """Fully-irrigated alfalfa ET (season model) vs. MODIS MOD16A2GF annual ET at the Fallon pixel (500 m)."""
    lat, lon = SITES["fallon_nv"]
    ctx = build(lat, lon, AS_OF)
    try:
        series = sources.ornl_series(
            "mod16", lat, lon, dt.date(2015, 1, 1), dt.date(2023, 12, 31), max_requests=60
        )
    except DataUnavailable as e:
        return {"status": f"unavailable: {e}"}
    if not series:
        return {"status": "no MOD16 data returned (ORNL DAAC unavailable)"}
    annual: dict[int, float] = {}
    for d, v in series:
        annual[d.year] = annual.get(d.year, 0.0) + v
    model = {}
    for y in sorted(annual):
        r = simulate(
            "alfalfa",
            ctx.weather,
            dt.date(y, 3, 15),
            taw_per_m=ctx.taw_per_m,
            strategy="full",
            method="flood",
        )
        # add non-growing-season soil evaporation, approximated as Kc 0.3 × ET0 outside the season
        i0, i1 = ctx.idx(dt.date(y, 1, 1)), ctx.idx(dt.date(y, 12, 31)) + 1
        js, je = ctx.idx(r.start), ctx.idx(r.end)
        off = 0.3 * (np.nansum(ctx.weather.et0[i0:js]) + np.nansum(ctx.weather.et0[je + 1 : i1]))
        model[y] = r.et_mm + off
    a = np.array([model[y] for y in sorted(annual)])
    b = np.array([annual[y] for y in sorted(annual)])
    return {
        "years": sorted(annual),
        "model_mm": [round(x) for x in a],
        "mod16_mm": [round(x) for x in b],
        **metrics(a, b),
        "note": "MOD16 is known to underestimate ET of irrigated crops in arid regions (no irrigation input); see docs/VALIDATION.md.",
    }


# --------------------------------------------------------------------------- 6. late blight 2009
def exp_late_blight() -> dict[str, Any]:
    """Hutton-criteria days from NASA POWER hourly T/RH, Ithaca NY, 1 Jun–31 Aug, 2005–2015.
    2009 had a documented, region-wide late-blight epidemic in the U.S. Northeast (Fry et al. 2013, Plant Disease)."""
    lat, lon = 42.45, -76.48
    res = {}
    for y in range(2005, 2016):
        f = get_json(
            "https://power.larc.nasa.gov/api/temporal/hourly/point",
            {
                "parameters": "T2M,RH2M",
                "community": "AG",
                "latitude": lat,
                "longitude": lon,
                "start": f"{y}0601",
                "end": f"{y}0831",
                "format": "JSON",
                "time-standard": "LST",
            },
            ttl_s=365 * 86400,
            timeout_s=180,
        )
        p = f.data["properties"]["parameter"]
        keys = sorted(p["T2M"])
        hourly = {
            "time": [f"{k[:4]}-{k[4:6]}-{k[6:8]}T{k[8:10]}:00" for k in keys],
            "temperature_2m": [p["T2M"][k] if p["T2M"][k] > -998 else None for k in keys],
            "relative_humidity_2m": [p["RH2M"][k] if p["RH2M"][k] > -998 else None for k in keys],
        }
        sc = disease.daily_scores(disease.hourly_by_day(hourly))["late_blight"]
        res[y] = {
            "hutton_days": int(sum(1 for v in sc.values() if v >= 1.0)),
            "favourable_days": int(sum(1 for v in sc.values() if v >= 0.6)),
        }
    order = sorted(res, key=lambda k: -res[k]["hutton_days"])
    return {"site": "Ithaca, NY", "per_year": res, "rank_of_2009": order.index(2009) + 1, "n_years": len(res)}


EXPERIMENTS = {
    "et0": exp_et0,
    "soil": exp_soil_water,
    "usdm": exp_usdm,
    "yield": exp_yield_signal,
    "mod16": exp_mod16,
    "blight": exp_late_blight,
}


def main() -> None:
    want = sys.argv[1:] or list(EXPERIMENTS)
    path = OUT / "results.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    for k in want:
        print(f"== {k}", flush=True)
        try:
            results[k] = EXPERIMENTS[k]()
        except Exception as e:  # report failures honestly instead of hiding them
            results[k] = {"status": f"failed: {type(e).__name__}: {e}"}
        results[k + "_run_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        print(json.dumps(results[k], default=str)[:1500], flush=True)
        path.write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
