"""Phase 4 — Thread 1: fault/anomaly detection via expected-power residuals.

Approach: train one "expected AC power given actual weather" model per plant,
pooled across all inverters (weather is plant-level, shared by every inverter
at a given timestamp). Out-of-fold residual = actual - expected. An inverter
that's persistently below its expected output — controlling for whatever the
weather was doing at the time — is a fault/underperformance candidate, not
just "had a below-average day."

Run: .venv/Scripts/python.exe src/fault_detection.py
"""

import sys
from pathlib import Path

import matplotlib
if "ipykernel" not in sys.modules:
    # Agg avoids a Tk/threading crash when run as a background script (RandomForest's
    # n_jobs=-1 spawns threads that conflict with the interactive TkAgg backend).
    # Skip this under Jupyter so the notebook's own inline backend isn't clobbered.
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import cross_val_predict, KFold

from data_loader import load_plant
from solar_features import add_solar_features

FIG_DIR = Path(__file__).resolve().parent.parent / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

FEATURES = ["IRRADIATION", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE", "SOLAR_ELEVATION"]
TARIFF_PER_KWH = 4.0  # assumed INR/kWh, stated explicitly — not a real published tariff
INTERVAL_HOURS = 0.25  # 15-minute readings


def build_plant_dataset(plant: int) -> pd.DataFrame:
    df = load_plant(plant)
    df = add_solar_features(df, irradiation_col="IRRADIATION")
    # Daytime only: nighttime rows are trivially AC_POWER=0 for every inverter
    # and would dominate the fit with an uninformative, easy-to-predict mass.
    df = df[df["SOLAR_ELEVATION"] > 5].dropna(subset=FEATURES + ["AC_POWER"])
    return df


def fit_expected_power(df: pd.DataFrame) -> tuple[np.ndarray, dict]:
    X = df[FEATURES].values
    y = df["AC_POWER"].values

    lr = LinearRegression()
    lr_pred = cross_val_predict(lr, X, y, cv=KFold(5, shuffle=True, random_state=0))

    rf = RandomForestRegressor(n_estimators=200, max_depth=10, random_state=0, n_jobs=-1)
    rf_pred = cross_val_predict(rf, X, y, cv=KFold(5, shuffle=True, random_state=0))

    metrics = {
        "linear_r2": r2_score(y, lr_pred),
        "linear_mae": mean_absolute_error(y, lr_pred),
        "rf_r2": r2_score(y, rf_pred),
        "rf_mae": mean_absolute_error(y, rf_pred),
    }
    return rf_pred, metrics


def analyze_plant(plant: int) -> pd.DataFrame:
    print(f"\n{'=' * 60}\nPlant {plant} — expected power model\n{'=' * 60}")
    df = build_plant_dataset(plant)
    expected, metrics = fit_expected_power(df)
    df = df.copy()
    df["EXPECTED_AC_POWER"] = expected
    df["RESIDUAL"] = df["AC_POWER"] - df["EXPECTED_AC_POWER"]

    print(f"Linear baseline: R2={metrics['linear_r2']:.3f}, MAE={metrics['linear_mae']:.1f}")
    print(f"Random Forest:   R2={metrics['rf_r2']:.3f}, MAE={metrics['rf_mae']:.1f}")

    by_inv = df.groupby("SOURCE_KEY")["RESIDUAL"].agg(["mean", "std", "count"])
    overall_std = by_inv["mean"].std()
    by_inv["z_score"] = (by_inv["mean"] - by_inv["mean"].mean()) / overall_std
    by_inv = by_inv.sort_values("mean")

    # Lost energy: only count negative residuals (underperformance), not
    # positive ones — the goal is to quantify shortfall, not net it against days
    # an inverter ran hot.
    loss_kwh = (
        df.assign(loss=df["RESIDUAL"].clip(upper=0).abs())
        .groupby("SOURCE_KEY")["loss"]
        .sum()
        * INTERVAL_HOURS
        / 1000  # AC_POWER units are ~kW-scale already per earlier EDA; keep consistent
    )
    by_inv["est_kwh_lost"] = loss_kwh
    by_inv["est_revenue_lost"] = loss_kwh * TARIFF_PER_KWH

    flagged = by_inv[by_inv["z_score"] < -1.5]
    print(f"\nFlagged inverters (z-score < -1.5): {len(flagged)} of {len(by_inv)}")
    print(by_inv.round(2))

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["crimson" if z < -1.5 else "steelblue" for z in by_inv["z_score"]]
    ax.bar(range(len(by_inv)), by_inv["mean"], color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(range(len(by_inv)))
    ax.set_xticklabels(by_inv.index, rotation=90, fontsize=7)
    ax.set_ylabel("Mean residual (actual - expected AC power)")
    ax.set_title(f"Plant {plant} — expected-power residuals by inverter (red = flagged)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"plant{plant}_residuals.png", dpi=120)
    plt.close(fig)

    if len(flagged):
        fig, ax = plt.subplots(figsize=(8, 5))
        for inv in flagged.index:
            sub = df[df["SOURCE_KEY"] == inv]
            ax.scatter(sub["IRRADIATION"], sub["RESIDUAL"], s=4, alpha=0.3, label=inv[:8])
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Irradiation")
        ax.set_ylabel("Residual")
        ax.set_title(f"Plant {plant} — flagged inverters: residual vs irradiance\n"
                     f"(proportional loss = fans out with irradiance; fixed offset = flat band)")
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"plant{plant}_flagged_residual_pattern.png", dpi=120)
        plt.close(fig)

    total_loss = by_inv["est_revenue_lost"].sum()
    print(f"\nTotal estimated revenue lost (plant, period, assumed tariff="
          f"{TARIFF_PER_KWH}/kWh): {total_loss:,.0f}")

    return by_inv


if __name__ == "__main__":
    for plant in (1, 2):
        analyze_plant(plant)
