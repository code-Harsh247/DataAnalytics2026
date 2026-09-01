"""Phase 5 — Thread 2: day-ahead plant-level yield forecasting.

Scope decision (see tasks.md): whole-plant daily total yield, not per-inverter
or hourly — keeps this thread tractable given the dataset only covers ~34 days.

Leakage discipline: forecasting day D's yield may only use information that
would actually have been available the evening before, i.e. lagged actual
yield from days < D, calendar features, and a *forecast* irradiation figure —
never D's own measured irradiance/temperature.

Forecast irradiation is synthetic (see tasks.md Phase 0 decision): actual daily
irradiation + Gaussian noise calibrated to a ~15% relative error, which is in
the range reported for real day-ahead solar irradiance forecasts. This is a
stated simplification, not real forecast data.
"""

import sys
from pathlib import Path

import matplotlib
if "ipykernel" not in sys.modules:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score

from data_loader import load_plant

FIG_DIR = Path(__file__).resolve().parent.parent / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

FORECAST_NOISE_SIGMA = 0.15  # relative, ~typical day-ahead irradiance forecast error
RNG_SEED = 42
TEST_DAYS = 7


def daily_aggregate(plant: int) -> pd.DataFrame:
    df = load_plant(plant)
    df["DATE"] = df["DATE_TIME"].dt.date
    daily = df.groupby("DATE").agg(
        AC_ENERGY_KWH=("AC_POWER", lambda s: s.sum() * 0.25 / 1000),
        IRRADIATION_SUM=("IRRADIATION", "sum"),
        AMBIENT_TEMP_MEAN=("AMBIENT_TEMPERATURE", "mean"),
    ).reset_index()
    daily["DATE"] = pd.to_datetime(daily["DATE"])
    daily = daily.sort_values("DATE").reset_index(drop=True)
    return daily


def add_forecast_features(daily: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED)
    out = daily.copy()

    noise = rng.normal(loc=0.0, scale=FORECAST_NOISE_SIGMA, size=len(out))
    out["FORECAST_IRRADIATION"] = (out["IRRADIATION_SUM"] * (1 + noise)).clip(lower=0)

    out["LAG_1"] = out["AC_ENERGY_KWH"].shift(1)
    out["LAG_2"] = out["AC_ENERGY_KWH"].shift(2)
    out["ROLLING_MEAN_3"] = out["AC_ENERGY_KWH"].shift(1).rolling(3).mean()
    out["DAY_INDEX"] = np.arange(len(out))

    # Expanding-window climatology baseline: mean of all *prior* days only.
    out["CLIMATOLOGY"] = out["AC_ENERGY_KWH"].shift(1).expanding().mean()
    out["PERSISTENCE"] = out["AC_ENERGY_KWH"].shift(1)

    return out


FEATURES = ["FORECAST_IRRADIATION", "LAG_1", "LAG_2", "ROLLING_MEAN_3", "DAY_INDEX"]


def evaluate_plant(plant: int) -> dict:
    print(f"\n{'=' * 60}\nPlant {plant} — day-ahead yield forecast\n{'=' * 60}")
    daily = daily_aggregate(plant)
    feat = add_forecast_features(daily).dropna(subset=FEATURES + ["AC_ENERGY_KWH"])
    print(f"Usable days after lag/rolling warmup: {len(feat)} "
          f"(out of {len(daily)} total days)")

    if len(feat) < TEST_DAYS + 5:
        print("WARNING: very small sample — results are illustrative, not robust.")

    train = feat.iloc[: -TEST_DAYS]
    test = feat.iloc[-TEST_DAYS:]

    X_train, y_train = train[FEATURES], train["AC_ENERGY_KWH"]
    X_test, y_test = test[FEATURES], test["AC_ENERGY_KWH"]

    lr = LinearRegression().fit(X_train, y_train)
    lr_pred = lr.predict(X_test)

    rf = RandomForestRegressor(n_estimators=200, max_depth=4, random_state=0)
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)

    preds = {
        "persistence": test["PERSISTENCE"].values,
        "climatology": test["CLIMATOLOGY"].values,
        "linear_regression": lr_pred,
        "random_forest": rf_pred,
    }

    results = {}
    for name, pred in preds.items():
        rmse = np.sqrt(np.mean((y_test.values - pred) ** 2))
        mae = mean_absolute_error(y_test, pred)
        mape = mean_absolute_percentage_error(y_test, pred)
        results[name] = {"rmse": rmse, "mae": mae, "mape": mape}
        print(f"  {name:18s} RMSE={rmse:8.2f}  MAE={mae:8.2f}  MAPE={mape:6.1%}")

    best_ml = min(("linear_regression", "random_forest"), key=lambda k: results[k]["rmse"])
    beats_persistence = results[best_ml]["rmse"] < results["persistence"]["rmse"]
    print(f"\n  Best ML model ({best_ml}) beats persistence: {beats_persistence}")

    importances = pd.Series(rf.feature_importances_, index=FEATURES).sort_values(ascending=False)
    print(f"\n  Random Forest feature importances:\n{importances.round(3)}")

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(test["DATE"], y_test.values, "k-o", label="actual")
    for name in ("persistence", "climatology", "random_forest"):
        ax.plot(test["DATE"], preds[name], "--o", label=name, alpha=0.7)
    ax.set_ylabel("Daily AC energy (kWh)")
    ax.set_title(f"Plant {plant} — day-ahead forecast vs actual (last {TEST_DAYS} days)")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"plant{plant}_forecast.png", dpi=120)
    plt.close(fig)

    return results


if __name__ == "__main__":
    for plant in (1, 2):
        evaluate_plant(plant)
