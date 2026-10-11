"""POST /api/plants/analyze: backfill a plant's recent history, run every
registered anomaly model on it, and summarize the chosen model's findings
for the dashboard. Stateless -- the dataset is generated in memory per
request and nothing is written to Supabase.

The dataset is synthetic with known fault labels (see backfill.py), which is
what makes the per-model precision/recall in `comparison` possible at all.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from .backfill import ARCHIVE_LAG_DAYS, build_dataset
from .models import get_registry
from .models.base import add_peer_features
from .models.evaluate import fit_and_score, time_split
from .synthetic_generation import DEFAULT_TEMP_COEFFICIENT

ANALYSIS_SEED = 42
FALLBACK_MODEL = "random_forest"  # default when the test window has no faults to score  # fixed, so re-running the same plant gives the same answer
CRITICAL_FLAGGED_SHARE = 0.10
WARNING_FLAGGED_SHARE = 0.03


class AnalyzeRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    capacity_kw: float = Field(gt=0)
    tilt_degrees: float = Field(ge=0, le=90)
    azimuth_degrees: float = Field(ge=0, le=360)
    temp_coefficient: float = DEFAULT_TEMP_COEFFICIENT
    degradation_factor: float = Field(default=1.0, gt=0, le=1)
    # Peer comparison needs at least two inverters.
    inverter_count: int = Field(default=4, ge=2, le=20)
    tariff_per_kwh: float = Field(default=0.0, ge=0)
    # Below ~3 weeks the held-out window often contains no faults at all,
    # leaving nothing to score the models against.
    days: int = Field(default=30, ge=21, le=90)
    model: str | None = None


def _iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(x: float, digits: int = 3) -> float | None:
    return None if pd.isna(x) else round(float(x), digits)


def _inverter_summary(pred: pd.DataFrame, tariff: float) -> list[dict]:
    day = pred[pred["is_daylight"]]
    # Isolation Forest has no expected_kw; fall back to the peer median as the
    # "what it should have made" reference for estimating lost energy.
    reference = day["expected_kw"].fillna(day["peer_median_kw"])
    lost_kw = (reference - day["ac_power_kw"]).clip(lower=0).where(day["flagged"], 0.0)
    day = day.assign(lost_kwh=lost_kw)  # hourly rows: kW over 1h = kWh

    summary = []
    for label, g in day.groupby("inverter"):
        flagged_hours = int(g["flagged"].sum())
        share = flagged_hours / max(len(g), 1)
        status = (
            "critical" if share >= CRITICAL_FLAGGED_SHARE
            else "warning" if share >= WARNING_FLAGGED_SHARE
            else "healthy"
        )
        kwh_lost = float(g["lost_kwh"].sum())
        summary.append({
            "label": label,
            "flagged_hours": flagged_hours,
            "true_fault_hours": int(g["is_fault"].sum()),
            "est_kwh_lost": round(kwh_lost, 3),
            "est_revenue_lost": round(kwh_lost * tariff, 2),
            "status": status,
        })
    return summary


def _plant_series(pred: pd.DataFrame) -> list[dict]:
    grouped = pred.groupby("timestamp").agg(
        actual_kw=("ac_power_kw", "sum"),
        expected_kw=("expected_kw", lambda s: s.sum() if s.notna().all() else np.nan),
        flagged=("flagged", "any"),
        true_fault=("is_fault", "any"),
    )
    return [
        {
            "timestamp": _iso(ts),
            "actual_kw": _num(row.actual_kw),
            "expected_kw": _num(row.expected_kw),
            "flagged": bool(row.flagged),
            "true_fault": bool(row.true_fault),
        }
        for ts, row in grouped.iterrows()
    ]


def analyze(req: AnalyzeRequest) -> dict:
    registry = get_registry()
    if req.model is not None and req.model not in registry:
        raise ValueError(f"Unknown model '{req.model}'. Available: {sorted(registry)}")

    end = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    start = end - timedelta(days=req.days - 1)
    df = build_dataset(
        req.lat, req.lon, str(start), str(end),
        capacity_kw=req.capacity_kw, tilt=req.tilt_degrees, azimuth=req.azimuth_degrees,
        inverter_count=req.inverter_count, temp_coefficient=req.temp_coefficient,
        degradation_factor=req.degradation_factor, seed=ANALYSIS_SEED,
    )
    train, test = time_split(df)

    comparison, predictions = [], {}
    for name in sorted(registry):
        metrics, pred = fit_and_score(registry[name](), train, test)
        comparison.append(metrics)
        predictions[name] = pred
    comparison.sort(key=lambda m: -1 if m["f1"] is None else m["f1"], reverse=True)

    best = comparison[0]["model"] if comparison[0]["f1"] is not None else None
    chosen = req.model or best or (FALLBACK_MODEL if FALLBACK_MODEL in registry else comparison[0]["model"])
    pred = predictions[chosen]
    pred = pred.join(add_peer_features(test)["peer_median_kw"])

    energy_kwh = float(df["ac_power_kw"].sum())  # hourly rows
    return {
        "model": chosen,
        "period": {
            "start": _iso(df["timestamp"].min()),
            "end": _iso(df["timestamp"].max()),
            "test_start": _iso(test["timestamp"].min()),
            "test_fault_hours": int(test[test["is_daylight"]]["is_fault"].sum()),
        },
        "series": _plant_series(pred),
        "inverters": _inverter_summary(pred, req.tariff_per_kwh),
        "comparison": comparison,
        "totals": {
            "energy_kwh": round(energy_kwh, 2),
            "revenue": round(energy_kwh * req.tariff_per_kwh, 2),
        },
    }
