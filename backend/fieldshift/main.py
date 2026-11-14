"""FieldShift API (FastAPI). OpenAPI docs at /docs."""

from __future__ import annotations

import csv
import io
import logging
import os
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .data.http import DataUnavailable, offline_mode
from .engine import service

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
VERSION = "1.0.0"

app = FastAPI(
    title="FieldShift API",
    version=VERSION,
    description="NASA Earth observations → simple farm decisions on water, drought, pests, disease and crop rotations. "
    "NASA Space Apps Challenge 2026 — 'Field Shift: Adapting Farms with NASA Data'.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)

Irr = Literal["none", "drip", "sprinkler", "pivot", "furrow", "flood"]
Lang = Literal["en", "es", "fr", "sw", "hi", "de"]


class FieldInput(BaseModel):
    lat: float = Field(ge=-60, le=75)
    lon: float = Field(ge=-180, le=180)
    crop: str
    planting_date: str
    irrigation: Irr = "sprinkler"
    polygon: list[list[float]] | None = None
    water_allocation_mm: float | None = None
    last_irrigation_date: str | None = None
    last_irrigation_mm: float | None = None
    lang: Lang = "en"
    as_of: str | None = None


class SimulateRequest(BaseModel):
    lat: float = Field(ge=-60, le=75)
    lon: float = Field(ge=-180, le=180)
    crop: str
    planting_date: str
    irrigation_strategy: Literal["rainfed", "full", "deficit_75", "deficit_50", "allocation"] = "full"
    irrigation_method: Irr = "sprinkler"
    water_allocation_mm: float | None = None
    delta_t_c: float = Field(0.0, ge=-2, le=6)
    rain_factor: float = Field(1.0, ge=0.3, le=1.7)
    years: int = Field(20, ge=5, le=35)
    as_of: str | None = None


class Priorities(BaseModel):
    water: float = 0.3
    soil: float = 0.2
    income: float = 0.25
    pests: float = 0.1
    risk: float = 0.15


class RotationRequest(BaseModel):
    lat: float = Field(ge=-60, le=75)
    lon: float = Field(ge=-180, le=180)
    current_rotation: list[str] = Field(min_length=1, max_length=6)
    irrigation: Irr = "sprinkler"
    water_allocation_mm: float | None = None
    priorities: Priorities = Priorities()
    lang: Lang = "en"
    as_of: str | None = None


def _check_crop(cid: str) -> None:
    from .science.cropmodel import crops

    if cid not in crops():
        raise HTTPException(422, f"unknown crop '{cid}'")


@app.exception_handler(DataUnavailable)
async def _data_unavailable(_: Any, exc: DataUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=503, content={"detail": f"Data source unavailable and no cached copy: {exc}"}
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": VERSION, "offline_mode": offline_mode()}


@app.get("/api/crops")
def crops_ep() -> list[dict[str, Any]]:
    return service.crop_list()


@app.get("/api/presets")
def presets_ep() -> list[dict[str, Any]]:
    return [{**p, "cached": True} for p in service.presets()]


@app.post("/api/advice")
def advice_ep(inp: FieldInput) -> dict[str, Any]:
    _check_crop(inp.crop)
    return service.advice(inp.model_dump())


@app.post("/api/simulate")
def simulate_ep(req: SimulateRequest) -> dict[str, Any]:
    _check_crop(req.crop)
    return service.simulate_api(req.model_dump())


@app.post("/api/rotations")
def rotations_ep(req: RotationRequest) -> dict[str, Any]:
    for c in req.current_rotation:
        _check_crop(c)
    return service.rotations_api(req.model_dump())


@app.get("/api/climate")
def climate_ep(
    lat: float = Query(ge=-60, le=75), lon: float = Query(ge=-180, le=180), as_of: str | None = None
) -> dict[str, Any]:
    import datetime as dt

    return service.climate_api(lat, lon, dt.date.fromisoformat(as_of) if as_of else None)


@app.get("/api/export/advice.csv")
def export_csv(
    lat: float,
    lon: float,
    crop: str,
    planting_date: str,
    irrigation: Irr = "sprinkler",
    as_of: str | None = None,
) -> Response:
    """All time series behind the advice as tidy CSV (date, series, value, normal, unit, source)."""
    _check_crop(crop)
    adv = service.advice(
        {
            "lat": lat,
            "lon": lon,
            "crop": crop,
            "planting_date": planting_date,
            "irrigation": irrigation,
            "as_of": as_of,
        }
    )
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["date", "series", "value", "normal", "unit", "source", "kind"])
    for s in adv["series"]:
        normals = {p["date"]: p["value"] for p in s.get("normal", [])}
        for p in s["points"]:
            wr.writerow(
                [
                    p["date"],
                    s["id"],
                    p["value"],
                    normals.get(p["date"]),
                    s["unit"],
                    s["source"],
                    s.get("kind"),
                ]
            )
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fieldshift_advice.csv"},
    )


