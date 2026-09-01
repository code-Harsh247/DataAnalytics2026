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
from scipy import stats
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, cross_val_predict

from .data import load_plant
from .solar_features import add_solar_features

FEATURES = ["IRRADIATION", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE", "SOLAR_ELEVATION"]
TARIFF_PER_KWH = 4.0  # assumed, illustrative — not a real published tariff
INTERVAL_HOURS = 0.25

# Trend-based risk scoring (Phase 3). NOT true predictive maintenance — this
# dataset has no historical failure/repair labels to learn from. Instead this
# extrapolates a inverter's *recent anomaly-severity trend*, and is honest
# about it: empirically, Plant 2's flagged inverters show weak, mostly
# insignificant slopes (correlation 0.03-0.21 over the 34-day window) — i.e.
# chronic, stable underperformance, NOT a worsening trend. The threshold below
# is deliberately lenient (p<0.10, not the usual 0.05) given only ~34 points,
# and even so most inverters classify as "stable" rather than "worsening" —
# that's the honest result, not a bug to tune away.
TREND_P_THRESHOLD = 0.10
TREND_SLOPE_THRESHOLD = 5.0  # minimum |slope| (residual/day) to call it a real trend, not noise
CRITICAL_RESIDUAL = -300.0  # illustrative severity threshold for a projected inspection window


def _classify_trend(daily_severity: list[dict]) -> dict:
    if len(daily_severity) < 5:
        return {"trend": "insufficient_data", "slope_per_day": None, "p_value": None,
                "projected_days_to_critical": None}

    y = np.array([d["mean_residual"] for d in daily_severity])
    x = np.arange(len(y))
    slope, intercept, r, p, se = stats.linregress(x, y)

    if p < TREND_P_THRESHOLD and slope < -TREND_SLOPE_THRESHOLD:
        trend = "worsening"
    elif p < TREND_P_THRESHOLD and slope > TREND_SLOPE_THRESHOLD:
        trend = "improving"
    else:
        trend = "stable"

    projected_days = None
    if trend == "worsening" and y[-1] > CRITICAL_RESIDUAL:
        projected_days = round(float((CRITICAL_RESIDUAL - y[-1]) / slope))

    return {
        "trend": trend,
        "slope_per_day": round(float(slope), 2),
        "p_value": round(float(p), 3),
        "projected_days_to_critical": projected_days,
    }


def _daily_severity(grp: pd.DataFrame) -> list[dict]:
    daily = grp.groupby(grp["DATE_TIME"].dt.date)["RESIDUAL"].mean().reset_index()
    daily.columns = ["date", "mean_residual"]
    daily["date"] = daily["date"].astype(str)
    daily["mean_residual"] = daily["mean_residual"].round(2)
    return daily.to_dict("records")

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
        rows.append(_inverter_row(source_key, grp, means, std))
    rows.sort(key=lambda r: r["z_score"])
    return rows


def _status_from_z(z: float) -> str:
    return "at_risk" if z < -1.5 else ("watch" if z < -1.0 else "healthy")


def _inverter_row(source_key: str, grp: pd.DataFrame, means: pd.Series, std: float) -> dict:
    mean_residual = grp["RESIDUAL"].mean()
    z = (mean_residual - means.mean()) / std
    loss_kwh = grp["RESIDUAL"].clip(upper=0).abs().sum() * INTERVAL_HOURS / 1000
    trend_info = _classify_trend(_daily_severity(grp))
    return {
        "source_key": source_key,
        "status": _status_from_z(z),
        "mean_residual": round(float(mean_residual), 2),
        "z_score": round(float(z), 2),
        "est_kwh_lost": round(float(loss_kwh), 2),
        "est_revenue_lost": round(float(loss_kwh * TARIFF_PER_KWH), 2),
        "trend": trend_info["trend"],
        "projected_days_to_critical": trend_info["projected_days_to_critical"],
    }


def inverter_detail(plant: int, source_key: str, as_of: pd.Timestamp) -> dict:
    all_df = _as_of_filter(get_residual_data(plant), as_of)
    df = all_df[all_df["SOURCE_KEY"] == source_key]
    if df.empty:
        return {"source_key": source_key, "points": [], "daily_severity": [],
                "status": None, "mean_residual": None, "z_score": None,
                "est_kwh_lost": None, "est_revenue_lost": None,
                "trend": "insufficient_data", "slope_per_day": None, "p_value": None,
                "projected_days_to_critical": None}

    means = all_df.groupby("SOURCE_KEY")["RESIDUAL"].mean()
    std = means.std() or 1.0
    summary_row = _inverter_row(source_key, df, means, std)

    points = [
        {"irradiation": round(float(r.IRRADIATION), 4), "residual": round(float(r.RESIDUAL), 2)}
        for r in df.itertuples()
    ]
    daily_severity = _daily_severity(df)
    trend_info = _classify_trend(daily_severity)

    return {
        **summary_row,
        "trend": trend_info["trend"],
        "projected_days_to_critical": trend_info["projected_days_to_critical"],
        "slope_per_day": trend_info["slope_per_day"],
        "p_value": trend_info["p_value"],
        "points": points,
        "daily_severity": daily_severity,
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
