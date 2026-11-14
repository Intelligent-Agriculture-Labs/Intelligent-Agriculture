"""Asynchronous field satellite analysis: Sentinel-2 NDVI time series, phenology, AI management zones, satellite Kcb.

POST /api/satellite starts (or returns) a job keyed by field geometry + date range. Results are cached on disk
(JSON + PNGs) so repeated requests and offline demos are instant.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..data import dem as demmod
from ..data import sentinel
from ..data.http import CACHE_DIR, DEMO_DIR
from ..science import satellite as sat
from ..science import terrain
from ..science.cropmodel import crop

log = logging.getLogger("fieldshift.satellite")
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sat-job")
_read_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="sat-read")
MAX_SCENES = 24


def _dir() -> Path:
    d = CACHE_DIR / "satellite"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key(req: dict[str, Any], start: dt.date, end: dt.date) -> str:
    geom = req.get("polygon") or [round(float(req["lat"]), 4), round(float(req["lon"]), 4)]
    return hashlib.sha256(
        json.dumps([geom, start.isoformat(), end.isoformat(), req.get("crop")], default=str).encode()
    ).hexdigest()[:20]


def png_path(key: str, name: str) -> Path | None:
    for d in (_dir(), DEMO_DIR / "satellite"):
        p = d / f"{key}_{name}.png"
        if p.exists():
            return p
    return None


def _cached(key: str) -> dict[str, Any] | None:
    for d in (_dir(), DEMO_DIR / "satellite"):
        p = d / f"{key}.json"
        if p.exists():
            try:
                return json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                return None
    return None


def satellite_api(req: dict[str, Any]) -> dict[str, Any]:
    end = dt.date.fromisoformat(req["end"]) if req.get("end") else dt.date.today()
    end = end - dt.timedelta(days=end.weekday())  # week granularity -> stable cache key within a week
    start = dt.date.fromisoformat(req["start"]) if req.get("start") else end - dt.timedelta(days=365)
    key = _key(req, start, end)
    hit = _cached(key)
    if hit:
        return hit
    with _lock:
        job = _jobs.get(key)
        if job is None or job["status"] == "error" and job.get("retry", True):
            job = {"status": "processing", "progress": 0.02, "message": "Searching Sentinel-2 archive…"}
            _jobs[key] = job
            _pool.submit(_run, key, req, start, end)
    return {
        "status": job["status"],
        "progress": round(job["progress"], 2),
        "message": job.get("message"),
        "field_key": key,
    }


def _set(key: str, **kw: Any) -> None:
    with _lock:
        _jobs[key].update(kw)


def _rgba_png(rgba: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _ndvi_rgba(v: np.ndarray, mask: np.ndarray) -> np.ndarray:
    stops = [
        (-0.1, (165, 0, 38)),
        (0.15, (244, 109, 67)),
        (0.3, (254, 224, 139)),
        (0.5, (166, 217, 106)),
        (0.8, (26, 152, 80)),
        (1.0, (0, 104, 55)),
    ]
    xs = [s[0] for s in stops]
    out = np.zeros(v.shape + (4,), dtype=np.uint8)
    vv = np.nan_to_num(v, nan=-0.1)
    for ch in range(3):
        out[..., ch] = np.interp(vv, xs, [s[1][ch] for s in stops]).astype(np.uint8)
    out[..., 3] = np.where(np.isfinite(v), np.where(mask, 230, 120), 0)
    return out


def _run(key: str, req: dict[str, Any], start: dt.date, end: dt.date) -> None:
    try:
        _analyse(key, req, start, end)
    except Exception as e:  # report to client, keep the server alive
        log.exception("satellite job failed")
        _set(key, status="error", message=f"{type(e).__name__}: {e}", progress=1.0)


def _analyse(key: str, req: dict[str, Any], start: dt.date, end: dt.date) -> None:
    lat, lon = float(req["lat"]), float(req["lon"])
    poly = req.get("polygon")
    grid = sentinel.field_grid(lat, lon, poly)
    scenes = sentinel.search(grid, start, end)
    if not scenes:
        _set(
            key,
            status="error",
            message="No Sentinel-2 scenes found for this field and period.",
            progress=1.0,
            retry=False,
        )
        return
    # spread the selection over the period, preferring clear scenes
    clear = sorted(scenes, key=lambda s: s["cloud_pct"])
    if len(scenes) > MAX_SCENES:
        bins: dict[int, dict[str, Any]] = {}
        span = max(1, (end - start).days)
        for s in clear:
            b = int((dt.date.fromisoformat(s["date"]) - start).days / span * MAX_SCENES)
            bins.setdefault(b, s)
        chosen = sorted(bins.values(), key=lambda s: s["date"])
    else:
        chosen = scenes
    _set(key, progress=0.08, message=f"Reading {len(chosen)} Sentinel-2 scenes of your field (10 m)…")

    # field mask on the grid
    h, w = grid["h"], grid["w"]
    yy, xx = np.mgrid[0:h, 0:w]
    if poly and len(poly) >= 3:
        pts = []
        for p in poly:
            mx, my = sentinel.merc(p[0], p[1])
            pts.append(((mx - grid["x0"]) / grid["px"], (grid["y1"] - my) / grid["px"]))
        mask = terrain.polygon_mask((h, w), pts)
    else:
        cx, cy = sentinel.merc(lon, lat)
        px_c, py_c = (cx - grid["x0"]) / grid["px"], (grid["y1"] - cy) / grid["px"]
        mask = np.hypot(xx + 0.5 - px_c, yy + 0.5 - py_c) * 10.0 <= 150
    if mask.sum() < 4:
        mask[h // 2, w // 2] = True

    done = [0]

    def read(sc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, np.ndarray] | None]:
        try:
            r = sentinel.read_scene(sc, grid)
        except Exception as e:  # one bad scene must not kill the job
            log.warning("scene %s failed: %s", sc["id"], e)
            r = None
        done[0] += 1
        _set(key, progress=0.08 + 0.75 * done[0] / len(chosen))
        return sc, r

    stack, recs = [], []
    for sc, r in _read_pool.map(read, chosen):
        if r is None:
            continue
        nd = sat.ndvi(r["red"], r["nir"])
        valid = (
            np.isin(r["scl"], sat.VALID_SCL) & np.isfinite(nd) & (r["red"] > 0.002) & (r["nir"] > 0.02)
        )  # physical reflectance only
        nd = np.where(valid, nd, np.nan)
        vf = float(valid[mask].mean())
        f = nd[mask]
        good = vf >= 0.6 and np.isfinite(f).any()
        recs.append(
            {
                "id": sc["id"],
                "date": sc["date"],
                "cloud_pct": sc["cloud_pct"],
                "valid_pct": round(100 * vf, 1),
                "ndvi_mean": round(float(np.nanmean(f)), 3) if good else None,
                "ndvi_p10": round(float(np.nanpercentile(f, 10)), 3) if good else None,
                "ndvi_p90": round(float(np.nanpercentile(f, 90)), 3) if good else None,
                "_scene": sc,
            }
        )
        if good:
            stack.append(nd)
    if not recs:
        _set(key, status="error", message="Sentinel-2 images could not be read (network).", progress=1.0)
        return
    _set(key, progress=0.86, message="Detecting crop phenology and computing AI management zones…")
    good_recs = [r for r in recs if r["ndvi_mean"] is not None]
    dates = [dt.date.fromisoformat(r["date"]) for r in good_recs]
    vals = [r["ndvi_mean"] for r in good_recs]
    days, sm = sat.smooth_series(dates, vals) if len(dates) >= 3 else (dates, np.array(vals, float))
    phen = sat.phenology(days, sm)
    phen["harvest_events"] = sat.harvest_events(dates, vals)  # cuttings / harvests detected from space

    # terrain on the same mercator grid (sample the zoom-14 DEM analysis at our pixel centres)
    slope_g = twi_g = None
    try:
        demarr, dmeta = demmod.dem_around(lat, lon)
        L = terrain.terrain_layers(demarr, dmeta["cell_m"], 500.0, "loam", 0.2)
        mx = grid["x0"] + (xx + 0.5) * grid["px"]
        my = grid["y1"] - (yy + 0.5) * grid["px"]
        n = 2 ** int(dmeta["zoom"])
        tx = (mx / (2 * math.pi * sentinel.R) + 0.5) * n
        ty = (0.5 - my / (2 * math.pi * sentinel.R)) * n
        ci = np.clip(((tx - dmeta["x0"]) * 256).astype(int), 0, demarr.shape[1] - 1)
        ri = np.clip(((ty - dmeta["y0"]) * 256).astype(int), 0, demarr.shape[0] - 1)
        slope_g = L["slope_pct"][ri, ci]
        twi_g = L["twi_zone"][ri, ci]
    except Exception as e:
        log.info("terrain for zones unavailable: %s", e)

    zones_out = None
    if len(stack) >= 4:
        z = sat.management_zones(np.array(stack), mask, slope_g, twi_g)
        if z:
            rgba = np.zeros((h, w, 4), dtype=np.uint8)
            for zi in z["zones"]:
                col = zi["color"]
                m = z["labels"] == zi["rank"]
                rgba[m, :3] = (int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16))
                rgba[m, 3] = 200
            (_dir() / f"{key}_zones.png").write_bytes(_rgba_png(rgba))
            twi_field = float(np.nanmean(twi_g[mask])) if twi_g is not None else None
            zones_out = {
                "png": f"/api/satellite/png/{key}/zones.png",
                "k": z["k"],
                "method": "k-means on standardized per-pixel features ("
                + ", ".join(z["features"])
                + "), k chosen by silhouette",
                "silhouette": z["silhouette"],
                "legend": [
                    {
                        "color": zi["color"],
                        "label": zi["label"],
                        "share_pct": zi["share_pct"],
                        "ndvi_mean": zi["ndvi_mean"],
                    }
                    for zi in z["zones"]
                ],
                "advice": sat.zone_advice(z["zones"], twi_field),
            }

    # latest clear scene: true colour + NDVI images
    latest = None
    if good_recs:
        lr = good_recs[-1]
        try:
            rb = sentinel.read_scene(lr["_scene"], grid, bands=("red", "green", "blue", "nir", "scl"))
            rgb = np.dstack([rb["red"], rb["green"], rb["blue"]])
            rgb8 = np.clip(np.nan_to_num(rgb) / 0.25 * 255, 0, 255).astype(
                np.uint8
            )  # simple reflectance stretch
            rgba = np.dstack([rgb8, np.full((h, w), 255, np.uint8)])
            (_dir() / f"{key}_truecolor.png").write_bytes(_rgba_png(rgba))
            nd = sat.ndvi(rb["red"], rb["nir"])
            (_dir() / f"{key}_ndvi.png").write_bytes(_rgba_png(_ndvi_rgba(nd, mask)))
            latest = {
                "date": lr["date"],
                "truecolor_png": f"/api/satellite/png/{key}/truecolor.png",
                "ndvi_png": f"/api/satellite/png/{key}/ndvi.png",
            }
        except Exception as e:
            log.warning("latest images failed: %s", e)

    kcb_now = None
    if good_recs and (end - dt.date.fromisoformat(good_recs[-1]["date"])).days <= 20:
        c = crop(req.get("crop") or "maize")
        kcb_now = sat.kcb_from_ndvi(
            good_recs[-1]["ndvi_mean"], kcb_full=c["kc_mid"] - 0.05, crop_height_m=1.0
        )

    result = {
        "status": "done",
        "progress": 1.0,
        "field_key": key,
        "bounds": grid["bounds"],
        "scenes": [{k: v for k, v in r.items() if k != "_scene"} for r in recs],
        "timeseries": [{"date": d.isoformat(), "value": v} for d, v in zip(dates, vals, strict=True)],
        "smoothed": [
            {"date": d.isoformat(), "value": round(float(v), 3)} for d, v in zip(days, sm, strict=True)
        ][::3],
        "latest": latest,
        "phenology": phen,
        "zones": zones_out,
        "kcb_now": kcb_now,
        "sources": [
            {
                "id": "sentinel2",
                "name": "Copernicus Sentinel-2 L2A (via Earth Search, AWS Open Data)",
                "provider": "ESA Copernicus / Element 84",
                "url": "https://registry.opendata.aws/sentinel-2-l2a-cogs/",
                "resolution": "10 m, 5-day revisit",
                "latency": "~1 day",
                "last_date": recs[-1]["date"],
                "is_nasa": False,
                "status": "live",
            }
        ],
        "caveats": [
            "Clouds and shadows are masked with the Sentinel-2 scene classification; scenes with < 60 % clear field pixels are skipped.",
            "NDVI shows canopy greenness, not yield; differences between zones need to be checked on the ground.",
            "Management zones are statistical (unsupervised); their causes (soil, water, pests) need local diagnosis.",
        ],
        "computed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }
    (_dir() / f"{key}.json").write_text(json.dumps(result))
    _set(key, status="done", progress=1.0)


def latest_for(
    lat: float, lon: float, polygon: list[list[float]] | None, crop_id: str | None, today: dt.date
) -> dict[str, Any] | None:
    """Cached satellite result for this field (default analysis window), if any — never starts a job."""
    end = today - dt.timedelta(days=today.weekday())
    req = {"lat": lat, "lon": lon, "polygon": polygon, "crop": crop_id}
    return _cached(_key(req, end - dt.timedelta(days=365), end))
