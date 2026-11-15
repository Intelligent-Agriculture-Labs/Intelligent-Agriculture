"""Global benchmark for tap-to-detect field boundaries (docs/VALIDATION.md, section V9).

Ground truth: *Fields of The World* (FTW; Kerner et al. 2025, AAAI) vector field boundaries, 24 countries on four
continents, downloaded from source.coop (``kerner-lab/fields-of-the-world-<country>/boundaries_*.parquet``).
Each country keeps its own source licence (see VALIDATION.md); the polygons are NOT redistributed here, only
field ids, tap points and per-field scores.

Protocol
  1. ``sample``: per country, stratified random sample by field size class
     (S < 0.5 ha, M 0.5–2 ha, L 2–10 ha, XL 10–150 ha). For every field a simulated tap: a uniformly random point
     inside the polygon shrunk by min(10 m, 15 % of sqrt(area)), so the tap is clearly inside the field, as a farmer
     would tap it.
  2. ``run``: call the production code path (``fieldshift.engine.fields.detect_field``) at the tap. That is the
     same Esri World Imagery tiles (zoom 17, zoom 16 retry) and the same post-processing the app gets.
     Score in a local UTM projection: IoU of the returned polygon vs. the FTW polygon, and the boundary F-score
     (precision/recall of boundary points within 5 m of the other boundary). A failed detection scores 0.
  3. ``report``: per-country and per-size-class tables, before vs. after, held-out countries marked.

Countries are split ONCE, before any tuning: DEV countries are used for parameter tuning and model selection
(and their open orthophotos for training the edge model); every other country is held out (TEST).

Usage (data box; needs geopandas, pyarrow, shapely, pyproj in addition to the backend deps):
    python scripts/field_benchmark.py sample --ftw-dir ~/ftw --out bench/sample.parquet
    FIELDSHIFT_CACHE_DIR=bench/cache python scripts/field_benchmark.py run --sample bench/sample.parquet \
        --out docs/validation/field_benchmark_after.json --workers 12
    python scripts/field_benchmark.py report docs/validation/field_benchmark_before.json \
        docs/validation/field_benchmark_after.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Chosen before any tuning. DEV: tuning + model selection; edge-model training uses open orthophotos of
# FR/ES/NL/AT only (never Esri imagery). Everything else is held out.
DEV_COUNTRIES = ["austria", "france", "india", "netherlands", "spain"]
SIZE_CLASSES = [
    ("S <0.5 ha", 0.05, 0.5),
    ("M 0.5–2 ha", 0.5, 2.0),
    ("L 2–10 ha", 2.0, 10.0),
    ("XL 10–150 ha", 10.0, 150.0),
]
CONTINENT = {
    "brazil": "S. America",
    "cambodia": "Asia",
    "india": "Asia",
    "vietnam": "Asia",
    "kenya": "Africa",
    "rwanda": "Africa",
    "south_africa": "Africa",
}
BF_TOL_M = 5.0


def _country(fname: str) -> str:
    stem = Path(fname).stem.removeprefix("boundaries_")
    parts = [p for p in stem.split("_") if not p.isdigit()]
    return "_".join(parts)


def size_class(ha: float) -> str:
    for name, lo, hi in SIZE_CLASSES:
        if lo <= ha < hi:
            return name
    return "other"


# ----------------------------------------------------------------------------------------------- sample
def cmd_sample(a: argparse.Namespace) -> None:
    import geopandas as gpd
    from shapely.geometry import MultiPolygon, Point

    rng = np.random.default_rng(a.seed)
    rows: list[dict[str, Any]] = []
    for f in sorted(Path(a.ftw_dir).expanduser().glob("boundaries_*.parquet")):
        c = _country(f.name)
        g = gpd.read_parquet(f)[["id", "geometry"]]
        g = g[g.geometry.notna() & g.geometry.is_valid]
        utm = g.estimate_utm_crs()
        gu = g.to_crs(utm)

        # multipolygons: keep the main part if it holds >= 95 % of the area (else the "field" is ambiguous)
        def main_part(geom: Any) -> Any:
            if isinstance(geom, MultiPolygon):
                parts = sorted(geom.geoms, key=lambda part: part.area, reverse=True)
                return parts[0] if parts[0].area >= 0.95 * geom.area else None
            return geom

        gu["geometry"] = gu.geometry.apply(main_part)
        gu = gu[gu.geometry.notna()]
        gu["ha"] = gu.area / 1e4
        per_class = a.n_dev if c in DEV_COUNTRIES else a.n_test
        for cname, lo, hi in SIZE_CLASSES:
            pool = gu[(gu.ha >= lo) & (gu.ha < hi)]
            if pool.empty:
                continue
            take = pool.iloc[rng.permutation(len(pool))[: per_class * 3]]
            n = 0
            for _, r in take.iterrows():
                if n >= per_class:
                    break
                poly = r.geometry
                inner = poly.buffer(-min(10.0, 0.15 * math.sqrt(poly.area)))
                if inner.is_empty or inner.area < 4.0:
                    continue
                minx, miny, maxx, maxy = inner.bounds
                for _ in range(500):
                    p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
                    if inner.contains(p):
                        break
                else:
                    continue
                tap = gpd.GeoSeries([p], crs=utm).to_crs(4326).iloc[0]
                geo = gpd.GeoSeries([poly], crs=utm).to_crs(4326).iloc[0]
                rows.append(
                    {
                        "country": c,
                        "split": "dev" if c in DEV_COUNTRIES else "test",
                        "field_id": str(r["id"]),
                        "area_ha": round(float(r.ha), 3),
                        "size": cname,
                        "tap_lat": round(tap.y, 7),
                        "tap_lon": round(tap.x, 7),
                        "geometry": geo,
                    }
                )
                n += 1
        print(c, sum(1 for r in rows if r["country"] == c), flush=True)
    out = gpd.GeoDataFrame(rows, crs=4326)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(a.out)
    # The committed manifest holds ids and taps only (no polygons: per-country licences).
    out.drop(columns="geometry").to_csv(
        ROOT / "docs" / "validation" / "field_benchmark_sample.csv", index=False
    )
    print(len(out), "fields")


# -------------------------------------------------------------------------------------------------- run
def boundary_f(det: Any, ref: Any, tol: float = BF_TOL_M, step: float = 1.0) -> tuple[float, float, float]:
    """Boundary precision/recall/F: share of each outline's points (every `step` m) within `tol` m of the other."""

    def pts(g: Any) -> list[Any]:
        b = g.boundary
        n = max(8, int(b.length / step))
        return [b.interpolate(i / n, normalized=True) for i in range(n)]

    db, rb = det.boundary, ref.boundary
    p = float(np.mean([rb.distance(q) <= tol for q in pts(det)]))
    r = float(np.mean([db.distance(q) <= tol for q in pts(ref)]))
    return p, r, (2 * p * r / (p + r) if p + r > 0 else 0.0)


