"""Thread 2: day-ahead plant-level yield forecast.

Leakage discipline: forecasting the day after as_of may only use lagged
actual yield from days <= as_of, calendar position, and a *forecast*
irradiation figure — never that day's own measured weather. Forecast
irradiation is synthetic (actual irradiation + ~15% relative Gaussian
noise, calibrated to typical day-ahead solar-forecast error) since real
archived forecasts weren't available for this date range — stated
simplification, not real forecast data.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from .data import load_plant

FORECAST_NOISE_SIGMA = 0.15
RNG_SEED = 42
FEATURES = ["FORECAST_IRRADIATION", "LAG_1", "LAG_2", "ROLLING_MEAN_3", "DAY_INDEX"]

_cache: dict[int, pd.DataFrame] = {}


def get_daily_data(plant: int) -> pd.DataFrame:
    if plant in _cache:
        return _cache[plant]

    df = load_plant(plant)
    df = df.copy()
    df["DATE"] = df["DATE_TIME"].dt.date
    daily = df.groupby("DATE").agg(
        AC_ENERGY_KWH=("AC_POWER", lambda s: s.sum() * 0.25 / 1000),
        IRRADIATION_SUM=("IRRADIATION", "sum"),
    ).reset_index()
    daily["DATE"] = pd.to_datetime(daily["DATE"])
    daily = daily.sort_values("DATE").reset_index(drop=True)

    rng = np.random.default_rng(RNG_SEED)
    noise = rng.normal(0.0, FORECAST_NOISE_SIGMA, size=len(daily))
    daily["FORECAST_IRRADIATION"] = (daily["IRRADIATION_SUM"] * (1 + noise)).clip(lower=0)
    daily["LAG_1"] = daily["AC_ENERGY_KWH"].shift(1)
    daily["LAG_2"] = daily["AC_ENERGY_KWH"].shift(2)
    daily["ROLLING_MEAN_3"] = daily["AC_ENERGY_KWH"].shift(1).rolling(3).mean()
    daily["DAY_INDEX"] = np.arange(len(daily))
    daily["PERSISTENCE"] = daily["AC_ENERGY_KWH"].shift(1)
    daily["CLIMATOLOGY"] = daily["AC_ENERGY_KWH"].shift(1).expanding().mean()

    _cache[plant] = daily
    return daily


def forecast_series(plant: int, as_of: pd.Timestamp) -> dict:
    daily = get_daily_data(plant)
    history_mask = daily["DATE"] <= as_of
    train = daily[history_mask].dropna(subset=FEATURES + ["AC_ENERGY_KWH"])

    history = daily[history_mask][["DATE", "AC_ENERGY_KWH", "PERSISTENCE", "CLIMATOLOGY"]].copy()
    history["DATE"] = history["DATE"].dt.strftime("%Y-%m-%d")
    history = history.rename(columns={"DATE": "date", "AC_ENERGY_KWH": "actual_kwh",
                                       "PERSISTENCE": "persistence_kwh", "CLIMATOLOGY": "climatology_kwh"})
    history = history.round(1)
    history_records = history.astype(object).where(history.notna(), None).to_dict("records")

    if len(train) < 8:
        return {"history": history_records, "forecast_tomorrow_kwh": None, "insufficient_data": True}

    X_train, y_train = train[FEATURES], train["AC_ENERGY_KWH"]
    rf = RandomForestRegressor(n_estimators=200, max_depth=4, random_state=0)
    rf.fit(X_train, y_train)

    next_row = daily[daily["DATE"] == as_of + pd.Timedelta(days=1)]
    forecast_kwh = None
    if not next_row.empty and next_row[FEATURES].notna().all(axis=None):
        forecast_kwh = round(float(rf.predict(next_row[FEATURES])[0]), 1)

    return {
        "history": history_records,
        "forecast_tomorrow_kwh": forecast_kwh,
        "insufficient_data": False,
    }