@app.get("/api/export/field.geojson")
def export_geojson(
    lat: float,
    lon: float,
    crop: str,
    planting_date: str,
    irrigation: Irr = "sprinkler",
    as_of: str | None = None,
) -> dict[str, Any]:
    _check_crop(crop)
    adv = service.advice(
        {
            "lat": lat,
            "lon": lon,
            "crop": crop,
            "planting_date": planting_date,
            "irrigation": irrigation,
            "as_of": as_of,
        }
    )
    props = {
        "crop": crop,
        "as_of": adv["as_of"],
        "drought_level": adv["drought"]["label"],
        "spi90": adv["drought"]["spi90"],
        "root_zone_depletion_mm": adv["water"].get("root_zone_depletion_mm"),
        "next_irrigation_date": adv["water"].get("next_irrigation_date"),
        "next_irrigation_mm": adv["water"].get("next_irrigation_mm"),
        "elevation_m": adv["field"]["elevation_m"],
        "slope_pct": adv["field"]["slope_pct"],
        "soil_texture": (adv["field"]["soil"] or {}).get("texture"),
        "cards": [
            {"id": c["id"], "risk": c["risk"], "title": c["title"], "due": c["due"]} for c in adv["cards"]
        ],
        "sources": [s["name"] for s in adv["sources"] if s["status"] != "unavailable"],
    }
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}
        ],
    }


class FarmCreate(BaseModel):
    name: str | None = Field(None, max_length=120)
    fields: list[dict[str, Any]] | None = None
    settings: dict[str, Any] | None = None


class FarmPush(BaseModel):
    name: str | None = Field(None, max_length=120)
    fields: list[dict[str, Any]] = []
    settings: dict[str, Any] | None = None


class FarmJoin(BaseModel):
    sync_code: str = Field(min_length=8, max_length=12)


def _farm_call(fn: Any, *a: Any) -> dict[str, Any]:
    from .engine import farms

    try:
        return fn(*a)
    except farms.FarmNotFound as e:
        raise HTTPException(404, "farm not found") from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/farms")
def farm_create(req: FarmCreate) -> dict[str, Any]:
    """Create a synced farm; returns farm_id (keep secret) and a short sync code for other devices."""
    from .engine import farms

    return _farm_call(farms.create, req.name, req.fields, req.settings)


@app.post("/api/farms/join")
def farm_join(req: FarmJoin) -> dict[str, Any]:
    from .engine import farms

    return _farm_call(farms.join, req.sync_code)


@app.get("/api/farms/{farm_id}")
def farm_get(farm_id: str) -> dict[str, Any]:
    from .engine import farms

    return _farm_call(farms.get, farm_id)


@app.put("/api/farms/{farm_id}")
def farm_push(farm_id: str, req: FarmPush) -> dict[str, Any]:
    from .engine import farms

    return _farm_call(farms.push, farm_id, req.name, req.fields, req.settings)