def _score_one(row: dict[str, Any]) -> dict[str, Any]:
    import shapely
    from fieldshift.engine import fields
    from pyproj import Transformer
    from shapely import wkb
    from shapely.geometry import Polygon

    ref_ll = wkb.loads(row["wkb"])
    lat, lon = row["tap_lat"], row["tap_lon"]
    zone = int((lon + 180) // 6) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    tf = Transformer.from_crs(4326, epsg, always_xy=True)

    def to_utm(g: Any) -> Any:
        return shapely.transform(g, lambda xy: np.column_stack(tf.transform(xy[:, 0], xy[:, 1])))

    ref = to_utm(ref_ll)
    out = {k: row[k] for k in ("country", "split", "field_id", "area_ha", "size", "tap_lat", "tap_lon")}
    t0 = time.perf_counter()
    try:
        for attempt in range(4):  # imagery-server hiccups are retried; they are not detector failures
            try:
                t0 = time.perf_counter()
                res = fields.detect_field(lat, lon)
                break
            except Exception as e:
                net = (
                    isinstance(e, OSError)
                    or "HTTP" in str(e)
                    or any(k in type(e).__name__ for k in ("Connect", "Timeout", "Remote", "Protocol"))
                )
                if not net or attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        out["seconds"] = round(time.perf_counter() - t0, 2)
        det = to_utm(Polygon(res["polygon"])).buffer(0)
        inter = det.intersection(ref).area
        union = det.union(ref).area
        p, r, f = boundary_f(det, ref)
        out.update(
            ok=True,
            iou=round(inter / union, 4) if union > 0 else 0.0,
            det_ha=round(det.area / 1e4, 3),
            bf_p=round(p, 4),
            bf_r=round(r, 4),
            bf=round(f, 4),
            confidence=res["confidence"],
            params=res.get("params"),
        )
    except Exception as e:  # a failed detection is scored as 0, never dropped
        out.update(
            ok=False, iou=0.0, bf=0.0, bf_p=0.0, bf_r=0.0, det_ha=0.0, error=f"{type(e).__name__}: {e}"[:200]
        )
        out.setdefault("seconds", round(time.perf_counter() - t0, 2))
    return out


def cmd_run(a: argparse.Namespace) -> None:
    import geopandas as gpd

    g = gpd.read_parquet(a.sample)
    if a.split:
        g = g[g.split == a.split]
    rows = [
        {**{k: r[k] for k in g.columns if k != "geometry"}, "wkb": r.geometry.wkb} for _, r in g.iterrows()
    ]
    res: list[dict[str, Any]] = []
    with ProcessPoolExecutor(a.workers) as ex:
        futs = [ex.submit(_score_one, r) for r in rows]
        for i, fu in enumerate(as_completed(futs)):
            res.append(fu.result())
            if (i + 1) % 25 == 0:
                print(
                    f"{i + 1}/{len(rows)} mean IoU so far {np.mean([x['iou'] for x in res]):.3f}", flush=True
                )
    res.sort(key=lambda x: (x["country"], x["size"], x["field_id"]))
    meta = {
        "label": a.label,
        "run": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "imagery": "Esri World Imagery z17 (z16 retry), production code path",
        "bf_tolerance_m": BF_TOL_M,
        "dev_countries": DEV_COUNTRIES,
        "n": len(res),
        "mean_iou": round(float(np.mean([x["iou"] for x in res])), 4),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"meta": meta, "fields": res}, indent=1, ensure_ascii=False))
    print(json.dumps(meta))


