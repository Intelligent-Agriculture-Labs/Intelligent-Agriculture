"""Build FieldShift's global GRACE/GRACE-FO water-storage asset from the JPL RL06.3 CRI mascon grid.

    python scripts/grace_extract.py                  # downloads the latest granule (needs Earthdata Login)
    python scripts/grace_extract.py path/to/GRCTellus.JPL.*.nc

Credentials: EARTHDATA_USER/EARTHDATA_PASS or ~/.config/fieldshift/earthdata ("user:password", chmod 600) — only
needed for the download; never printed or stored. Needs `netCDF4` (data box only; the backend does not).

Input:  TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4 (PO.DAAC), monthly liquid-water-equivalent thickness anomaly
        (cm, relative to 2004.0–2009.999), 0.5° grid sampled from 3° equal-area mascons, Apr 2002 → ~3 months ago.
Output: backend/fieldshift/data/grace/grace_tws.npz (committed, ~1 MB) with
          days     (T,)      mid-month time, days since 2002-01-01
          series   (S, T)    int16, mm — the distinct land mascon series (CRI splits coastal mascons)
          index    (360,720) int16, row in `series` for each 0.5° land cell, -1 = ocean / no data
          scale    (360,720) float16, JPL CRI land-hydrology scale factor (gain) for each cell
          sigma    (S,)      float16, median monthly uncertainty of the series, mm
        and grace_tws.json (provenance: granule, coverage, licence).
The backend reads the asset offline (fieldshift/data/grace.py), so the indicator works worldwide without a key.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "fieldshift" / "data" / "grace"
SHORT_NAME = "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4"
URS = "urs.earthdata.nasa.gov"


def creds() -> tuple[str, str]:
    u, p = os.environ.get("EARTHDATA_USER"), os.environ.get("EARTHDATA_PASS")
    if u and p:
        return u, p
    user, _, pw = (Path.home() / ".config" / "fieldshift" / "earthdata").read_text().strip().partition(":")
    return user, pw


def download(dest: Path) -> Path:
    import httpx

    r = httpx.get(
        "https://cmr.earthdata.nasa.gov/search/granules.umm_json",
        params={"short_name": SHORT_NAME, "sort_key": "-start_date", "page_size": 1},
        timeout=60,
    )
    item = r.json()["items"][0]["umm"]
    url = next(
        u["URL"]
        for u in item["RelatedUrls"]
        if u.get("Type") == "GET DATA" and u["URL"].startswith("https") and u["URL"].endswith(".nc")
    )
    path = dest / url.rsplit("/", 1)[1]
    if path.exists():
        return path
    auth = creds()
    c = httpx.Client(timeout=600, follow_redirects=False)
    for _ in range(10):  # follow the Earthdata Login redirect chain; send credentials only to URS
        resp = c.get(url, auth=auth if httpx.URL(url).host == URS else None)
        if resp.status_code in (301, 302, 303, 307, 308):
            url = str(httpx.URL(url).join(resp.headers["location"]))
            continue
        resp.raise_for_status()
        dest.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        return path
    raise RuntimeError("too many redirects")


def build(nc_path: Path) -> None:
    import netCDF4

    d = netCDF4.Dataset(nc_path)
    lwe = np.ma.filled(d["lwe_thickness"][:], np.nan).astype(np.float64)  # (T, 360, 720) cm
    unc = np.ma.filled(d["uncertainty"][:], np.nan).astype(np.float64)
    land = np.ma.filled(d["land_mask"][:], 0) > 0.5
    scale = np.ma.filled(d["scale_factor"][:], np.nan)
    days = np.asarray(d["time"][:], dtype=np.float64)
    lat = np.asarray(d["lat"][:])
    lon = np.asarray(d["lon"][:])
    assert lat[0] < lat[-1] and abs(lon[0] - 0.25) < 1e-6, (
        "expected lat ascending from -89.75, lon 0.25..359.75"
    )

    mm = np.round(lwe * 10).astype(np.int32)  # cm -> mm, 1 mm precision is far below GRACE's uncertainty
    ok = land & np.isfinite(lwe).all(axis=0)
    rows = mm[:, ok].T  # (cells, T)
    uniq, inv = np.unique(rows, axis=0, return_inverse=True)
    index = np.full(land.shape, -1, dtype=np.int16)
    index[ok] = inv.astype(np.int16)
    sigma = np.zeros(len(uniq), dtype=np.float16)
    unc_rows = unc[:, ok].T * 10
    for k in range(len(uniq)):
        sigma[k] = np.float16(np.nanmedian(unc_rows[inv == k]))
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT / "grace_tws.npz",
        days=days.astype(np.float32),
        series=uniq.astype(np.int16),
        index=index,
        scale=np.where(np.isfinite(scale), scale, 1.0).astype(np.float16),
        sigma=sigma,
    )
    meta = {
        "granule": nc_path.name,
        "short_name": SHORT_NAME,
        "title": str(getattr(d, "title", "")),
        "time_coverage_start": str(getattr(d, "time_coverage_start", "")),
        "time_coverage_end": str(getattr(d, "time_coverage_end", "")),
        "time_mean_removed": str(getattr(d, "time_mean_removed", "")),
        "native_resolution": "3° equal-area mascons (~300 km), sampled on a 0.5° grid",
        "months": int(len(days)),
        "land_cells": int(ok.sum()),
        "distinct_series": int(len(uniq)),
        "licence": "NASA Earth science data policy (open, no restrictions); cite Watkins et al. 2015, Wiese et al. 2016",
        "doi": "10.5067/TEMSC-3JC63",
    }
    (OUT / "grace_tws.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))
    print("asset size", (OUT / "grace_tws.npz").stat().st_size, "bytes")


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else download(ROOT / "backend" / ".cache" / "grace")
    build(src)


if __name__ == "__main__":
    main()
