"""Live NASA Earthdata layers for one field, fetched in parallel with a hard time budget.

  * smap_l4 / smap_l4_surface / smap_l4_pctl ... SMAP L4 root-zone + surface soil moisture and root-zone percentile
  * ecostress ................................. ECOSTRESS 70 m daily ET on clear overpasses (mm/day)
  * grace_da_gws / grace_da_rtzsm / grace_da_sfsm  GRACE-DA weekly groundwater / root-zone / surface percentiles

Every layer is optional: without Earthdata Login, offline, or past the deadline it is simply absent (the disk cache and
the committed demo cache still serve the demo fields). Values are lists of (date, value) like ctx.enrich.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from concurrent.futures import Future
from typing import Any

from ..data import earthdata
from ..data.http import DataUnavailable

log = logging.getLogger("fieldshift.live")

SMAP_DAYS = 45  # SMAP L4 window (every 3rd day + the latest analysis)
ECO_DAYS = 60  # ECOSTRESS overpasses considered
GRACE_DA_DAYS = 400  # ~1 year of weekly GRACE-DA percentiles (latency 2–3 months)


def _smap(lat: float, lon: float, today: dt.date) -> tuple[dict[str, list[tuple[dt.date, float]]], str]:
    rows, st = earthdata.smap_l4_series(lat, lon, today - dt.timedelta(days=SMAP_DAYS), today, every_days=3)
    out: dict[str, list[tuple[dt.date, float]]] = {"smap_l4": [], "smap_l4_surface": [], "smap_l4_pctl": []}
    for r in rows:
        d = dt.date.fromisoformat(r["date"])
        for key, sid in (
            ("rootzone", "smap_l4"),
            ("surface", "smap_l4_surface"),
            ("rootzone_pctl", "smap_l4_pctl"),
        ):
            v = r.get(key)
            if v is not None:
                out[sid].append((d, float(v)))
    return out, st


def _eco(lat: float, lon: float, today: dt.date) -> tuple[dict[str, list[tuple[dt.date, float]]], str]:
    rows, st = earthdata.ecostress_et(lat, lon, today - dt.timedelta(days=ECO_DAYS), today)
    return {"ecostress": rows}, st


def _grace_da(lat: float, lon: float, today: dt.date) -> tuple[dict[str, list[tuple[dt.date, float]]], str]:
    out: dict[str, list[tuple[dt.date, float]]] = {}
    status = "unavailable"
    for key, sid in (
        ("groundwater", "grace_da_gws"),
        ("rootzone", "grace_da_rtzsm"),
        ("surface", "grace_da_sfsm"),
    ):
        try:
            rows, st, _ = earthdata.giovanni_series(
                earthdata.GRACE_DA[key], lat, lon, today - dt.timedelta(days=GRACE_DA_DAYS), today
            )
        except DataUnavailable:
            continue
        out[sid] = rows
        status = st if status == "unavailable" else status
    if not out:
        raise DataUnavailable("GRACE-DA unavailable")
    return out, status


LAYERS = {"smap_l4": _smap, "ecostress": _eco, "grace_da": _grace_da}


def fetch(lat: float, lon: float, today: dt.date, *, timeout_s: float = 12.0) -> dict[str, Any]:
    """{layer series..., "_status": {source id: status}}; whatever is not back within `timeout_s` is dropped."""
    futs: dict[str, Future[Any]] = {sid: earthdata.submit(fn, lat, lon, today) for sid, fn in LAYERS.items()}
    deadline = time.time() + timeout_s
    out: dict[str, Any] = {"_status": {}}
    for sid, f in futs.items():
        try:
            data, st = f.result(timeout=max(0.1, deadline - time.time()))
        except Exception as e:  # optional layers: never break advice
            log.info("live layer %s unavailable: %s", sid, type(e).__name__)
            out["_status"][sid] = "unavailable"
            continue
        out.update(data)
        out["_status"][sid] = st if any(data.values()) else "unavailable"
    return out