# ----------------------------------------------------------------------------------------------- report
def _agg(rows: list[dict[str, Any]]) -> tuple[int, float, float, float]:
    if not rows:
        return 0, float("nan"), float("nan"), float("nan")
    iou = np.array([r["iou"] for r in rows])
    return len(rows), float(iou.mean()), float(np.mean(iou >= 0.5)), float(np.mean([r["bf"] for r in rows]))


def _boot_ci(diff: np.ndarray, n: int = 4000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    m = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)]
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def report(before_path: str, after_path: str) -> str:
    b = json.loads(Path(before_path).read_text())
    a = json.loads(Path(after_path).read_text())
    key = lambda r: (r["country"], r["field_id"])  # noqa: E731
    bm = {key(r): r for r in b["fields"]}
    am = {key(r): r for r in a["fields"]}
    keys = sorted(set(bm) & set(am))
    B = [bm[k] for k in keys]
    A = [am[k] for k in keys]
    L: list[str] = []

    def line(name: str, bb: list[dict[str, Any]], aa: list[dict[str, Any]]) -> str:
        n, bi, bh, bf = _agg(bb)
        _, ai, ah, af = _agg(aa)
        d = ai - bi
        return f"| {name} | {n} | {bi:.2f} | **{ai:.2f}** | {d:+.2f} | {bh:.0%} → {ah:.0%} | {bf:.2f} → {af:.2f} |"

    hdr = "| {} | n | IoU before | IoU after | Δ | IoU ≥ 0.5 | boundary F (5 m) |\n|---|---|---|---|---|---|---|"
    for split, title in (
        ("test", "Held-out countries (never used for tuning or training)"),
        ("dev", "Development countries (used for tuning)"),
    ):
        bb = [r for r in B if r["split"] == split]
        aa = [r for r in A if r["split"] == split]
        if not bb:
            continue
        diff = np.array([y["iou"] - x["iou"] for x, y in zip(bb, aa, strict=True)])
        lo, hi = _boot_ci(diff)
        L.append(
            f"**{title}** — mean ΔIoU {diff.mean():+.3f} (95 % bootstrap CI {lo:+.3f} … {hi:+.3f}), n = {len(bb)}\n"
        )
        L.append(hdr.format("Country"))
        for c in sorted({r["country"] for r in bb}):
            cont = CONTINENT.get(c, "Europe")
            L.append(
                line(
                    f"{c.replace('_', ' ').title()} ({cont})",
                    [r for r in bb if r["country"] == c],
                    [r for r in aa if r["country"] == c],
                )
            )
        L.append(line("**All**", bb, aa))
        L.append("")
        L.append(hdr.format("Continent"))
        for cont in ("Africa", "Asia", "Europe", "S. America"):
            cb = [r for r in bb if CONTINENT.get(r["country"], "Europe") == cont]
            if cb:
                ca = [r for r in aa if CONTINENT.get(r["country"], "Europe") == cont]
                L.append(line(cont, cb, ca))
        L.append("")
        L.append(hdr.format("Size class"))
        for s, _, _ in SIZE_CLASSES:
            L.append(line(s, [r for r in bb if r["size"] == s], [r for r in aa if r["size"] == s]))
        L.append("")
    sec_b = np.array([r.get("seconds", np.nan) for r in B], float)
    sec_a = np.array([r.get("seconds", np.nan) for r in A], float)
    L.append(
        f"Time per tap (imagery cached, one process): median {np.nanmedian(sec_b):.1f} s → {np.nanmedian(sec_a):.1f} s, "
        f"95th percentile {np.nanpercentile(sec_b, 95):.1f} s → {np.nanpercentile(sec_a, 95):.1f} s. "
        f"Runs: before {b['meta']['run']}, after {a['meta']['run']}."
    )
    return "\n".join(L)


