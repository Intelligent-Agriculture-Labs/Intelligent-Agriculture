"""V9 validation: rainy-season onset/cessation from NASA POWER vs. published onset climatologies.

    backend/.venv/bin/python scripts/validate_onset.py          # fetches POWER (cached), writes JSON + table
    backend/.venv/bin/python scripts/validate_onset.py --report # only print the markdown from the saved JSON

Writes docs/validation/onset_results.json and prints the markdown section for docs/VALIDATION.md (V9).
References were read in the original sources (URLs in REFS); the detector settings are the production
defaults in backend/fieldshift/config/onset.yaml, declared before this script was first run. Like-for-like
variants (the reference study's own thresholds) are reported separately and never feed back into the defaults.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldshift.data import sources  # noqa: E402
from fieldshift.science import et0 as et0mod  # noqa: E402
from fieldshift.science import onset as on  # noqa: E402

OUT = ROOT / "docs" / "validation"
START, END = dt.date(1984, 1, 1), dt.date(2025, 10, 31)

REFS = {
    "imd_mok": "IMD onset over Kerala: Pai & Rajeevan (2009) J. Earth Syst. Sci. 118:123–135, Table 1 ('new' 2006 criteria, 1984–2007); "
    "IMD press releases 24 May 2025 (Annexure 2, 2009–2025) and 15 May 2020; 2008 from a secondary copy of the IMD table.",
    "imd_normals": "IMD new normal onset dates 1961–2019: Pai et al. (2020) IMD CRS Research Report 3/2020, Table 2 "
    "(https://internal.imd.gov.in/press_release/20200515_pr_804.pdf).",
    "sivakumar": "Sivakumar (1988) Agric. For. Meteorol. 42:295–305: mean onset Niamey 12 Jun (1904–1984); mean length of "
    "the growing season per station, Tables I–II (end = first date after 1 Sep followed by 20 days without rain).",
    "omoyo": "Omoyo, Wakhungu & Oteng'i (2015) Agric. & Food Security 4:8, Machakos station 1979–2009 (Instat): mean onset "
    "7 Apr (MAM) and 28 Oct (OND; the text also says 10 Oct). Criterion: ≥ 20 mm in 3 days, no 10-day dry spell in 30 days, "
    "rain day ≥ 4.95 mm.",
    "bom": "Bureau of Meteorology, northern rainfall onset (50 mm accumulated after 1 Sep), "
    "https://www.bom.gov.au/climate/rainfall-onset/: the western Top End usually reaches it by late October or early November.",
}

# IMD monsoon onset over Kerala (2006 criteria throughout; see REFS["imd_mok"])
MOK = {
    1984: (6, 1), 1985: (5, 24), 1986: (6, 12), 1987: (6, 1), 1988: (6, 2), 1989: (6, 4), 1990: (5, 18),
    1991: (6, 2), 1992: (6, 5), 1993: (6, 3), 1994: (5, 28), 1995: (6, 10), 1996: (6, 9), 1997: (6, 12),
    1998: (6, 3), 1999: (5, 22), 2000: (6, 1), 2001: (5, 26), 2002: (6, 9), 2003: (6, 13), 2004: (6, 3),
    2005: (6, 7), 2006: (5, 26), 2007: (5, 28), 2008: (5, 31), 2009: (5, 23), 2010: (5, 31), 2011: (5, 29),
    2012: (6, 5), 2013: (6, 1), 2014: (6, 6), 2015: (6, 5), 2016: (6, 8), 2017: (5, 30), 2018: (5, 29),
    2019: (6, 8), 2020: (6, 1), 2021: (6, 3), 2022: (5, 29), 2023: (6, 8), 2024: (5, 30), 2025: (5, 24),
}  # fmt: skip
KERALA = {"Thiruvananthapuram": (8.48, 76.95), "Kochi": (9.97, 76.28), "Kozhikode": (11.26, 75.78)}
IMD_NORMALS = {  # city: (lat, lon, new normal onset 1961–2019)
    "Mumbai": (19.08, 72.88, (6, 11)),
    "Pune": (18.52, 73.86, (6, 10)),
    "Nagpur": (21.15, 79.09, (6, 16)),
    "Bhopal": (23.26, 77.41, (6, 20)),
    "Ahmedabad": (23.03, 72.58, (6, 26)),
    "Jaipur": (26.91, 75.79, (6, 29)),
    "Delhi": (28.61, 77.21, (6, 27)),
    "Patna": (25.59, 85.14, (6, 16)),
    "Varanasi": (25.32, 82.97, (6, 23)),
}
SAHEL_LGP = {  # station: (lat, lon, Sivakumar 1988 mean growing-season length, days)
    "Niamey": (13.48, 2.17, 94),
    "Ayorou": (14.73, 0.92, 67),
    "Birni N'Konni": (13.80, 5.25, 93),
    "Dosso": (13.05, 3.19, 99),
    "Maradi": (13.50, 7.10, 86),
    "Tahoua": (14.89, 5.26, 76),
    "Zinder": (13.80, 8.99, 80),
    "Tillabery": (14.21, 1.45, 81),
    "Say": (13.10, 2.37, 98),
    "Djibo": (14.10, -1.63, 83),
    "Dori": (14.03, -0.03, 85),
    "Markoye": (14.65, 0.04, 76),
    "Ouagadougou": (12.37, -1.53, 117),
    "Fada N'Gourma": (12.06, 0.36, 120),
    "Kaya": (13.09, -1.08, 107),
    "Po": (11.17, -1.15, 125),
    "Leo": (11.10, -2.10, 129),
}
MACHAKOS = (-1.517, 37.263)
DARWIN = (-12.42, 130.89)


def load(lat: float, lon: float) -> tuple[list[dt.date], np.ndarray, np.ndarray]:
    p = sources.power_daily(lat, lon, START, END)
    doy = np.array([d.timetuple().tm_yday for d in p.dates])
    elev = p.meta.get("power_elevation_m") or 0.0
    et0 = et0mod.et0_pm(
        p["T2M_MAX"], p["T2M_MIN"], p["ALLSKY_SFC_SW_DWN"], p["WS2M"], lat, elev, doy, tdew=p["T2MDEW"]
    )
    et0 = np.where(np.isfinite(et0), et0, et0mod.et0_hargreaves(p["T2M_MAX"], p["T2M_MIN"], lat, doy))
    return list(p.dates), np.nan_to_num(p["PRECTOTCORR"]), et0


def doy_of(d: dt.date) -> int:
    return (dt.date(2001, d.month, d.day) - dt.date(2001, 1, 1)).days + 1


def md(doy: float) -> str:
    return (dt.date(2001, 1, 1) + dt.timedelta(days=round(doy) - 1)).strftime("%d %b")


def season_near(site: on.SiteClimatology, month: int) -> on.SeasonClimatology:
    """The detected season whose climatological onset is closest to ``month``."""
    target = (dt.date(2001, month, 15) - dt.date(2001, 1, 1)).days
    return min(
        site.seasons,
        key=lambda s: min((s.season.onset_doy - target) % 365, (target - s.season.onset_doy) % 365),
    )


def onset_doys(sc: on.SeasonClimatology, y0: int = 1984, y1: int = 2025) -> dict[int, int]:
    """Onset day of year per season year (onsets in the next calendar year counted beyond 365)."""
    out = {}
    for y in sc.years:
        if y.onset and y0 <= y.year <= y1:
            out[y.year] = (
                (y.onset - dt.date(y.year, 1, 1)).days
                + 1
                - (1 if y.onset.year % 4 == 0 and y.onset.month > 2 else 0)
            )
    return out


def sivakumar_end(
    dates: list[dt.date], rain: np.ndarray, onset: dt.date, crit: on.Criteria
) -> dt.date | None:
    """Sivakumar (1988) end of rains: first date after 1 Sep followed by 20 days without rain (< dry-day threshold)."""
    i = max((dt.date(onset.year, 9, 1) - dates[0]).days, (onset - dates[0]).days)
    while i + 20 < len(rain):
        if rain[i] >= crit.dry_day_mm and np.all(rain[i + 1 : i + 21] < crit.dry_day_mm):
            return dates[i]
        i += 1
    return None


def err_stats(ours: list[float], ref: list[float]) -> dict[str, Any]:
    e = np.array(ours) - np.array(ref)
    out: dict[str, Any] = {
        "n": int(len(e)),
        "bias_days": round(float(e.mean()), 1),
        "mae_days": round(float(np.abs(e).mean()), 1),
        "median_abs_err_days": round(float(np.median(np.abs(e))), 1),
        "within_10d_pct": round(100 * float(np.mean(np.abs(e) <= 10))),
    }
    if len(e) > 5 and np.std(ours) > 0 and np.std(ref) > 0:
        r, p = stats.pearsonr(ours, ref)
        out["r"], out["p"] = round(float(r), 2), round(float(p), 3)
    return out


def main() -> None:
    crit = on.Criteria.from_config()
    res: dict[str, Any] = {
        "run": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "criteria": dataclasses.asdict(crit),
        "refs": REFS,
    }

    # ---- 1. Kerala: per-year onset vs IMD
    kerala = {}
    for name, (lat, lon) in KERALA.items():
        d, r, e = load(lat, lon)
        site = on.site_climatology(d, r, e, lat)
        sc = season_near(site, 6)
        ours = onset_doys(sc)
        yrs = sorted(set(ours) & set(MOK))
        ref = [doy_of(dt.date(2001, *MOK[y])) for y in yrs]
        o = [ours[y] for y in yrs]
        kerala[name] = {
            "lat": lat, "lon": lon, "season": sc.season.label, "regime": site.info["regime"],
            "years_detected": len(yrs), "years_ref": len([y for y in MOK if 1984 <= y <= 2025]),
            "median_ours": md(float(np.median(o))), "median_imd": md(float(np.median(ref))),
            **err_stats(o, ref),
            "per_year": {y: [md(ours[y]), md(doy_of(dt.date(2001, *MOK[y])))] for y in yrs},
        }  # fmt: skip
    res["kerala"] = kerala

    # ---- 2. IMD normal onset dates of 9 cities (climatology vs climatology)
    cities = {}
    for name, (lat, lon, mmdd) in IMD_NORMALS.items():
        d, r, e = load(lat, lon)
        site = on.site_climatology(d, r, e, lat)
        sc = season_near(site, 6)
        o = list(onset_doys(sc).values())
        ref = doy_of(dt.date(2001, *mmdd))
        cities[name] = {
            "lat": lat, "lon": lon, "season": sc.season.label, "applicable": site.applicable, "n": len(o),
            "median_ours": md(float(np.median(o))), "normal_imd": md(ref),
            "error_days": round(float(np.median(o)) - ref), "false_start_pct": sc.false_start_pct(),
        }  # fmt: skip
    errs = [c["error_days"] for c in cities.values()]
    res["imd_normals"] = {
        "cities": cities,
        "bias_days": round(float(np.mean(errs)), 1),
        "mae_days": round(float(np.mean(np.abs(errs))), 1),
        "r_across_cities": round(float(stats.pearsonr(
            [doy_of(dt.date(2001, *v[2])) for v in IMD_NORMALS.values()],
            [doy_of(dt.date(2001, *v[2])) + c["error_days"] for v, c in zip(IMD_NORMALS.values(), cities.values(), strict=True)],
        )[0]), 2),
    }  # fmt: skip

    # ---- 3. Sahel (Sivakumar 1988): Niamey mean onset; season length at 17 stations
    sahel = {}
    for name, (lat, lon, lgp) in SAHEL_LGP.items():
        d, r, e = load(lat, lon)
        site = on.site_climatology(d, r, e, lat)
        sc = season_near(site, 7)
        yrs = [y for y in sc.years if y.onset]
        ends = [sivakumar_end(d, r, y.onset, crit) for y in yrs]
        len_siv = [(en - y.onset).days for y, en in zip(yrs, ends, strict=True) if en]
        o = list(onset_doys(sc).values())
        sahel[name] = {
            "lat": lat, "lon": lon, "season": sc.season.label, "n": len(o),
            "mean_onset": md(float(np.mean(o))), "sd_onset_days": round(float(np.std(o)), 1),
            "failed_pct": sc.failed_pct(), "false_start_pct": sc.false_start_pct(),
            "lgp_ref": lgp,
            "lgp_ours_sivakumar_end": round(float(np.mean(len_siv)), 1) if len_siv else None,
            "lgp_ours_water_balance": round(float(np.mean(sc.lengths)), 1) if sc.lengths else None,
        }  # fmt: skip
    nia = sahel["Niamey"]
    nia["onset_ref"] = "12 Jun"
    nia["onset_error_days"] = round(
        float(np.mean(list(onset_doys(season_near(on.site_climatology(*load(13.48, 2.17), 13.48), 7)).values())))
        - doy_of(dt.date(2001, 6, 12)), 1
    )  # fmt: skip
    ls = [(s["lgp_ours_sivakumar_end"], s["lgp_ref"]) for s in sahel.values() if s["lgp_ours_sivakumar_end"]]
    lw = [(s["lgp_ours_water_balance"], s["lgp_ref"]) for s in sahel.values() if s["lgp_ours_water_balance"]]
    res["sahel"] = {
        "stations": sahel,
        "lgp_sivakumar_end": err_stats([a for a, _ in ls], [b for _, b in ls]),
        "lgp_water_balance": err_stats([a for a, _ in lw], [b for _, b in lw]),
    }

    # ---- 4. Machakos (Omoyo et al. 2015, station 1979–2009): production defaults and the study's own thresholds
    d, r, e = load(*MACHAKOS)
    mach = {}
    for variant, c in (
        ("default", crit),
        ("omoyo_thresholds", dataclasses.replace(crit, dry_day_mm=4.95, max_dry_spell_days=9)),
    ):
        site = on.site_climatology(d, r, e, MACHAKOS[0], crit=c)
        for key, month, ref in (("MAM", 3, (4, 7)), ("OND", 10, (10, 28))):
            sc = season_near(site, month)
            o = list(onset_doys(sc, 1984, 2009).values())
            mach[f"{variant}:{key}"] = {
                "season": sc.season.label, "n": len(o), "mean_onset": md(float(np.mean(o))),
                "ref_mean_onset": md(doy_of(dt.date(2001, *ref))),
                "error_days": round(float(np.mean(o)) - doy_of(dt.date(2001, *ref)), 1),
                "failed_pct_1984_2009": round(100 * float(np.mean([y.onset is None for y in sc.years if 1984 <= y.year <= 2009])), 1),
            }  # fmt: skip
    mach["regime"] = on.site_climatology(d, r, e, MACHAKOS[0]).info["regime"]
    res["machakos"] = mach

    # ---- 5. Darwin (BoM): agronomic onset and the BoM 50 mm rule, both from POWER
    d, r, e = load(*DARWIN)
    site = on.site_climatology(d, r, e, DARWIN[0])
    sc = season_near(site, 11)
    o = [((y.onset - dt.date(y.year, 9, 1)).days) for y in sc.years if y.onset]
    bom = []
    for y in range(1984, 2025):
        i0 = (dt.date(y, 9, 1) - d[0]).days
        cs = np.cumsum(r[i0 : i0 + 240])
        k = int(np.searchsorted(cs, 50.0))
        if k < 240:
            bom.append(k)
    sep1 = doy_of(dt.date(2001, 9, 1))
    res["darwin"] = {
        "season": sc.season.label, "regime": site.info["regime"], "n": len(o),
        "median_onset_ours": md(sep1 + float(np.median(o))),
        "median_onset_bom_rule_power": md(sep1 + float(np.median(bom))),
        "ref": "late Oct – early Nov",
        "error_days_vs_1_nov": round(sep1 + float(np.median(o)) - doy_of(dt.date(2001, 11, 1))),
        "bom_rule_error_days_vs_1_nov": round(sep1 + float(np.median(bom)) - doy_of(dt.date(2001, 11, 1))),
        "false_start_pct": sc.false_start_pct(),
    }  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "onset_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    print(
        json.dumps(
            {k: v for k, v in res.items() if k not in ("refs",)}, indent=1, ensure_ascii=False, default=str
        )[:20000]
    )


def report(res: dict[str, Any]) -> str:
    """Markdown tables for docs/VALIDATION.md (V9) from the results JSON."""
    L = [f"_run: {res['run']} · NASA POWER daily 1984–2025 · production criteria (config/onset.yaml)_", ""]
    k = res["imd_normals"]
    L += [
        "**(a) India, 9 cities: median onset vs. IMD new normal onset date (1961–2019)**",
        "",
        "| City | lat, lon | Season | FieldShift median onset | IMD normal | Error (days) | False starts |",
        "|---|---|---|---|---|---|---|",
    ]
    for n, c in k["cities"].items():
        L.append(
            f"| {n} | {c['lat']}, {c['lon']} | {c['season']} | {c['median_ours']} | {c['normal_imd']} | {c['error_days']:+d} | {c['false_start_pct']:.0f} % |"
        )
    L += [
        "",
        f"Bias {k['bias_days']:+.1f} days, **MAE {k['mae_days']} days**, r = {k['r_across_cities']} across cities.",
        "",
    ]
    L += [
        "**(b) Kerala: per-year onset vs. IMD monsoon onset over Kerala (1984–2025)**",
        "",
        "| Site | n years | FieldShift median | IMD median | Bias (days) | MAE (days) | within ±10 d | r |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for n, c in res["kerala"].items():
        L.append(
            f"| {n} | {c['n']} | {c['median_ours']} | {c['median_imd']} | {c['bias_days']:+.1f} | {c['mae_days']} | {c['within_10d_pct']} % | {c.get('r', '–')} |"
        )
    sa = res["sahel"]
    nia = sa["stations"]["Niamey"]
    L += [
        "",
        "**(c) West African Sahel / Sudan zone vs. Sivakumar (1988), Niger and Burkina Faso**",
        "",
        f"Niamey mean onset: FieldShift {nia['mean_onset']} (1984–2025) vs. Sivakumar 12 Jun (1904–1984): **{nia['onset_error_days']:+.0f} days**.",
        "",
        "| Station | Mean onset | SD (days) | False starts | Failed | Length, Sivakumar | Length, FieldShift (water balance) | Length, FieldShift (Sivakumar's end rule) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for n, c in sa["stations"].items():
        L.append(
            f"| {n} | {c['mean_onset']} | {c['sd_onset_days']} | {c['false_start_pct']:.0f} % | {c['failed_pct']:.0f} % | {c['lgp_ref']} | {c['lgp_ours_water_balance']} | {c['lgp_ours_sivakumar_end']} |"
        )
    wb, se = sa["lgp_water_balance"], sa["lgp_sivakumar_end"]
    L += [
        "",
        f"Season length over {wb['n']} stations: water balance (used in the app) bias {wb['bias_days']:+.1f} days, **MAE {wb['mae_days']} days**, r = {wb['r']}; "
        f"Sivakumar's end rule on POWER rain: bias {se['bias_days']:+.1f}, MAE {se['mae_days']} days, r = {se['r']}.",
        "",
        "**(d) Kenya, Machakos (bimodal) vs. Omoyo et al. (2015), Machakos station 1979–2009; FieldShift 1984–2009**",
        "",
        "| Season | Criteria | n | FieldShift mean onset | Reference mean onset | Error (days) | Failed seasons |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, c in res["machakos"].items():
        if ":" not in key:
            continue
        v, s_ = key.split(":")
        L.append(
            f"| {s_} | {'production' if v == 'default' else 'study thresholds (≥ 4.95 mm rain day, 10-day spell)'} | {c['n']} | {c['mean_onset']} | {c['ref_mean_onset']} | {c['error_days']:+.1f} | {c['failed_pct_1984_2009']:.0f} % |"
        )
    dw = res["darwin"]
    L += [
        "",
        "**(e) Australia, Darwin (southern hemisphere, season across New Year) vs. Bureau of Meteorology**",
        "",
        f"FieldShift median onset {dw['median_onset_ours']} ({dw['season']}, n = {dw['n']}); BoM's 50 mm rule computed on the same POWER rain: "
        f"{dw['median_onset_bom_rule_power']}; BoM: the western Top End usually reaches onset by late October or early November. "
        f"Error vs. 1 Nov: **{dw['error_days_vs_1_nov']:+d} days**.",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    if "--report" in sys.argv:
        print(report(json.loads((OUT / "onset_results.json").read_text())))
    else:
        main()
