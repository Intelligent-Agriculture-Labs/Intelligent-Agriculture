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
