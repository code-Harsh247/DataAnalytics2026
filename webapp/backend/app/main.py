import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import analysis, plant_analysis, plant_pages, plant_status
from .plant_data import AuthError, InsufficientData, NotFound, UserSupabase

app = FastAPI(title="Solar Plant Manager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/plants/analyze")
def analyze_plant(req: analysis.AnalyzeRequest):
    try:
        return analysis.analyze(req)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except requests.RequestException as e:
        raise HTTPException(502, f"Weather provider error: {e}")


# ---- A user's own plant (Contract 6): reads Supabase as the caller, so the
# ---- request must carry their access token.

def _call_as_user(authorization: str | None, fn):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing Authorization: Bearer <access token>")
    try:
        return fn(UserSupabase(authorization.split(" ", 1)[1]))
    except AuthError as e:
        raise HTTPException(401, str(e))
    except NotFound as e:
        raise HTTPException(404, str(e))
    except InsufficientData as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except requests.RequestException as e:
        raise HTTPException(502, f"Database error: {e}")


@app.post("/api/plants/{plant_id}/analyze")
def analyze_stored_plant(
    plant_id: str,
    req: plant_analysis.PlantAnalyzeRequest = plant_analysis.PlantAnalyzeRequest(),
    authorization: str | None = Header(default=None),
):
    return _call_as_user(authorization, lambda db: plant_analysis.analyze_stored(db, plant_id, req))


@app.get("/api/plants/{plant_id}/status")
def get_plant_status(plant_id: str, authorization: str | None = Header(default=None)):
    return _call_as_user(authorization, lambda db: plant_status.plant_status(db, plant_id))


# ---- The plant pages (Contract 7).

@app.get("/api/plants/{plant_id}/overview")
def get_plant_overview(plant_id: str, authorization: str | None = Header(default=None)):
    return _call_as_user(authorization, lambda db: plant_pages.overview(db, plant_id))


@app.get("/api/plants/{plant_id}/production")
def get_plant_production(plant_id: str, days: int = 30, authorization: str | None = Header(default=None)):
    days = max(7, min(days, 31))
    return _call_as_user(authorization, lambda db: plant_pages.production(db, plant_id, days))


@app.get("/api/plants/{plant_id}/forecast")
def get_plant_forecast(plant_id: str, authorization: str | None = Header(default=None)):
    return _call_as_user(authorization, lambda db: plant_pages.forecast_page(db, plant_id))


@app.get("/api/plants/{plant_id}/health")
def get_plant_health(plant_id: str, authorization: str | None = Header(default=None)):
    return _call_as_user(authorization, lambda db: plant_pages.health(db, plant_id))


@app.get("/api/plants/{plant_id}/finance")
def get_plant_finance(plant_id: str, authorization: str | None = Header(default=None)):
    return _call_as_user(authorization, lambda db: plant_pages.finance(db, plant_id))
