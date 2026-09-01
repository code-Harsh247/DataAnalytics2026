"""Phase 2 EDA: generate summary stats + figures for both plants.

Run: .venv/Scripts/python.exe src/eda.py
Figures are saved to reports/figures/.
"""

import sys
from pathlib import Path

import matplotlib
if "ipykernel" not in sys.modules:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from data_loader import load_all

FIG_DIR = Path(__file__).resolve().parent.parent / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["figure.figsize"] = (10, 5)


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> None:
    df = load_all()

    section("Basic shape & date ranges")
    print(f"Total rows: {len(df):,}")
    for plant in (1, 2):
        sub = df[df["PLANT"] == plant]
        n_inverters = sub["SOURCE_KEY"].nunique()
        print(
            f"Plant {plant}: {len(sub):,} rows, {n_inverters} inverters, "
            f"{sub['DATE_TIME'].min()} to {sub['DATE_TIME'].max()}"
        )

    section("Missing weather data — concentrated or scattered?")
    missing = df[df["IRRADIATION"].isna()]
    print(f"Missing weather rows: {len(missing):,} ({len(missing) / len(df):.1%})")
    missing_by_time = missing.groupby(missing["DATE_TIME"].dt.floor("15min")).size()
    print(f"Distinct timestamps affected: {missing_by_time.shape[0]}")
    print(
        "-> If distinct timestamps << affected rows / inverters-per-timestamp, "
        "it's whole-timestamp sensor dropouts, not random noise."
    )

    section("Daily yield trend per plant")
    # AC_POWER, not DC_POWER — consistently scaled across plants (see note above).
    fig, ax = plt.subplots()
    for plant in (1, 2):
        sub = df[df["PLANT"] == plant]
        daily = sub.groupby(sub["DATE_TIME"].dt.date)["AC_POWER"].sum() / 1000
        ax.plot(daily.index, daily.values, label=f"Plant {plant}", marker="o", markersize=3)
    ax.set_ylabel("Total daily AC energy (kWh, arbitrary scale)")
    ax.set_title("Daily generation trend by plant")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "daily_trend.png", dpi=120)
    plt.close(fig)

    section("Average power curve by hour of day")
    fig, ax = plt.subplots()
    for plant in (1, 2):
        sub = df[df["PLANT"] == plant]
        hourly = sub.groupby(sub["DATE_TIME"].dt.hour)["AC_POWER"].mean()
        ax.plot(hourly.index, hourly.values, label=f"Plant {plant}", marker="o")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Mean AC power")
    ax.set_title("Average daily power curve")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "hourly_curve.png", dpi=120)
    plt.close(fig)

    section("Irradiation vs AC power correlation")
    for plant in (1, 2):
        sub = df[df["PLANT"] == plant].dropna(subset=["IRRADIATION", "AC_POWER"])
        corr = sub[["IRRADIATION", "AC_POWER", "MODULE_TEMPERATURE", "AMBIENT_TEMPERATURE"]].corr()
        print(f"\nPlant {plant} correlation with AC_POWER:")
        print(corr["AC_POWER"].sort_values(ascending=False))

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, plant in zip(axes, (1, 2)):
        sub = df[df["PLANT"] == plant].dropna(subset=["IRRADIATION"])
        ax.scatter(sub["IRRADIATION"], sub["AC_POWER"], s=3, alpha=0.2)
        ax.set_xlabel("Irradiation")
        ax.set_title(f"Plant {plant}")
    axes[0].set_ylabel("AC power")
    fig.suptitle("Irradiation vs AC power")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "irradiation_vs_power.png", dpi=120)
    plt.close(fig)

    section("Per-inverter average yield — spotting underperformers")
    # Use AC_POWER, not DC_POWER: Plant 1's DC_POWER is on a ~10x different
    # scale than Plant 2's (see DC->AC ratio check below), so DC_POWER isn't
    # safely comparable across plants. AC_POWER is consistently scaled.
    for plant in (1, 2):
        sub = df[df["PLANT"] == plant]
        by_inv = sub.groupby("SOURCE_KEY")["AC_POWER"].mean().sort_values()
        plant_mean = by_inv.mean()
        print(f"\nPlant {plant} — inverter mean AC_POWER (plant avg = {plant_mean:.1f}):")
        print(by_inv)

        fig, ax = plt.subplots(figsize=(10, 5))
        colors = ["crimson" if v < 0.9 * plant_mean else "steelblue" for v in by_inv.values]
        ax.bar(range(len(by_inv)), by_inv.values, color=colors)
        ax.axhline(plant_mean, color="black", linestyle="--", label="plant mean")
        ax.set_xticks(range(len(by_inv)))
        ax.set_xticklabels(by_inv.index, rotation=90, fontsize=7)
        ax.set_ylabel("Mean AC power")
        ax.set_title(f"Plant {plant} — per-inverter mean output (red = >10% below plant mean)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"plant{plant}_inverter_comparison.png", dpi=120)
        plt.close(fig)

    section("DC -> AC conversion ratio (inverter efficiency sanity check)")
    df_nonzero = df[df["DC_POWER"] > 0].copy()
    df_nonzero["AC_DC_RATIO"] = df_nonzero["AC_POWER"] / df_nonzero["DC_POWER"]
    for plant in (1, 2):
        sub = df_nonzero[df_nonzero["PLANT"] == plant]
        print(f"Plant {plant} AC/DC ratio: mean={sub['AC_DC_RATIO'].mean():.3f}, "
              f"std={sub['AC_DC_RATIO'].std():.3f}")

    print(f"\nFigures saved to {FIG_DIR}")


if __name__ == "__main__":
    main()
