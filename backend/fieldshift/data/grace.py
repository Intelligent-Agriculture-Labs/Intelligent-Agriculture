"""GRACE / GRACE-FO terrestrial water storage at a location, from the committed global asset.

The asset (data/grace/grace_tws.npz, ~0.7 MB) is built by scripts/grace_extract.py from the JPL RL06.3 CRI mascon
grid (PO.DAAC, Earthdata Login). It holds every distinct land mascon series once plus a 0.5° index and the JPL
land-hydrology scale factor per cell, so lookups work worldwide and offline with no key.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

DIR = Path(__file__).resolve().parent / "grace"
ASSET = DIR / "grace_tws.npz"
EPOCH = dt.date(2002, 1, 1)


@lru_cache(maxsize=1)
def _load() -> dict[str, Any] | None:
    if not ASSET.exists():
        return None
    with np.load(ASSET) as z:
        data = {k: z[k] for k in z.files}
    meta_f = DIR / "grace_tws.json"
    data["meta"] = json.loads(meta_f.read_text()) if meta_f.exists() else {}
    return data


def cell_of(lat: float, lon: float) -> tuple[int, int]:
    """Row/column of the 0.5° cell (rows from -90, columns from 0° E)."""
    i = min(359, max(0, int(math.floor((lat + 90.0) / 0.5))))
    j = int(math.floor((lon % 360.0) / 0.5)) % 720
    return i, j


def tws_at(lat: float, lon: float, max_cells: int = 2) -> dict[str, Any] | None:
    """Monthly water-storage anomaly (cm LWE, vs. 2004–2009 mean) for the land cell at/nearest to lat, lon.
    Coastal fields fall back to the nearest land cell within `max_cells` (≤ ~110 km). None if no data."""
    a = _load()
    if a is None:
        return None
    index, scale = a["index"], a["scale"]
    i0, j0 = cell_of(lat, lon)
    best: tuple[float, int, int] | None = None
    for di in range(-max_cells, max_cells + 1):
        for dj in range(-max_cells, max_cells + 1):
            i, j = i0 + di, (j0 + dj) % 720
            if 0 <= i < 360 and index[i, j] >= 0:
                d = math.hypot(di, dj * math.cos(math.radians(lat)))
                if best is None or d < best[0]:
                    best = (d, i, j)
    if best is None:
        return None
    _, i, j = best
    k = int(index[i, j])
    g = float(scale[i, j])
    g = g if math.isfinite(g) and g > 0 else 1.0
    vals = a["series"][k].astype(np.float64) / 10.0 * g  # mm -> cm, JPL land-hydrology gain
    dates = [EPOCH + dt.timedelta(days=float(d)) for d in a["days"]]
    return {
        "dates": dates,
        "tws_cm": vals,
        "sigma_cm": float(a["sigma"][k]) / 10.0 * g,
        "cell_lat": -90.0 + 0.5 * i + 0.25,
        "cell_lon": ((0.5 * j + 0.25 + 180.0) % 360.0) - 180.0,
        "scale_factor": round(g, 3),
        "moved_km": round(best[0] * 55.0) if best[0] > 0 else 0,
        "meta": a["meta"],
    }
