import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import fault_model, forecast_model, overview
from .data import load_plant

app = FastAPI(title="Solar Plant Manager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PLANTS = {
    1: {"id": 1, "name": "Plant 1", "description": "Healthy baseline plant"},
    2: {"id": 2, "name": "Plant 2", "description": "Plant with active maintenance flags"},
}


def _require_plant(plant_id: int) -> None:
    if plant_id not in PLANTS:
        raise HTTPException(404, f"Unknown plant {plant_id}")


def _parse_as_of(as_of: str) -> pd.Timestamp:
    try:
        return pd.Timestamp(as_of)
    except ValueError:
        raise HTTPException(400, f"Invalid as_of date: {as_of!r}")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/plants")
def list_plants():
    return list(PLANTS.values())


@app.get("/api/plants/{plant_id}/timeline")
def timeline(plant_id: int):
    _require_plant(plant_id)
    df = load_plant(plant_id)
    return {
        "start": df["DATE_TIME"].dt.date.min().isoformat(),
        "end": df["DATE_TIME"].dt.date.max().isoformat(),
    }


@app.get("/api/plants/{plant_id}/overview")
def get_overview(plant_id: int, as_of: str):
    _require_plant(plant_id)
    return overview.get_overview(plant_id, _parse_as_of(as_of))


@app.get("/api/plants/{plant_id}/inverters")
def get_inverters(plant_id: int, as_of: str):
    _require_plant(plant_id)
    return fault_model.inverter_summary(plant_id, _parse_as_of(as_of))


@app.get("/api/plants/{plant_id}/inverters/{source_key}")
def get_inverter_detail(plant_id: int, source_key: str, as_of: str):
    _require_plant(plant_id)
    return fault_model.inverter_detail(plant_id, source_key, _parse_as_of(as_of))


@app.get("/api/plants/{plant_id}/forecast")
def get_forecast(plant_id: int, as_of: str):
    _require_plant(plant_id)
    return forecast_model.forecast_series(plant_id, _parse_as_of(as_of))
