"""A4: exploratory analysis of the benchmark data and the expected-power model.

On the canonical dataset (seed 42) unless noted:
- data profile (size, coverage, daylight and fault shares)
- power vs plane-of-array irradiance, coloured by cell temperature
- the temperature effect: efficiency vs cell temperature, and the
  temperature coefficient recovered from the data by regression
- the average daily profile (plant-local time)
- correlations between the model's inputs and output
- residuals (relative shortfall) of the Random Forest, healthy vs faulted
  hours, pooled over seeds 1-8, with the label-free threshold
- permutation importance of the Random Forest's inputs

    python -m analysis.eda
"""

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from app.models.base import LABEL_COLUMNS, WEATHER_FEATURES
from app.models.evaluate import time_split
from app.models.random_forest import FEATURES, RandomForestModel, _prepare
from app.synthetic_generation import INVERTER_EFFICIENCY

from .common import COLORS, OUT, canonical_args, dataset, save, write_json

TZ = "Asia/Kolkata"  # 80 E


def profile(df: pd.DataFrame) -> dict:
    day = df[df["is_daylight"]]
    return {
        "rows": int(len(df)), "inverters": int(df["inverter"].nunique()),
        "hours": int(df["timestamp"].nunique()),
        "from": str(df["timestamp"].min()), "to": str(df["timestamp"].max()),
        "daylight_share": round(float(df["is_daylight"].mean()), 3),
        "faulted_daylight_share": round(float(day["is_fault"].mean()), 3),
        "missing_values": int(df.isna().sum().sum()),
        "ac_power_kw": {k: round(float(v), 3) for k, v in day["ac_power_kw"].describe().items()},
        "poa_wm2": {k: round(float(v), 1) for k, v in day["poa_irradiance"].describe().items()},
        "cell_temp_c": {k: round(float(v), 1) for k, v in day["cell_temp"].describe().items()},
    }


def _coefficient(healthy: pd.DataFrame, per_inverter_kw: float) -> tuple[float, float, float, pd.DataFrame, pd.Series]:
    bright = healthy[healthy["poa_irradiance"] > 300]
    eff = bright["ac_power_kw"] / (per_inverter_kw * bright["poa_irradiance"] / 1000 * INVERTER_EFFICIENCY)
    slope, intercept = np.polyfit(bright["cell_temp"], eff, 1)
    at_25 = intercept + slope * 25
    return float(slope / at_25), float(slope), float(at_25), bright, eff


def temperature_effect(healthy: pd.DataFrame, per_inverter_kw: float) -> dict:
    """Efficiency = AC / (rated x POA/1000 x inverter efficiency); its slope
    against cell temperature, normalised at 25 C, is the temperature
    coefficient. Fit on bright, healthy hours only (low sun is noisy). A
    day-block bootstrap gives its uncertainty; seeds 1-8 show its spread."""
    coef, slope, at_25, bright, eff = _coefficient(healthy, per_inverter_kw)
    rng = np.random.default_rng(0)
    days = bright["timestamp"].dt.date.to_numpy()
    unique_days = np.unique(days)
    rows_by_day = {d: np.where(days == d)[0] for d in unique_days}
    boot = []
    for _ in range(1000):
        idx = np.concatenate([rows_by_day[d] for d in rng.choice(unique_days, len(unique_days))])
        s = np.polyfit(bright["cell_temp"].to_numpy()[idx], eff.to_numpy()[idx], 1)
        boot.append(s[0] / np.polyval(s, 25))
    per_seed = []
    for seed in range(1, 9):
        d = dataset(seed)
        per_seed.append(_coefficient(d[d["is_daylight"] & ~d["is_fault"]], per_inverter_kw)[0])
    return {"rows": int(len(bright)), "slope_per_c": slope, "efficiency_at_25c": at_25,
            "coefficient_per_c": round(coef, 5),
            "ci95": [round(float(x), 5) for x in np.quantile(boot, [0.025, 0.975])],
            "seeds_1_8_mean": round(float(np.mean(per_seed)), 5),
            "configured": canonical_args()["temp_coefficient"], "efficiency": eff, "cell_temp": bright["cell_temp"]}


