"""NASA FIRMS active fires (MODIS + VIIRS near-real-time) around a field.

Modes (env FIELDSHIFT_FIRMS, default "auto"):
  * auto  – with a MAP_KEY (env FIELDSHIFT_FIRMS_MAP_KEY or FIRMS_MAP_KEY; free at
            https://firms.modaps.eosdis.nasa.gov/api/map_key/) use the FIRMS area API for the field's
            surroundings (VIIRS NOAA-20, NOAA-21, S-NPP and MODIS; NRT for recent dates, standard
            processing for older as-of dates). Without a key, use the public keyless 24-hour global
            VIIRS NOAA-20 / NOAA-21 text files (recent dates only). If both fail, or the network is off,
            fall back to recorded demo data (when the field and date are covered), else "unavailable".
  * demo  – recorded data only (backend/fieldshift/data/firms_demo/*.json.gz).
  * off   – never fetch; no fire cards.
The MAP_KEY is never written to the cache key, cache index, logs or responses.
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from .http import CACHE_DIR, DataUnavailable, offline_mode
from .sources import SOURCES

log = logging.getLogger("fieldshift.firms")
API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
OPEN = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
OPEN_FILES = {
    "VIIRS_NOAA20_NRT": "noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_24h.csv",
    "VIIRS_NOAA21_NRT": "noaa-21-viirs-c2/csv/J2_VIIRS_C2_Global_24h.csv",
}
NRT_SOURCES = ["VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"]
SP_SOURCES = ["VIIRS_NOAA20_SP", "VIIRS_SNPP_SP", "MODIS_SP"]
DEMO_DIR = Path(__file__).resolve().parent / "firms_demo"

SOURCES.setdefault(
    "firms",
    dict(
        name="NASA FIRMS active fires (VIIRS 375 m, MODIS 1 km)",
        provider="NASA LANCE / FIRMS",
        url="https://firms.modaps.eosdis.nasa.gov/",
        resolution="375 m (VIIRS), 1 km (MODIS); several overpasses per day",
        latency="< 3 hours (near real-time)",
        is_nasa=True,
    ),
)


@dataclass
class Fire:
    lat: float
    lon: float
    date: dt.date
    time_utc: str
    satellite: str
    confidence: str  # low | nominal | high
    frp_mw: float
    daynight: str
    km: float = 0.0
    bearing: float = 0.0


@dataclass
class FireResult:
    fires: list[Fire]
    status: str  # live | cache | demo | unavailable | off
    mode: str  # api | open | demo | none
    radius_km: float
    start: dt.date
    end: dt.date
    note: str = ""


def mode() -> str:
    return os.environ.get("FIELDSHIFT_FIRMS", "auto").lower()


def map_key() -> str | None:
    k = os.environ.get("FIELDSHIFT_FIRMS_MAP_KEY") or os.environ.get("FIRMS_MAP_KEY")
    return k.strip() if k and k.strip() else None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(b: float) -> str:
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((b + 22.5) // 45) % 8]


def _conf(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("l", "low"):
        return "low"
    if v in ("h", "high"):
        return "high"
    if v in ("n", "nominal"):
        return "nominal"
    try:  # MODIS: 0–100 %
        x = float(v)
    except ValueError:
        return "nominal"
    return "low" if x < 30 else "high" if x >= 80 else "nominal"


def parse_csv(text: str) -> list[Fire]:
    out: list[Fire] = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            out.append(
                Fire(
                    float(r["latitude"]),
                    float(r["longitude"]),
                    dt.date.fromisoformat(r["acq_date"]),
                    str(r.get("acq_time", "")).zfill(4),
                    str(r.get("satellite", "")),
                    _conf(str(r.get("confidence", ""))),
                    float(r.get("frp") or 0.0),
                    str(r.get("daynight", "")),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return out


# ------------------------------------------------------------------ fetching with a key-free disk cache
def _cache_path(tag: str) -> Path:
    return CACHE_DIR / "firms" / f"{hashlib.sha256(tag.encode()).hexdigest()[:32]}.csv.gz"


def _get_csv(url: str, cache_tag: str, ttl_s: float, timeout_s: float = 30.0) -> tuple[str, str]:
    """GET a CSV through: fresh cache -> network -> stale cache. `cache_tag` must not contain secrets."""
    path = _cache_path(cache_tag)
    if path.exists() and (time.time() - path.stat().st_mtime < ttl_s or offline_mode()):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read(), "cache"
    if not offline_mode():
        try:
            r = httpx.get(
                url, timeout=timeout_s, follow_redirects=True, headers={"User-Agent": "IA-Intelligent-Agriculture/1.0"}
            )
            if r.status_code == 200 and r.text.startswith("latitude"):
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(f".{os.getpid()}.tmp")
                with gzip.open(tmp, "wt", encoding="utf-8") as f:
                    f.write(r.text)
                tmp.replace(path)
                return r.text, "live"
            # never log the URL (it contains the MAP_KEY)
            log.warning("FIRMS request failed: HTTP %s %s", r.status_code, r.text[:80].replace("\n", " "))
        except httpx.HTTPError as e:
            log.warning("FIRMS request failed: %s", type(e).__name__)
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read(), "cache"
    raise DataUnavailable("FIRMS unavailable")


def _bbox(lat: float, lon: float, km: float) -> tuple[float, float, float, float]:
    dlat = km / 111.0
    dlon = km / (111.0 * max(0.1, math.cos(math.radians(lat))))
    return (round(lon - dlon, 3), round(lat - dlat, 3), round(lon + dlon, 3), round(lat + dlat, 3))


def fetch_api(
    lat: float, lon: float, start: dt.date, end: dt.date, radius_km: float, key: str
) -> tuple[list[Fire], str]:
    w, s, e, n = _bbox(lat, lon, radius_km)
    days = max(1, min(5, (end - start).days + 1))
    recent = (dt.date.today() - end).days <= 60
    fires: list[Fire] = []
    statuses = []
    for src in NRT_SOURCES if recent else SP_SOURCES:
        tag = f"api|{src}|{w},{s},{e},{n}|{days}|{end.isoformat()}"
        url = f"{API}/{key}/{src}/{w},{s},{e},{n}/{days}/{(end - dt.timedelta(days=days - 1)).isoformat()}"
        try:
            text, st = _get_csv(url, tag, ttl_s=3 * 3600 if recent else 365 * 86400)
        except DataUnavailable:
            continue
        statuses.append(st)
        fires += parse_csv(text)
    if not statuses:
        raise DataUnavailable("FIRMS API unavailable")
    return fires, "live" if "live" in statuses else "cache"


def fetch_open(lat: float, lon: float, radius_km: float) -> tuple[list[Fire], str]:
    """Keyless: public 24 h global VIIRS files (~7 MB each), cached for 3 h, filtered to the field."""
    fires: list[Fire] = []
    statuses = []
    w, s, e, n = _bbox(lat, lon, radius_km)
    for src, path in OPEN_FILES.items():
        hour = int(time.time() // (3 * 3600))
        try:
            text, st = _get_csv(f"{OPEN}/{path}", f"open|{src}|{hour}", ttl_s=3 * 3600, timeout_s=60)
        except DataUnavailable:
            continue
        statuses.append(st)
        # cheap pre-filter on the text before parsing 80k rows
        lines = text.splitlines()
        keep = [lines[0]]
        for ln in lines[1:]:
            parts = ln.split(",", 2)
            try:
                la, lo = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                continue
            if s <= la <= n and w <= lo <= e:
                keep.append(ln)
        fires += parse_csv("\n".join(keep))
    if not statuses:
        raise DataUnavailable("FIRMS open files unavailable")
    return fires, "live" if "live" in statuses else "cache"


@lru_cache
def _demo_sets() -> list[dict[str, Any]]:
    out = []
    if DEMO_DIR.exists():
        for p in sorted(DEMO_DIR.glob("*.json.gz")):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def fetch_demo(lat: float, lon: float, start: dt.date, end: dt.date) -> list[Fire] | None:
    """Recorded FIRMS detections, used only when the field lies inside a recording's box and the
    requested window overlaps its dates."""
    for ds in _demo_sets():
        w, s, e, n = ds["bbox"]
        d0, d1 = dt.date.fromisoformat(ds["start"]), dt.date.fromisoformat(ds["end"])
        if not (s <= lat <= n and w <= lon <= e) or end < d0 or start > d1:
            continue
        cols = ds["columns"]
        fires = []
        for row in ds["fires"]:
            r = dict(zip(cols, row, strict=True))
            fires.append(
                Fire(
                    r["lat"],
                    r["lon"],
                    dt.date.fromisoformat(r["date"]),
                    r["time"],
                    r["sat"],
                    r["conf"],
                    r["frp"],
                    r["dn"],
                )
            )
        return fires
    return None


def nearby_fires(
    lat: float, lon: float, today: dt.date, radius_km: float = 50.0, days: int = 2
) -> FireResult:
    """Active-fire detections within `radius_km` of the field in the `days` days up to `today`."""
    end = today
    start = today - dt.timedelta(days=days - 1)
    m = mode()
    fires: list[Fire] | None = None
    status, used, note = "unavailable", "none", ""
    if m == "off":
        return FireResult([], "off", "none", radius_km, start, end, "FIRMS disabled (FIELDSHIFT_FIRMS=off)")
    if m != "demo":
        key = map_key()
        try:
            if key:
                fires, status = fetch_api(lat, lon, start, end, radius_km, key)
                used = "api"
            elif (dt.date.today() - today).days <= 1:
                fires, status = fetch_open(lat, lon, radius_km)
                used = "open"
                note = "Keyless FIRMS feed covers the last 24 h only; add a free MAP_KEY for 48 h and MODIS."
        except DataUnavailable as e:
            log.info("FIRMS live unavailable: %s", e)
            fires = None
    if fires is None:
        demo = fetch_demo(lat, lon, start, end)
        if demo is not None:
            fires, status, used = demo, "demo", "demo"
            note = "Recorded FIRMS detections (demo data)."
    if fires is None:
        return FireResult(
            [],
            "unavailable",
            "none",
            radius_km,
            start,
            end,
            "No FIRMS data (offline, no key, or historic date)",
        )
    out = []
    for f in fires:
        if not (start <= f.date <= end) or f.confidence == "low":
            continue
        f.km = haversine_km(lat, lon, f.lat, f.lon)
        if f.km <= radius_km:
            f.bearing = bearing_deg(lat, lon, f.lat, f.lon)
            out.append(f)
    out.sort(key=lambda f: f.km)
    return FireResult(out, status, used, radius_km, start, end, note)
