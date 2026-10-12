"""POST /api/plants/{plant_id}/analyze (Contract 6a): the 30-day analysis on
the readings actually stored for this plant -- the same data its dashboard
shows -- instead of a freshly generated month.

Same time split, models, metrics and response shape as Contract 3
(analysis.py, reused rather than modified), plus `source` and `coverage`.
The default model is fixed (DEFAULT_MODEL), not the best F1 of the run:
choosing by test-window score is selection on the test data.
"""

import pandas as pd
from pydantic import BaseModel, Field

from .analysis import _inverter_summary, _iso, _plant_series
from .models import get_registry
from .models.base import add_peer_features
from .models.evaluate import fit_and_score, time_split
from .plant_data import InsufficientData, UserSupabase, load_hourly

DEFAULT_MODEL = "random_forest"  # chosen once on the canonical benchmark (FINDINGS.md section 1)
MIN_DAYS = 7
MIN_DAYLIGHT_HOURS_PER_INVERTER = 40


class PlantAnalyzeRequest(BaseModel):
    days: int = Field(default=30, ge=MIN_DAYS, le=90)
    model: str | None = None


def analyze_stored(db: UserSupabase, plant_id: str, req: PlantAnalyzeRequest) -> dict:
    registry = get_registry()
    if req.model is not None and req.model not in registry:
        raise ValueError(f"Unknown model '{req.model}'. Available: {sorted(registry)}")

    plant = db.plant(plant_id)
    inverters = db.inverters(plant_id)
    if len(inverters) < 2:
        raise InsufficientData("Analysis needs at least 2 inverters: each is compared with its peers.")

    now = pd.Timestamp.now(tz="UTC")
    since = (now - pd.Timedelta(days=req.days)).floor("h")
    df = load_hourly(db, plant, inverters, since)
    if df.empty:
        raise InsufficientData("No readings stored yet. Connect a gateway or wait for data to arrive.")

    span_days = (df["timestamp"].max() - df["timestamp"].min()) / pd.Timedelta(days=1)
    daylight_per_inverter = df["is_daylight"].sum() / len(inverters)
    if span_days < MIN_DAYS or daylight_per_inverter < MIN_DAYLIGHT_HOURS_PER_INVERTER:
        raise InsufficientData(
            f"Only {span_days:.1f} days of readings stored; the analysis needs at least {MIN_DAYS}.")

    train, test = time_split(df)
    comparison, predictions = [], {}
    for name in sorted(registry):
        metrics, pred = fit_and_score(registry[name](), train, test)
        comparison.append(metrics)
        predictions[name] = pred
    comparison.sort(key=lambda m: -1 if m["f1"] is None else m["f1"], reverse=True)

    chosen = req.model or (DEFAULT_MODEL if DEFAULT_MODEL in registry else comparison[0]["model"])
    pred = predictions[chosen].join(add_peer_features(test)["peer_median_kw"])

    tariff = plant.get("tariff_per_kwh") or 0.0
    energy_kwh = float(df["ac_power_kw"].sum())  # hourly means: kW over 1 h = kWh
    expected_rows = int((now.floor("h") - since) / pd.Timedelta(hours=1)) * len(inverters)
    return {
        "model": chosen,
        "source": "stored",
        "period": {
            "start": _iso(df["timestamp"].min()),
            "end": _iso(df["timestamp"].max()),
            "test_start": _iso(test["timestamp"].min()),
            "test_fault_hours": int(test[test["is_daylight"]]["is_fault"].sum()),
        },
        "coverage": {"expected_rows": expected_rows, "present_rows": int(len(df))},
        "series": _plant_series(pred),
        "inverters": _inverter_summary(pred, tariff),
        "comparison": comparison,
        "totals": {"energy_kwh": round(energy_kwh, 2), "revenue": round(energy_kwh * tariff, 2)},
    }
