"""Season planner: sowing-date scan, expected stage dates, field-operations timeline, monthly water budget and
risk calendar for the coming season — all simulated over the last 15 seasons of NASA POWER weather."""

from __future__ import annotations

import datetime as dt
from statistics import median
from typing import Any

import numpy as np

from ..science import pests as pst
from ..science.cropmodel import IRRIGATION_EFFICIENCY, crop, gdd, gdd_requirement, simulate
from .context import build

STAGE_NAMES = ["Establishment complete", "Full canopy / flowering", "Start of ripening", "Maturity / harvest"]


def _next_occurrence(p: dt.date, today: dt.date) -> dt.date:
    d = dt.date(today.year, p.month, min(p.day, 28))
    return d if d >= today - dt.timedelta(days=14) else dt.date(today.year + 1, p.month, min(p.day, 28))


def planner_api(req: dict[str, Any]) -> dict[str, Any]:
    lat, lon = float(req["lat"]), float(req["lon"])
    today = dt.date.fromisoformat(req["as_of"]) if req.get("as_of") else dt.date.today()
    ctx = build(lat, lon, today)
    w = ctx.weather
    cid = req["crop"]
    c = crop(cid)
    method = req.get("irrigation", "sprinkler")
    irrigated = method != "none"
    alloc = req.get("water_allocation_mm")
    strategy = "allocation" if (irrigated and alloc) else ("full" if irrigated else "rainfed")
    p_in = dt.date.fromisoformat(req["planting_date"])
    p_next = _next_occurrence(p_in, today)
    last = today.year - (2 if p_in.month >= 8 else 1)
    years = list(range(last - 14, last + 1))
    perennial = c["type"] == "perennial"
    eff = IRRIGATION_EFFICIENCY.get(method, 0.75) if irrigated else 1.0

    def run(p_md: dt.date, record: bool) -> list[Any]:
        req_gdd = gdd_requirement(c, w, p_md, years)
        out = []
        for y in years:
            try:
                p = dt.date(y, p_md.month, min(p_md.day, 28))
                out.append(
                    simulate(
                        cid,
                        w,
                        p,
                        taw_per_m=ctx.taw_per_m,
                        strategy=strategy,
                        method=method,
                        allocation_mm=alloc,
                        gdd_req=req_gdd,
                        record_daily=record,
                    )
                )
            except (ValueError, IndexError):
                continue
        return out

    # ---- sowing-date scan (annuals)
    scan: list[dict[str, Any]] = []
    window = None
    if not perennial:
        for k in range(-6, 7):
            p = p_next + dt.timedelta(days=7 * k)
            res = run(p, False)
            if len(res) < 8:
                continue
            ys = np.array([r.yield_t_ha for r in res])
            scan.append(
                {
                    "date": p.isoformat(),
                    "yield_median": round(float(np.median(ys)), 2),
                    "yield_p10": round(float(np.percentile(ys, 10)), 2),
                    "irrigation_median_mm": round(float(np.median([r.irrigation_mm for r in res]))),
                    "frost_risk_pct": round(100 * float(np.mean([r.frost_events > 0 for r in res]))),
                    "heat_days_median": round(float(np.median([r.heat_days for r in res])), 1),
                    "score": round(float(np.median(ys) - 0.5 * (np.median(ys) - np.percentile(ys, 10))), 3),
                }
            )
        if scan:
            best = max(scan, key=lambda s: s["score"])
            good = [s for s in scan if s["score"] >= 0.97 * best["score"]]
            ws, we = min(s["date"] for s in good), max(s["date"] for s in good)
            window = {
                "start": ws,
                "end": max(we, (dt.date.fromisoformat(ws) + dt.timedelta(days=7)).isoformat()),
                "best": best["date"],
            }

    # ---- chosen date: stages, water budget, events
    runs = run(p_next, True)
    stage_offsets: list[list[int]] = [[] for _ in STAGE_NAMES]
    cut_offsets: list[list[int]] = []
    monthly: dict[int, dict[str, list[float]]] = {}
    req_gdd = gdd_requirement(c, w, p_next, years)
    for r in runs:
        if not r.daily:
            continue
        days = [dt.date.fromisoformat(x) for x in r.daily["date"]]
        if perennial:
            cut_offsets.append(
                [(dt.date.fromisoformat(e["date"]) - r.start).days for e in r.events if e["type"] == "cut"]
            )
        else:
            i0 = w.index(r.start)
            g = np.cumsum(gdd(w.tmax[i0 : i0 + len(days)], w.tmin[i0 : i0 + len(days)], c["t_base"]))
            s = np.array(c["stages"], float)
            fr = np.cumsum(s) / s.sum()
            for k, f in enumerate(fr):
                idx = int(np.searchsorted(g, f * req_gdd))
                if idx < len(days):
                    stage_offsets[k].append(idx)
        per_year: dict[int, dict[str, float]] = {}
        for k, d in enumerate(days):
            acc_m = per_year.setdefault(
                d.month, {"et0": 0.0, "etc": 0.0, "eta": 0.0, "rain": 0.0, "irr": 0.0}
            )
            i = w.index(d)
            acc_m["et0"] += float(w.et0[i]) if np.isfinite(w.et0[i]) else 0.0
            acc_m["etc"] += r.daily["etc"][k]
            acc_m["eta"] += r.daily["eta"][k]
            acc_m["rain"] += r.daily["rain"][k]
            acc_m["irr"] += r.daily["irr"][k]
        for mth, vals in per_year.items():
            agg = monthly.setdefault(mth, {kk: [] for kk in vals})
            for kk, v in vals.items():
                agg[kk].append(v)
    month_order = sorted(monthly, key=lambda m: (m - p_next.month) % 12)
    budget = [
        {"month": m, **{k: round(float(median(v)), 1) for k, v in monthly[m].items()}} for m in month_order
    ]
    season_irr = float(median([r.irrigation_mm for r in runs])) if runs else 0.0
    full_need = season_irr
    if strategy == "allocation":
        req_full = gdd_requirement(c, w, p_next, years)
        full_runs = []
        for y in years:
            try:
                full_runs.append(
                    simulate(
                        cid,
                        w,
                        dt.date(y, p_next.month, min(p_next.day, 28)),
                        taw_per_m=ctx.taw_per_m,
                        strategy="full",
                        method=method,
                        gdd_req=req_full,
                    ).irrigation_mm
                )
            except (ValueError, IndexError):
                continue
        full_need = float(median(full_runs)) if full_runs else season_irr

    stages: list[dict[str, Any]] = []
    if perennial and cut_offsets:
        n_cuts = int(median([len(co) for co in cut_offsets]))
        for k in range(n_cuts):
            offs = [co[k] for co in cut_offsets if len(co) > k]
            if offs:
                stages.append(
                    {
                        "label": f"Cutting {k + 1}",
                        "date": (p_next + dt.timedelta(days=int(median(offs)))).isoformat(),
                        "spread_days": int(np.percentile(offs, 90) - np.percentile(offs, 10))
                        if len(offs) > 2
                        else 0,
                    }
                )
    else:
        for name, offs in zip(STAGE_NAMES, stage_offsets, strict=True):
            if offs:
                stages.append(
                    {
                        "label": name,
                        "date": (p_next + dt.timedelta(days=int(median(offs)))).isoformat(),
                        "spread_days": int(np.percentile(offs, 90) - np.percentile(offs, 10)),
                    }
                )

    # ---- pest scouting dates (median over years, degree-days from the calendar biofix or sowing)
    ops: list[dict[str, Any]] = [
        {
            "date": p_next.isoformat(),
            "label": "Green-up / first irrigation check" if perennial else "Sowing",
            "kind": "sow",
        }
    ]
    for stg in stages:
        ops.append(
            {
                "date": stg["date"],
                "label": stg["label"],
                "kind": "harvest" if ("Maturity" in stg["label"] or "Cutting" in stg["label"]) else "stage",
            }
        )
    for pid, pest in pst.PESTS.items():
        if cid not in pest["crops"] or not pst.present(pid, lat, lon):
            continue
        for dd_ev, label, action in pest["events"][:2]:
            offs = []
            for y in years:
                bf = pst.biofix(dt.date(y, p_next.month, min(p_next.day, 28)), lat)
                if not perennial:
                    bf = max(bf, dt.date(y, p_next.month, min(p_next.day, 28)))
                i0 = w.index(bf)
                if i0 < 0 or i0 + 300 > len(w.dates):
                    continue
                acc = np.cumsum(
                    pst.degree_days(
                        w.tmax[i0 : i0 + 300], w.tmin[i0 : i0 + 300], pest["t_low"], pest["t_high"]
                    )
                )
                k = int(np.searchsorted(acc, dd_ev))
                if k < 300:
                    offs.append((bf - dt.date(y, p_next.month, min(p_next.day, 28))).days + k)
            if len(offs) >= 5:
                ops.append(
                    {
                        "date": (p_next + dt.timedelta(days=int(median(offs)))).isoformat(),
                        "label": f"{pest['name']}: {label.lower()} — {action}",
                        "kind": "scout",
                    }
                )
    if budget and irrigated:
        peak = max(budget, key=lambda b: b["irr"])
        if peak["irr"] > 0:
            ops.append(
                {
                    "date": dt.date(
                        p_next.year + (1 if peak["month"] < p_next.month else 0), int(peak["month"]), 1
                    ).isoformat(),
                    "label": f"Peak irrigation month: ~{peak['irr']:.0f} mm",
                    "kind": "water",
                }
            )
    ops.sort(key=lambda o: o["date"])

    # ---- risk calendar from weather history (season months)
    risk_cal = []
    ys_idx = np.array([d.year for d in w.dates])
    ms_idx = np.array([d.month for d in w.dates])
    for m in month_order:
        frost_p = heat_p = 0.0
        n = 0
        for y in years:
            sel = (ys_idx == y) & (ms_idx == m)
            if sel.sum() < 20:
                continue
            n += 1
            frost_p += float(np.nanmin(w.tmin[sel]) <= c.get("t_kill_spring", c["t_kill"]))
            heat_p += float(np.nansum(w.tmax[sel] >= c["t_heat"]) >= 3)
        if n:
            risk_cal.append(
                {"month": m, "frost_pct": round(100 * frost_p / n), "heat_pct": round(100 * heat_p / n)}
            )

    water = {
        "season_irrigation_median_mm": round(season_irr),
        "full_need_median_mm": round(full_need),
        "allocation_mm": alloc,
        "coverage_pct": round(100 * min(1.0, alloc / full_need)) if (alloc and full_need > 0) else None,
        "efficiency": eff,
        "note": (
            f"Your allocation covers ~{round(100 * min(1.0, alloc / full_need))} % of the full-irrigation need ({round(full_need)} mm); "
            "plan deficit irrigation, a split season, or a shorter-season crop."
            if alloc and full_need > 0 and alloc < full_need
            else None
        ),
    }
    return {
        "crop": cid,
        "season_start": p_next.isoformat(),
        "years": [years[0], years[-1]],
        "sowing_scan": scan,
        "window": window,
        "stages": stages,
        "operations": ops,
        "water_budget": budget,
        "water": water,
        "risk_calendar": risk_cal,
        "why": (
            "Every number here comes from re-running the FieldShift season model for each of the last 15 seasons of NASA POWER weather "
            "at your field: dates are medians, 'spread' is the 10–90 % range between years."
        ),
        "sources": ["nasa_power", "soilgrids", "srtm"],
    }
