"""Build the multi-region drought label set for the global drought classifier (run on the data box).

    backend/.venv/bin/python scripts/drought_labels_global.py

Inputs (downloaded by the `download` step into $FS_GD_DATA, default ~/fs-gdml-data; nothing is committed):
  * European Drought Observatory Combined Drought Indicator v4.1 (cdinx, 0.0417°, dekadal, 2012-2024), CC BY 4.0
    https://drought.emergency.copernicus.eu/data/Drought_Observatories_datasets/EDO_Combined_Drought_Indicator/
  * Global Drought Observatory Soil Moisture Index Anomaly v3.0.1 (smang, 0.05°, dekadal, 2005-2024), CC BY 4.0
    https://drought.emergency.copernicus.eu/data/Drought_Observatories_datasets/GDO_Soil_Moisture_Index_Anomaly/
  * U.S. Drought Monitor county statistics are fetched later by train_drought_ml.py (public domain).

Sites (fixed random seed, stratified on a coarse grid so every part of a region is represented):
  US   the same 80 counties as EXP-09 (labels: USDM)
  EU   80 points on the EDO grid north of 36°N, west of 40°E, with valid CDI (labels: CDI, strong)
  AUS, SAM, AFR, SAS, EAS   30 points each with valid SMIA (labels: SMIA, weak)
For every site the SMIA z-score is extracted as well (also for US/EU), so the weak label can be calibrated against
USDM and checked against CDI where both exist.

Output: $FS_GD_DATA/sites.json and $FS_GD_DATA/labels_{cdi,smia}.npz (site index, dekad date, value).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("FS_GD_DATA", Path.home() / "fs-gdml-data"))
EDO = "https://drought.emergency.copernicus.eu/data/Drought_Observatories_datasets"
CDI_YEARS = range(2012, 2025)
SMIA_YEARS = range(2005, 2025)
HALF_BOX = 0.25  # labels are summarised over a 0.5° box, about one NASA POWER cell

# lat0, lat1, lon0, lon1
WEAK_REGIONS = {
    "AUS": (-39.0, -12.0, 113.0, 154.0),
    "SAM": (-40.0, 5.0, -75.0, -35.0),
    "AFR": (-35.0, 15.0, -18.0, 52.0),
    "SAS": (6.0, 35.0, 66.0, 98.0),
    "EAS": (20.0, 50.0, 100.0, 135.0),
}
N_EU, N_WEAK = 80, 30


def cdi_path(y: int) -> Path:
    return DATA / "cdi" / f"cdinx_m_edo_{y}0101_{y}1221_t.nc"


def smia_path(y: int) -> Path:
    return DATA / "smia" / f"smang_m_gdo_{y}0101_{y}1221_t.nc"


def download() -> None:
    for sub, base, name, years in (
        ("cdi", "EDO_Combined_Drought_Indicator/ver4-1-1", "cdinx_m_edo", CDI_YEARS),
        ("smia", "GDO_Soil_Moisture_Index_Anomaly/ver3-0-1", "smang_m_gdo", SMIA_YEARS),
    ):
        (DATA / sub).mkdir(parents=True, exist_ok=True)
        for y in years:
            f = DATA / sub / f"{name}_{y}0101_{y}1221_t.nc"
            if not f.exists():
                subprocess.run(["curl", "-sSfL", "-o", str(f), f"{EDO}/{base}/{f.name}"], check=True)


def _grid(path: Path, var: str) -> tuple[np.ndarray, np.ndarray, list[dt.date]]:
    import netCDF4

    with netCDF4.Dataset(path) as d:
        lat, lon = np.array(d["lat"][:]), np.array(d["lon"][:])
        t = netCDF4.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False)
        dates = [dt.date(x.year, x.month, x.day) for x in t]
    return lat, lon, dates


def _box(lat: np.ndarray, lon: np.ndarray, la: float, lo: float) -> tuple[slice, slice]:
    i = np.where(np.abs(lat - la) <= HALF_BOX)[0]
    j = np.where(np.abs(lon - lo) <= HALF_BOX)[0]
    return slice(int(i.min()), int(i.max()) + 1), slice(int(j.min()), int(j.max()) + 1)


def _stratified(cands: list[tuple[float, float]], n: int, cell: float, seed: int) -> list[tuple[float, float]]:
    rng = np.random.default_rng(seed)
    cells: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for c in rng.permutation(np.array(cands)):
        cells.setdefault((int(c[0] // cell), int(c[1] // cell)), []).append((float(c[0]), float(c[1])))
    keys = list(cells)
    rng.shuffle(keys)
    out: list[tuple[float, float]] = []
    while len(out) < n and any(cells.values()):
        for k in keys:
            if cells[k] and len(out) < n:
                out.append(cells[k].pop())
    return out


def pick_eu() -> list[tuple[float, float]]:
    """Candidate centres on a 0.5° lattice whose 0.5° box has CDI data (classes 0-6) in >= 90 % of 2018 dekads."""
    import netCDF4

    with netCDF4.Dataset(cdi_path(2018)) as d:
        a = np.array(d["cdinx"][:, 0, :, :], dtype=float)
        lat, lon = np.array(d["lat"][:]), np.array(d["lon"][:])
    valid = np.mean((a >= 0) & (a <= 6), axis=0)
    cands = []
    for la in np.arange(36.25, 71.0, 0.5):
        for lo in np.arange(-10.25, 40.0, 0.5):
            si, sj = _box(lat, lon, la, lo)
            if np.mean(valid[si, sj] >= 0.9) >= 0.8:
                cands.append((round(float(la), 2), round(float(lo), 2)))
    return _stratified(cands, N_EU, 4.0, seed=7)


def pick_weak() -> dict[str, list[tuple[float, float]]]:
    import netCDF4

    with netCDF4.Dataset(smia_path(2015)) as d:
        lat, lon = np.array(d["lat"][:]), np.array(d["lon"][:])
        v = d["smang"]
        a = np.stack([np.array(v[k, :, :], dtype=np.float32) for k in (2, 11, 20, 29)])
    ok = np.mean(np.isfinite(a) & (np.abs(a) < 10), axis=0)
    out = {}
    for r, (la0, la1, lo0, lo1) in WEAK_REGIONS.items():
        cands = []
        for la in np.arange(la0 + 0.25, la1, 0.5):
            for lo in np.arange(lo0 + 0.25, lo1, 0.5):
                si, sj = _box(lat, lon, la, lo)
                if np.mean(ok[si, sj] >= 1.0) >= 0.8:
                    cands.append((round(float(la), 2), round(float(lo), 2)))
        out[r] = _stratified(cands, N_WEAK, 3.0, seed=11)
    return out


CDI_TO_LEVEL = np.array([0, 1, 2, 3, 0, 1, 1], dtype=np.int64)  # see cdi_level()


def cdi_level(px: np.ndarray) -> int | None:
    """CDI classes in a 0.5° box -> IA level (0 None, 1 D0, 2 D1, 3 D2).

    Watch (precipitation deficit) ~ D0, Warning (soil-moisture deficit) ~ D1, Alert (vegetation stress) ~ D2.
    Recovery -> None; the two temporary-recovery classes -> D0 (the event is not over). The box level follows
    the USDM county rule used for the U.S. labels: the highest level covering >= 50 % of the valid pixels."""
    v = px[(px >= 0) & (px <= 6)].astype(np.int64)
    if v.size < 0.5 * px.size:
        return None
    lv = CDI_TO_LEVEL[v]
    out = 0
    for k in (1, 2, 3):
        if np.mean(lv >= k) >= 0.5:
            out = k
    return out


def _cdi_year(args: tuple[int, list[tuple[float, float]]]) -> list[tuple[int, str, int]]:
    import netCDF4

    y, sites = args
    lat, lon, dates = _grid(cdi_path(y), "cdinx")
    with netCDF4.Dataset(cdi_path(y)) as d:
        a = np.array(d["cdinx"][:, 0, :, :])
    rows = []
    for s, (la, lo) in enumerate(sites):
        si, sj = _box(lat, lon, la, lo)
        for t, day in enumerate(dates):
            lv = cdi_level(a[t, si, sj])
            if lv is not None:
                rows.append((s, day.isoformat(), lv))
    return rows


def _smia_year(args: tuple[int, list[tuple[float, float]]]) -> list[tuple[int, str, float]]:
    import netCDF4

    y, sites = args
    lat, lon, dates = _grid(smia_path(y), "smang")
    boxes = [_box(lat, lon, la, lo) for la, lo in sites]
    rows = []
    with netCDF4.Dataset(smia_path(y)) as d:
        v = d["smang"]
        for t, day in enumerate(dates):
            a = np.array(v[t, :, :], dtype=np.float32)
            a[(~np.isfinite(a)) | (np.abs(a) > 10)] = np.nan
            for s, (si, sj) in enumerate(boxes):
                b = a[si, sj]
                if np.mean(np.isfinite(b)) >= 0.5:
                    rows.append((s, day.isoformat(), float(np.nanmean(b))))
    return rows


def main() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from train_drought_ml import counties

    download()
    us = counties(80)
    sites: list[dict[str, object]] = [
        {"id": f"US-{c['fips']}", "region": "US", "label": "usdm", "lat": c["lat"], "lon": c["lon"], "fips": c["fips"]}
        for c in us
    ]
    sites += [
        {"id": f"EU-{k:02d}", "region": "EU", "label": "cdi", "lat": la, "lon": lo}
        for k, (la, lo) in enumerate(pick_eu())
    ]
    for r, pts in pick_weak().items():
        sites += [
            {"id": f"{r}-{k:02d}", "region": r, "label": "smia", "lat": la, "lon": lo}
            for k, (la, lo) in enumerate(pts)
        ]
    print({r: sum(s["region"] == r for s in sites) for r in ("US", "EU", *WEAK_REGIONS)}, flush=True)
    (DATA / "sites.json").write_text(json.dumps(sites, indent=1))

    eu_idx = [i for i, s in enumerate(sites) if s["region"] == "EU"]
    eu_pts = [(float(sites[i]["lat"]), float(sites[i]["lon"])) for i in eu_idx]  # type: ignore[arg-type]
    with ProcessPoolExecutor(max_workers=8) as ex:
        cdi_rows = [r for rows in ex.map(_cdi_year, [(y, eu_pts) for y in CDI_YEARS]) for r in rows]
    np.savez_compressed(
        DATA / "labels_cdi.npz",
        site=np.array([eu_idx[r[0]] for r in cdi_rows]),
        date=np.array([r[1] for r in cdi_rows]),
        value=np.array([r[2] for r in cdi_rows]),
    )
    print("cdi rows", len(cdi_rows), flush=True)

    all_pts = [(float(s["lat"]), float(s["lon"])) for s in sites]  # type: ignore[arg-type]
    with ProcessPoolExecutor(max_workers=6) as ex:
        sm_rows = [r for rows in ex.map(_smia_year, [(y, all_pts) for y in SMIA_YEARS]) for r in rows]
    np.savez_compressed(
        DATA / "labels_smia.npz",
        site=np.array([r[0] for r in sm_rows]),
        date=np.array([r[1] for r in sm_rows]),
        value=np.array([r[2] for r in sm_rows]),
    )
    print("smia rows", len(sm_rows), flush=True)


if __name__ == "__main__":
    main()
