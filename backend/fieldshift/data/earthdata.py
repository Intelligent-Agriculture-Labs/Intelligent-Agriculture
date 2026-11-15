"""NASA feeds that need an Earthdata Login (EDL) account, with the same cache → demo → unavailable chain as http.py.

Routes (all verified 2026-11-15 from the data box):
  * GES DISC through the **Giovanni time-series API** (one request returns a whole point series, ~2.5 s):
      - GPM IMERG Late / Early daily rain (GPM_3IMERGDL.07 / GPM_3IMERGDE.07) → fills the ~2 months POWER's IMERG Final lacks
      - GRACE-DA weekly drought percentiles (GRACEDADM_CLSM025GL_7D.3.0): groundwater, root-zone and surface soil moisture
  * NSIDC **cloud OPeNDAP** point reads of SMAP L4 (SPL4SMGP.008): root-zone and surface soil moisture + root-zone
    percentile at the 9 km EASE-Grid 2.0 cell (granules found through CMR, which needs no login)
  * LP DAAC **ECOSTRESS L3T JET** (ECO_L3T_JET.002, 70 m daily ET) Cloud-Optimized GeoTIFFs, one pixel per overpass

Credentials (first found wins; never logged, never part of a cache key, never sent anywhere but urs.earthdata.nasa.gov):
  1. EARTHDATA_USER / EARTHDATA_PASS environment variables
  2. a "user:password" file at $FIELDSHIFT_EARTHDATA_FILE (default ~/.config/fieldshift/earthdata, chmod 600)
  3. ~/.netrc entry for machine urs.earthdata.nasa.gov
Without credentials (or with FIELDSHIFT_EARTHDATA=off) every function serves the disk cache or the committed demo
cache, else raises DataUnavailable — callers treat these layers as optional enrichment.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import netrc
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .http import DataUnavailable, Fetched, cached_call, get_json, offline_mode

log = logging.getLogger("fieldshift.earthdata")

URS = "urs.earthdata.nasa.gov"
GIOVANNI = "https://api.giovanni.earthdata.nasa.gov"
CMR = "https://cmr.earthdata.nasa.gov/search"
UA = {"User-Agent": "FieldShift/1.0 (NASA Space Apps 2026)"}

IMERG_LATE = "GPM_3IMERGDL_07_precipitation"
IMERG_EARLY = "GPM_3IMERGDE_07_precipitation"
GRACE_DA = {
    "groundwater": "GRACEDADM_CLSM025GL_7D_3_0_gws_inst",
    "rootzone": "GRACEDADM_CLSM025GL_7D_3_0_rtzsm_inst",
    "surface": "GRACEDADM_CLSM025GL_7D_3_0_sfsm_inst",
}
SMAP_L4 = ("SPL4SMGP", "008")
SMAP_L4_HOUR = "T103000"  # one 3-hourly analysis per day (09:00–12:00 UTC); root-zone water changes slowly
SMAP_L4_VARS = {
    "rootzone": "/Geophysical_Data/sm_rootzone",
    "surface": "/Geophysical_Data/sm_surface",
    "rootzone_pctl": "/Geophysical_Data/sm_rootzone_pctl",
}
ECOSTRESS = ("ECO_L3T_JET", "002")

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="edl")
_lock = threading.Lock()
_tokens: dict[str, tuple[str, float]] = {}  # name -> (token, expires_at); in memory only


# --------------------------------------------------------------------------- credentials and sessions
def credentials() -> tuple[str, str] | None:
    if os.environ.get("FIELDSHIFT_EARTHDATA", "auto") == "off":
        return None
    u, p = os.environ.get("EARTHDATA_USER"), os.environ.get("EARTHDATA_PASS")
    if u and p:
        return u, p
    f = Path(
        os.environ.get("FIELDSHIFT_EARTHDATA_FILE", Path.home() / ".config" / "fieldshift" / "earthdata")
    )
    try:
        user, _, pw = f.read_text().strip().partition(":")
        if user and pw:
            return user, pw
    except OSError:
        pass
    try:
        auth = netrc.netrc().authenticators(URS)
        if auth and auth[0] and auth[2]:
            return auth[0], auth[2]
    except (OSError, netrc.NetrcParseError):
        pass
    return None


def available() -> bool:
    """True when live Earthdata requests can be attempted (credentials present and not offline)."""
    return not offline_mode() and credentials() is not None


def _need_creds() -> tuple[str, str]:
    c = credentials()
    if c is None:
        raise DataUnavailable("no Earthdata Login configured")
    return c


_client_local = threading.local()


def _client() -> httpx.Client:
    c = getattr(_client_local, "c", None)
    if c is None:
        c = httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=False, headers=UA)
        _client_local.c = c
    return c


def edl_get(url: str, *, headers: dict[str, str] | None = None, timeout: float = 60.0) -> httpx.Response:
    """GET following redirects by hand; the basic-auth header goes to urs.earthdata.nasa.gov only."""
    auth = _need_creds()
    c = _client()
    for _ in range(10):
        on_urs = httpx.URL(url).host == URS
        r = c.get(url, auth=auth if on_urs else None, headers=headers, timeout=timeout)
        if r.status_code in (301, 302, 303, 307, 308):
            url = str(httpx.URL(url).join(r.headers["location"]))
            continue
        return r
    raise DataUnavailable("too many redirects")


def _token(name: str, make: Callable[[], tuple[str, float]]) -> str:
    with _lock:
        tok = _tokens.get(name)
        if tok and tok[1] > time.time() + 60:
            return tok[0]
    value, ttl = make()
    with _lock:
        _tokens[name] = (value, time.time() + ttl)
    return value


def _forget(name: str) -> None:
    with _lock:
        _tokens.pop(name, None)


def _giovanni_token() -> str:
    def make() -> tuple[str, float]:
        r = edl_get(f"{GIOVANNI}/signin")
        if r.status_code != 200:
            raise DataUnavailable(f"Giovanni sign-in HTTP {r.status_code}")
        j = r.json()
        return str(j["token"]), float(j.get("expires_in") or 3600)

    return _token("giovanni", make)


def _edl_bearer() -> str:
    def make() -> tuple[str, float]:
        r = httpx.post(
            f"https://{URS}/api/users/find_or_create_token", auth=_need_creds(), headers=UA, timeout=30
        )
        if r.status_code != 200:
            raise DataUnavailable(f"EDL token HTTP {r.status_code}")
        return str(r.json()["access_token"]), 12 * 3600.0

    return _token("edl", make)


# --------------------------------------------------------------------------- GES DISC via Giovanni
def parse_giovanni_csv(text: str) -> dict[str, Any]:
    """Giovanni time-series CSV → {"meta": {...}, "rows": [[iso_date, value|None], ...]}."""
    meta: dict[str, str] = {}
    rows: list[list[Any]] = []
    in_data = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Timestamp"):
            in_data = True
            continue
        k, _, v = line.partition(",")
        if not in_data:
            meta[k] = v
            continue
        try:
            val: float | None = float(v)
        except ValueError:
            val = None
        try:
            undef = float(meta.get("undef", "-9999"))
        except ValueError:
            undef = -9999.0
        if val is not None and (not math.isfinite(val) or abs(val - undef) < 1e-6 or val < -998):
            val = None
        rows.append([k[:10], val])
    if not rows and "Timestamp" not in text:
        raise DataUnavailable(f"unexpected Giovanni response: {text[:120]!r}")
    return {"meta": meta, "rows": rows}


def giovanni_series(
    data_id: str, lat: float, lon: float, start: dt.date, end: dt.date, *, ttl_s: float = 12 * 3600
) -> tuple[list[tuple[dt.date, float]], str, dict[str, Any]]:
    """Point time series from GES DISC through Giovanni. Returns ([(date, value)], status, meta)."""
    url = f"{GIOVANNI}/timeseries"
    params = {
        "data": data_id,
        "location": f"[{lat:.3f},{lon:.3f}]",
        "time": f"{start.isoformat()}T00:00:00/{end.isoformat()}T23:59:59",
    }

    def fetch() -> dict[str, Any]:
        for attempt in range(2):
            r = _client().get(
                url, params=params, headers={"authorizationtoken": _giovanni_token()}, timeout=90
            )
            if r.status_code == 200:
                return parse_giovanni_csv(r.text)
            if r.status_code in (401, 403) and attempt == 0:
                _forget("giovanni")
                continue
            raise DataUnavailable(f"Giovanni HTTP {r.status_code}")
        raise DataUnavailable("Giovanni authorisation failed")

    f: Fetched = cached_call(url, params, fetch, ttl_s=ttl_s)
    out = [
        (dt.date.fromisoformat(d), float(v))
        for d, v in f.data.get("rows", [])
        if v is not None and start <= dt.date.fromisoformat(d) <= end
    ]
    return out, f.status, f.data.get("meta", {})


# --------------------------------------------------------------------------- CMR (public, no login)
def cmr_granules(
    short_name: str,
    version: str,
    start: dt.date,
    end: dt.date,
    *,
    point: tuple[float, float] | None = None,
    name_pattern: str | None = None,
    ttl_s: float = 6 * 3600,
) -> list[dict[str, Any]]:
    """Granules (title, start time, links) of a collection in [start, end], optionally at a point."""
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        params: dict[str, Any] = {
            "short_name": short_name,
            "version": version,
            "temporal": f"{start.isoformat()}T00:00:00Z,{end.isoformat()}T23:59:59Z",
            "page_size": 2000,
            "page_num": page,
            "sort_key": "start_date",
        }
        if point is not None:
            params["point"] = f"{point[1]:.5f},{point[0]:.5f}"
        if name_pattern:
            params["readable_granule_name"] = name_pattern
            params["options[readable_granule_name][pattern]"] = "true"
        f = get_json(f"{CMR}/granules.json", params, ttl_s=ttl_s, timeout_s=60, retries=2)
        entries = f.data.get("feed", {}).get("entry", [])
        for e in entries:
            out.append(
                {
                    "title": e.get("title", ""),
                    "start": e.get("time_start", "")[:10],
                    "links": [lk.get("href", "") for lk in e.get("links", [])],
                }
            )
        if len(entries) < 2000:
            return out
        page += 1


# --------------------------------------------------------------------------- SMAP L4 via cloud OPeNDAP
_A, _E2 = 6378137.0, 0.0066943799901413165
_E = math.sqrt(_E2)


def _q(phi: float) -> float:
    s = math.sin(phi)
    return (1 - _E2) * (s / (1 - _E2 * s * s) - (1 / (2 * _E)) * math.log((1 - _E * s) / (1 + _E * s)))


def ease2_m09(lat: float, lon: float) -> tuple[int, int]:
    """Row, column of the 9 km global EASE-Grid 2.0 cell (3856 × 1624, WGS84 cylindrical equal-area, φ1 = 30°)."""
    cell, ncol, nrow = 9008.055210146, 3856, 1624
    phi1 = math.radians(30.0)
    k0 = math.cos(phi1) / math.sqrt(1 - _E2 * math.sin(phi1) ** 2)
    x = _A * k0 * math.radians(lon)
    y = _A * _q(math.radians(max(-85.0, min(85.0, lat)))) / (2 * k0)
    row = int((nrow / 2 * cell - y) // cell)
    col = int((x + ncol / 2 * cell) // cell)
    return min(nrow - 1, max(0, row)), min(ncol - 1, max(0, col))


def parse_dap_ascii(text: str) -> dict[str, float | None]:
    """'/Geophysical_Data/sm_rootzone[0], 0.0298674' lines → {'/Geophysical_Data/sm_rootzone': 0.0298674}."""
    out: dict[str, float | None] = {}
    for line in text.splitlines():
        if "[" not in line or "," not in line:
            continue
        name, _, rest = line.partition("[")
        vals = rest.split("]", 1)[-1].strip().lstrip(",").strip()
        try:
            v: float | None = float(vals.split(",")[0])
        except ValueError:
            continue
        out[name.strip()] = v if v is not None and math.isfinite(v) and v > -9000 else None
    return out


def _smap_granule_point(od_url: str, row: int, col: int) -> tuple[dict[str, float | None], str]:
    ce = ",".join(f"{p}[{row}][{col}]" for p in SMAP_L4_VARS.values())

    def fetch() -> dict[str, Any]:
        r = edl_get(f"{od_url}.ascii?{quote(ce, safe='/,')}", timeout=60)
        if r.status_code != 200:
            raise DataUnavailable(f"OPeNDAP HTTP {r.status_code}")
        vals = parse_dap_ascii(r.text)
        if not any(v is not None for v in vals.values()):
            raise DataUnavailable("OPeNDAP returned no values")
        return {k: vals.get(p) for k, p in SMAP_L4_VARS.items()}

    # granules never change: cache a year, never fuzzy-match another granule
    f = cached_call(od_url, {"row": row, "col": col, "v": 1}, fetch, ttl_s=365 * 86400, fuzzy=False)
    return dict(f.data), f.status


def _merge_status(statuses: list[str]) -> str:
    for s in ("live", "cache", "demo"):
        if s in statuses:
            return s
    return "unavailable"


def smap_l4_series(
    lat: float,
    lon: float,
    start: dt.date,
    end: dt.date,
    *,
    every_days: int = 1,
    max_workers: int = 8,
) -> tuple[list[dict[str, Any]], str]:
    """Daily SMAP L4 snapshots (one 3-hourly analysis per day) at the field's 9 km cell.
    Returns ([{date, rootzone, surface, rootzone_pctl}], status)."""
    row, col = ease2_m09(lat, lon)
    grans = cmr_granules(*SMAP_L4, start, end, name_pattern=f"SMAP_L4_SM_gph_*{SMAP_L4_HOUR}*")
    by_day: dict[str, str] = {}
    for g in grans:
        od = next((u for u in g["links"] if u.startswith("https://opendap.earthdata.nasa.gov/")), None)
        if od and g["start"]:
            by_day[g["start"]] = od
    days = sorted(by_day)
    if every_days > 1 and days:
        last = days[-1]
        days = [d for k, d in enumerate(reversed(days)) if k % every_days == 0][::-1]
        if last not in days:
            days.append(last)
    if not days:
        raise DataUnavailable("no SMAP L4 granules")

    def one(d: str) -> tuple[dict[str, Any], str] | None:
        try:
            vals, st = _smap_granule_point(by_day[d], row, col)
            return {"date": d, **vals}, st
        except DataUnavailable:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        got = [x for x in ex.map(one, days) if x is not None]
    if not got:
        raise DataUnavailable("SMAP L4 reads failed")
    return [g for g, _ in got], _merge_status([s for _, s in got])


# --------------------------------------------------------------------------- ECOSTRESS L3T JET (70 m daily ET)
def _cog_pixel(url: str, lat: float, lon: float) -> float | None:
    """One pixel of an LP DAAC Cloud-Optimized GeoTIFF (EDL bearer token → signed S3 URL → GDAL range reads)."""
    import rasterio
    from rasterio.warp import transform

    r = _client().get(url, headers={"Authorization": f"Bearer {_edl_bearer()}"}, timeout=60)
    if r.status_code not in (301, 302, 303, 307):
        raise DataUnavailable(f"LP DAAC HTTP {r.status_code}")
    signed = r.headers["location"]
    with (
        rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="2", GDAL_HTTP_TIMEOUT="60"
        ),
        rasterio.open("/vsicurl/" + signed) as ds,
    ):
        xs, ys = transform("EPSG:4326", ds.crs, [lon], [lat])
        rr, cc = ds.index(xs[0], ys[0])
        if not (0 <= rr < ds.height and 0 <= cc < ds.width):
            return None
        v = float(ds.read(1, window=((rr, rr + 1), (cc, cc + 1)))[0, 0])
    return v if math.isfinite(v) and 0 <= v < 30 else None


def ecostress_et(
    lat: float, lon: float, start: dt.date, end: dt.date, *, max_workers: int = 6
) -> tuple[list[tuple[dt.date, float]], str]:
    """ECOSTRESS daily ET (mm/day, 70 m) on clear overpasses over the point. Cloudy overpasses are dropped."""
    recent = (dt.date.today() - end).days < 30
    grans = cmr_granules(*ECOSTRESS, start, end, point=(lat, lon), ttl_s=6 * 3600 if recent else 30 * 86400)
    jobs: dict[str, tuple[str, str]] = {}
    for g in grans:
        url = next((u for u in g["links"] if u.startswith("https") and u.endswith("_ETdaily.tif")), None)
        if url:
            jobs.setdefault(g["title"], (g["start"], url))

    statuses: list[str] = []

    def one(item: tuple[str, str]) -> tuple[dt.date, float] | None:
        day, url = item

        def fetch() -> dict[str, Any]:
            return {"et": _cog_pixel(url, lat, lon)}

        try:
            f = cached_call(
                url, {"lat": round(lat, 5), "lon": round(lon, 5)}, fetch, ttl_s=365 * 86400, fuzzy=False
            )
        except DataUnavailable:
            return None
        statuses.append(f.status)
        v = f.data.get("et")
        return (dt.date.fromisoformat(day), float(v)) if v is not None else None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        got = [x for x in ex.map(one, jobs.values()) if x is not None]
    # several tiles/overpasses on one day: average
    by: dict[dt.date, list[float]] = {}
    for d, v in got:
        by.setdefault(d, []).append(v)
    return sorted((d, sum(v) / len(v)) for d, v in by.items()), _merge_status(statuses)


def submit(fn: Callable[..., Any], *a: Any, **k: Any) -> Any:
    """Run an Earthdata request on the module's thread pool (callers bound it with a timeout)."""
    return _pool.submit(fn, *a, **k)
