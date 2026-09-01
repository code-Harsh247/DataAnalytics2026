"""Thread 1: expected-power model + residual-based anomaly flagging.

Design note on "live" simulation: the expected-power model is fit ONCE on
the whole known history per plant (cached), not retrained per as_of request.
This mirrors how a real product would actually work — you wouldn't retrain
a fault-detection baseline on every request, just periodically (e.g.
monthly) — and it's cheap here because all 34 days already exist in the
CSVs; the "live" scrubber only controls how much of that history is
*revealed* to the summary/detail views, via as_of filtering, not what the
model was fit on.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, cross_val_predict

from .data import load_plant
from .solar_features import add_solar_features

FEATURES = ["IRRADIATION", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE", "SOLAR_ELEVATION"]
TARIFF_PER_KWH = 4.0  # assumed, illustrative — not a real published tariff
INTERVAL_HOURS = 0.25

_cache: dict[int, pd.DataFrame] = {}


def get_residual_data(plant: int) -> pd.DataFrame:
    if plant in _cache:
        return _cache[plant]

    df = load_plant(plant)
    df = add_solar_features(df, irradiation_col="IRRADIATION")
    df = df[df["SOLAR_ELEVATION"] > 5].dropna(subset=FEATURES + ["AC_POWER"]).copy()

    X, y = df[FEATURES].values, df["AC_POWER"].values
    rf = RandomForestRegressor(n_estimators=200, max_depth=10, random_state=0, n_jobs=-1)
    df["EXPECTED_AC_POWER"] = cross_val_predict(rf, X, y, cv=KFold(5, shuffle=True, random_state=0))
    df["RESIDUAL"] = df["AC_POWER"] - df["EXPECTED_AC_POWER"]

    _cache[plant] = df
    return df


def _as_of_filter(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    return df[df["DATE_TIME"].dt.date <= as_of.date()]


def inverter_summary(plant: int, as_of: pd.Timestamp) -> list[dict]:
    df = _as_of_filter(get_residual_data(plant), as_of)
    if df.empty:
        return []

    by_inv = df.groupby("SOURCE_KEY")
    means = by_inv["RESIDUAL"].mean()
    std = means.std() or 1.0

    rows = []
    for source_key, grp in by_inv:
        mean_residual = grp["RESIDUAL"].mean()
        z = (mean_residual - means.mean()) / std
        loss_kwh = grp["RESIDUAL"].clip(upper=0).abs().sum() * INTERVAL_HOURS / 1000
        status = "at_risk" if z < -1.5 else ("watch" if z < -1.0 else "healthy")
        rows.append({
            "source_key": source_key,
            "status": status,
            "mean_residual": round(float(mean_residual), 2),
            "z_score": round(float(z), 2),
            "est_kwh_lost": round(float(loss_kwh), 2),
            "est_revenue_lost": round(float(loss_kwh * TARIFF_PER_KWH), 2),
        })
    rows.sort(key=lambda r: r["z_score"])
    return rows


def inverter_detail(plant: int, source_key: str, as_of: pd.Timestamp) -> dict:
    df = _as_of_filter(get_residual_data(plant), as_of)
    df = df[df["SOURCE_KEY"] == source_key]
    if df.empty:
        return {"source_key": source_key, "points": [], "daily_severity": []}

    points = [
        {"irradiation": round(float(r.IRRADIATION), 4), "residual": round(float(r.RESIDUAL), 2)}
        for r in df.itertuples()
    ]

    daily = df.groupby(df["DATE_TIME"].dt.date)["RESIDUAL"].mean().reset_index()
    daily.columns = ["date", "mean_residual"]
    daily["date"] = daily["date"].astype(str)
    daily["mean_residual"] = daily["mean_residual"].round(2)

    return {
        "source_key": source_key,
        "points": points,
        "daily_severity": daily.to_dict("records"),
    }


def daily_plant_trend(plant: int, as_of: pd.Timestamp) -> pd.DataFrame:
    """Plant-level actual vs expected daily energy (kWh), summed across
    inverters — a byproduct of the Thread 1 model, reused for the overview."""
    df = _as_of_filter(get_residual_data(plant), as_of)
    if df.empty:
        return pd.DataFrame(columns=["date", "actual_kwh", "expected_kwh"])

    daily = df.groupby(df["DATE_TIME"].dt.date).agg(
        actual_kwh=("AC_POWER", lambda s: s.sum() * INTERVAL_HOURS / 1000),
        expected_kwh=("EXPECTED_AC_POWER", lambda s: s.sum() * INTERVAL_HOURS / 1000),
    ).reset_index()
    daily.columns = ["date", "actual_kwh", "expected_kwh"]
    daily["date"] = daily["date"].astype(str)
    daily["actual_kwh"] = daily["actual_kwh"].round(1)
    daily["expected_kwh"] = daily["expected_kwh"].round(1)
    return daily