class SatelliteRequest(BaseModel):
    lat: float = Field(ge=-60, le=75)
    lon: float = Field(ge=-180, le=180)
    polygon: list[list[float]] | None = None
    crop: str | None = None
    start: str | None = None
    end: str | None = None


@app.post("/api/satellite")
def satellite_ep(req: SatelliteRequest) -> dict[str, Any]:
    """Field satellite analysis on Sentinel-2 (async: poll until status == 'done')."""
    from .engine import satellite_service

    if req.polygon and len(req.polygon) > 400:
        raise HTTPException(422, "polygon too complex (max 400 vertices)")
    return satellite_service.satellite_api(req.model_dump())


@app.get("/api/satellite/png/{key}/{name}.png", include_in_schema=False)
def satellite_png(key: str, name: str) -> Response:
    from .engine import satellite_service

    if name not in ("zones", "ndvi", "truecolor") or not key.isalnum():
        raise HTTPException(404)
    p = satellite_service.png_path(key, name)
    if p is None:
        raise HTTPException(404)
    return Response(
        p.read_bytes(), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
    )


class DetectRequest(BaseModel):
    lat: float = Field(ge=-60, le=75)
    lon: float = Field(ge=-180, le=180)
    source: Literal["esri", "naip"] | None = None


@app.post("/api/fields/detect")
def detect_ep(req: DetectRequest) -> dict[str, Any]:
    """Tap-to-detect: returns an editable field polygon around the tapped point."""
    from .engine import fields

    return fields.detect_field(req.lat, req.lon, req.source)


class PlannerRequest(BaseModel):
    lat: float = Field(ge=-60, le=75)
    lon: float = Field(ge=-180, le=180)
    crop: str
    planting_date: str
    irrigation: Irr = "sprinkler"
    water_allocation_mm: float | None = None
    as_of: str | None = None


@app.post("/api/planner")
def planner_ep(req: PlannerRequest) -> dict[str, Any]:
    """Season planner: sowing-date scan, stage dates, operations timeline, monthly water budget, risk calendar."""
    from .engine import planner

    _check_crop(req.crop)
    return planner.planner_api(req.model_dump())


class TerrainRequest(BaseModel):
    lat: float = Field(ge=-60, le=60)
    lon: float = Field(ge=-180, le=180)
    crop: str = "maize"
    polygon: list[list[float]] | None = None


@app.post("/api/terrain")
def terrain_ep(req: TerrainRequest) -> dict[str, Any]:
    """Computed terrain maps around the field: elevation, slope, RUSLE erosion, wetness, frost hollows, zones."""
    from .engine import maps

    _check_crop(req.crop)
    return maps.terrain_api(req.model_dump())


@app.get("/api/terrain/png/{key}/{layer}.png", include_in_schema=False)
def terrain_png(key: str, layer: str) -> Response:
    from .engine import maps

    data = maps.get_png(key, layer)
    if data is None:
        raise HTTPException(404, "map expired; request /api/terrain again")
    return Response(data, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


# --------------------------------------------------------------------------- static web app (single-container deploy)
_WEB_DIR = os.environ.get("FIELDSHIFT_WEB_DIR")
if _WEB_DIR and os.path.isdir(_WEB_DIR):
    from pathlib import Path

    from fastapi.responses import FileResponse

    _web_root = Path(_WEB_DIR).resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str) -> FileResponse:
        """Serve the exported Expo web build with SPA fallback (mirrors nginx try_files $uri $uri.html /index.html)."""
        if path.startswith("api/"):
            raise HTTPException(404)
        for cand in (_web_root / path, _web_root / f"{path}.html", _web_root / path / "index.html"):
            try:
                c = cand.resolve()
            except OSError:
                continue
            if c.is_file() and _web_root in c.parents:
                return FileResponse(c)
        return FileResponse(_web_root / "index.html")
