"""HTTP access with a disk cache, retries, rate limiting and an offline/demo fallback chain.

Fallback chain for every request:  fresh disk cache -> live network (with retries) -> stale disk
cache -> committed demo cache (backend/demo_cache) -> raise DataUnavailable.

The cache key is a hash of the URL + sorted params, so the committed demo cache is simply a copy
of the disk cache for the demo locations (see scripts/build_demo_cache.py).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("fieldshift.http")

BACKEND_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(os.environ.get("FIELDSHIFT_CACHE_DIR", BACKEND_DIR / ".cache"))
DEMO_DIR = Path(os.environ.get("FIELDSHIFT_DEMO_DIR", BACKEND_DIR / "demo_cache"))


def offline_mode() -> bool:
    return os.environ.get("FIELDSHIFT_OFFLINE", "0") == "1"


class DataUnavailable(RuntimeError):
    pass


@dataclass
class Fetched:
    data: Any
    status: str  # "live" | "cache" | "demo"
    fetched_at: float


_host_locks: dict[str, threading.Lock] = {}
_host_down: dict[str, float] = {}
_deadline_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="http")


def _get_with_deadline(url: str, *, timeout: float, **kw: Any) -> httpx.Response:
    """httpx timeouts are per phase (a trickling server can exceed them); enforce a hard total deadline."""
    fut = _deadline_pool.submit(httpx.get, url, timeout=httpx.Timeout(timeout, connect=10.0), **kw)
    try:
        return fut.result(timeout=timeout * 1.5 + 5)
    except FutTimeout as e:
        raise TimeoutError(f"hard deadline exceeded for {url}") from e


_host_last: dict[str, float] = {}
_MIN_INTERVAL = {"modis.ornl.gov": 0.5, "power.larc.nasa.gov": 0.2, "rest.isric.org": 1.0}


def _rate_limit(host: str) -> None:
    lock = _host_locks.setdefault(host, threading.Lock())
    with lock:
        wait = _MIN_INTERVAL.get(host, 0.1) - (time.time() - _host_last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _host_last[host] = time.time()


def cache_key(url: str, params: dict[str, Any] | None) -> str:
    p = json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.sha256(f"{url}?{p}".encode()).hexdigest()[:32]


def _read(path: Path) -> Any | None:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    tmp.replace(path)


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    ttl_s: float = 6 * 3600,
    timeout_s: float = 60.0,
    retries: int = 3,
    headers: dict[str, str] | None = None,
) -> Fetched:
    """GET a JSON document through the fallback chain."""
    key = cache_key(url, params)
    cpath = CACHE_DIR / f"{key}.json.gz"
    dpath = DEMO_DIR / f"{key}.json.gz"

    cached = _read(cpath) if cpath.exists() else None
    if cached is not None and (time.time() - cached["t"] < ttl_s or offline_mode()):
        return Fetched(cached["d"], "cache", cached["t"])

    down_until = _host_down.get(httpx.URL(url).host, 0.0)
    if not offline_mode() and time.time() >= down_until:
        host = httpx.URL(url).host
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                _rate_limit(host)
                r = _get_with_deadline(
                    url,
                    params=params,
                    timeout=timeout_s,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "FieldShift/1.0 (NASA Space Apps 2026)",
                        **(headers or {}),
                    },
                    follow_redirects=True,
                )
                if r.status_code == 200:
                    data = r.json()
                    _write(cpath, {"t": time.time(), "u": url, "p": params, "d": data})
                    _update_index(key, url, params)
                    return Fetched(data, "live", time.time())
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    raise DataUnavailable(f"{url} -> HTTP {r.status_code}: {r.text[:200]}")
                last_err = RuntimeError(f"HTTP {r.status_code}")
            except DataUnavailable:
                raise
            except (httpx.HTTPError, ValueError, RuntimeError, TimeoutError) as e:  # network / JSON errors
                last_err = e
            time.sleep(min(8.0, 1.5 * 2**attempt))
        log.warning("live fetch failed for %s: %s", url, last_err)
        if (
            isinstance(last_err, (TimeoutError, httpx.TimeoutException))
            and os.environ.get("FIELDSHIFT_CIRCUIT_BREAKER", "1") == "1"
        ):
            _host_down[host] = time.time() + 300  # circuit breaker: skip a hanging host for 5 min

    if cached is not None:
        return Fetched(cached["d"], "cache", cached["t"])
    demo = _read(dpath) if dpath.exists() else None
    if demo is not None:
        return Fetched(demo["d"], "demo", demo["t"])
    fuzzy = _fuzzy_lookup(url, params)
    if fuzzy is not None:
        return fuzzy
    raise DataUnavailable(f"no live data and no cache for {url}")


DATE_KEYS = {"start", "end", "start_date", "end_date", "startDate", "endDate", "past_days"}


def _index_path(d: Path) -> Path:
    return d / "index.json"


def _fuzzy_lookup(url: str, params: dict[str, Any] | None) -> Fetched | None:
    """Offline fallback: same endpoint + same non-date params (location, variables), any date range.
    Picks the entry whose date range ends latest. Used so a pre-cached demo keeps working on later days."""
    want = {k: v for k, v in (params or {}).items() if k not in DATE_KEYS}
    best: tuple[str, Path, str] | None = None
    for d, status in ((CACHE_DIR, "cache"), (DEMO_DIR, "demo")):
        idx_file = _index_path(d)
        if not idx_file.exists():
            continue
        try:
            idx = json.loads(idx_file.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for key, meta in idx.items():
            if meta.get("u") != url:
                continue
            p = meta.get("p") or {}
            if {k: v for k, v in p.items() if k not in DATE_KEYS} != want:
                continue
            end = str(p.get("end") or p.get("end_date") or p.get("endDate") or "")
            if best is None or end > best[0]:
                best = (end, d / f"{key}.json.gz", status)
    if best is None:
        return None
    payload = _read(best[1])
    if payload is None:
        return None
    return Fetched(payload["d"], "demo" if best[2] == "demo" else "cache", payload["t"])


_index_lock = threading.Lock()


def _update_index(key: str, url: str, params: dict[str, Any] | None) -> None:
    with _index_lock:
        f = _index_path(CACHE_DIR)
        try:
            idx = json.loads(f.read_text()) if f.exists() else {}
        except (OSError, json.JSONDecodeError):
            idx = {}
        idx[key] = {"u": url, "p": params}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, default=str))
        tmp.replace(f)