def figures(df: pd.DataFrame, healthy: pd.DataFrame, temp: dict, importance: pd.Series) -> dict:
    import matplotlib.pyplot as plt

    paths = {}
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    sc = ax.scatter(healthy["poa_irradiance"], healthy["ac_power_kw"], c=healthy["cell_temp"], s=4, cmap="inferno", alpha=0.7)
    fig.colorbar(sc, ax=ax, label="cell temperature, °C")
    ax.set_xlabel("sunlight on the panels (POA), W/m²")
    ax.set_ylabel("AC power per inverter, kW")
    ax.set_title("Healthy daylight hours, seed 42")
    paths["power_vs_irradiance"] = save(fig, "power_vs_irradiance")

    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    ax.scatter(temp["cell_temp"], temp["efficiency"], s=4, alpha=0.4, color=COLORS["random_forest"])
    xs = np.linspace(temp["cell_temp"].min(), temp["cell_temp"].max(), 10)
    ax.plot(xs, temp["efficiency_at_25c"] + temp["slope_per_c"] * (xs - 25), color="#dc2626",
            label=f"fit: {temp['coefficient_per_c'] * 100:.2f}%/°C (configured {temp['configured'] * 100:.2f}%/°C)")
    ax.set_xlabel("cell temperature, °C")
    ax.set_ylabel("output ÷ rated output for the sunlight")
    ax.legend(fontsize=7)
    paths["temperature_effect"] = save(fig, "temperature_effect")

    local = df.assign(hour=(df["timestamp"] - pd.Timedelta(minutes=30)).dt.tz_convert(TZ).dt.hour)
    by_hour = local.groupby("hour")[["ac_power_kw", "poa_irradiance"]].mean()
    fig, ax = plt.subplots(figsize=(4.8, 2.8))
    ax.plot(by_hour.index, by_hour["ac_power_kw"] * df["inverter"].nunique(), "o-", color=COLORS["random_forest"], label="plant AC power")
    ax.set_xlabel("hour of day (local)")
    ax.set_ylabel("mean plant power, kW")
    ax2 = ax.twinx()
    ax2.plot(by_hour.index, by_hour["poa_irradiance"], "--", color="#f59e0b", label="sunlight (POA)")
    ax2.set_ylabel("W/m²")
    ax2.grid(False)
    fig.legend(fontsize=7, loc="upper left", bbox_to_anchor=(0.12, 0.88))
    paths["daily_profile"] = save(fig, "daily_profile")

    cols = WEATHER_FEATURES + ["ac_power_kw"]
    corr = healthy[cols].corr()
    fig, ax = plt.subplots(figsize=(4.8, 4.0))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), cols, rotation=60, ha="right", fontsize=7)
    ax.set_yticks(range(len(cols)), cols, fontsize=7)
    ax.grid(False)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{corr.iloc[i, j]:.1f}", ha="center", va="center", fontsize=6)
    fig.colorbar(im, ax=ax)
    paths["correlations"] = save(fig, "correlations")

    fig, ax = plt.subplots(figsize=(4.8, 2.6))
    importance = importance.sort_values()
    ax.barh(importance.index, importance.to_numpy(), color=COLORS["random_forest"])
    ax.set_xlabel("drop in R² when the input is shuffled")
    ax.set_title("What the expected-power model relies on")
    paths["feature_importance"] = save(fig, "feature_importance")
    return paths


def residual_figure(threshold: float) -> tuple[str, dict]:
    """Relative shortfall of Random Forest predictions, pooled over seeds 1-8
    (from model_stats' cached predictions)."""
    import matplotlib.pyplot as plt

    path = OUT / "predictions.csv"
    if not path.exists():
        from .model_stats import pooled_predictions
        pooled_predictions()
    preds = pd.read_csv(path)
    rf = preds[(preds["model"] == "random_forest") & preds["is_daylight"]]
    healthy, faulted = rf[~rf["is_fault"]]["anomaly_score"], rf[rf["is_fault"]]["anomaly_score"]
    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    bins = np.linspace(-0.3, 0.6, 61)
    ax.hist(healthy.clip(-0.3, 0.6), bins=bins, alpha=0.7, density=True, color=COLORS["random_forest"], label=f"healthy hours ({len(healthy)})")
    ax.hist(faulted.clip(-0.3, 0.6), bins=bins, alpha=0.6, density=True, color="#dc2626", label=f"faulted hours ({len(faulted)})")
    ax.axvline(threshold, color="#111827", ls="--", lw=1, label=f"typical threshold ≈ {threshold:.2f}")
    ax.set_xlabel("relative shortfall vs expected (smoothed)")
    ax.set_ylabel("density")
    ax.legend(fontsize=7)
    stats = {"healthy_median": round(float(healthy.median()), 3), "faulted_median": round(float(faulted.median()), 3),
             "healthy_p95": round(float(healthy.quantile(0.95)), 3)}
    return save(fig, "residuals"), stats


def main() -> dict:
    df = dataset(42)
    healthy = df[df["is_daylight"] & ~df["is_fault"]]
    a = canonical_args()
    temp = temperature_effect(healthy, a["capacity_kw"] / a["inverters"])

    train, test = time_split(df)
    model = RandomForestModel()
    model.fit(train.drop(columns=LABEL_COLUMNS))
    test_healthy = _prepare(test[test["is_daylight"] & ~test["is_fault"]].drop(columns=LABEL_COLUMNS))
    imp = permutation_importance(model.forest, test_healthy[FEATURES], test_healthy["ac_power_kw"],
                                 scoring="r2", n_repeats=10, random_state=0)
    importance = pd.Series(imp.importances_mean, index=FEATURES)

    paths = figures(df, healthy, temp, importance)
    paths["residuals"], residual_stats = residual_figure(model.threshold)
    result = {
        "profile": profile(df),
        "temperature_coefficient": {k: v for k, v in temp.items() if k not in ("efficiency", "cell_temp")},
        "feature_importance_r2_drop": {k: round(float(v), 4) for k, v in importance.sort_values(ascending=False).items()},
        "rf_threshold_seed42": round(float(model.threshold), 3),
        "residuals": residual_stats,
        "figures": paths,
    }
    write_json("eda", result)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(main(), indent=1, default=str))