def cmd_report(a: argparse.Namespace) -> None:
    md = report(a.before, a.after)
    print(md)
    if a.write:
        doc = ROOT / "docs" / "VALIDATION.md"
        t = doc.read_text()
        b0, b1 = "<!-- FIELDS:BEGIN -->", "<!-- FIELDS:END -->"
        i, j = t.index(b0) + len(b0), t.index(b1)
        doc.write_text(t[:i] + "\n" + md + "\n" + t[j:])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("sample")
    s.add_argument("--ftw-dir", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--n-test", type=int, default=4, help="fields per size class per held-out country")
    s.add_argument("--n-dev", type=int, default=8, help="fields per size class per dev country")
    s.add_argument("--seed", type=int, default=2026)
    s.set_defaults(fn=cmd_sample)
    r = sp.add_parser("run")
    r.add_argument("--sample", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--label", default=os.environ.get("BENCH_LABEL", "run"))
    r.add_argument("--split", choices=["dev", "test"])
    r.add_argument("--workers", type=int, default=8)
    r.set_defaults(fn=cmd_run)
    q = sp.add_parser("report")
    q.add_argument("before")
    q.add_argument("after")
    q.add_argument("--write", action="store_true", help="replace the FIELDS block in docs/VALIDATION.md")
    q.set_defaults(fn=cmd_report)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
