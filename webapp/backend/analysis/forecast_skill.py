"""A1: is the generation forecast any good? Twelve months at the test plant
(Pune, 18.52 N 73.86 E; 7.5 kWp, tilt 18.5, south), daily energy, comparing:

- Day-ahead forecast: Open-Meteo's forecast *as issued the day before*
  (previous-runs API, `_previous_day1`) -> the app's physics model.
- Persistence: tomorrow = today's actual.
- Climatology: the trailing 30-day mean of actual daily energy.

"Actual" = the same physics run on ERA5 reanalysis weather (the archive),
the closest thing to measured sunlight we have for a whole year. Same model
on both sides, so the comparison isolates the *weather* forecast's skill.
Skill = 1 - MAE / MAE_reference (1 = perfect, 0 = no better, < 0 = worse).

    python -m analysis.forecast_skill
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from app.backfill import ARCHIVE_LAG_DAYS, compute_plant_physics, fetch_historical_weather
from app.synthetic_generation import INVERTER_EFFICIENCY

from .common import OUT, save, write_json

LAT, LON, TZ = 18.52, 73.86, "Asia/Kolkata"
CAPACITY_KW, TILT, AZIMUTH, GAMMA = 7.5, 18.52, 180.0, -0.0035
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
CLIMATOLOGY_DAYS = 30
METHODS = {"forecast": "Day-ahead forecast", "persistence": "Persistence", "climatology": "30-day climatology"}
METHOD_COLORS = {"forecast": "#2563eb", "persistence": "#f59e0b", "climatology": "#9ca3af"}


def period() -> tuple[date, date]:
    end = date.today() - timedelta(days=ARCHIVE_LAG_DAYS + 1)
    return end - timedelta(days=364), end


def day_ahead_weather(start: date, end: date) -> pd.DataFrame:
    path = OUT / f"previous_runs_{start}_{end}.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["timestamp"])
    names = {"shortwave_radiation": "ghi", "direct_normal_irradiance": "dni",
             "diffuse_radiation": "dhi", "temperature_2m": "air_temp"}
    resp = requests.get(PREVIOUS_RUNS_URL, timeout=120, params={
        "latitude": LAT, "longitude": LON, "start_date": str(start), "end_date": str(end), "timezone": "UTC",
        "hourly": ",".join(f"{v}_previous_day1" for v in names),
    })
    resp.raise_for_status()
    hourly = resp.json()["hourly"]
    df = pd.DataFrame({"timestamp": pd.to_datetime(hourly["time"]).tz_localize("UTC")})
    for v, short in names.items():
        df[short] = hourly[f"{v}_previous_day1"]
    df = df.dropna().reset_index(drop=True)
    df.to_csv(path, index=False)
    return df


def archive_weather(start: date, end: date) -> pd.DataFrame:
    path = OUT / f"archive_{start}_{end}.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["timestamp"])
    df = fetch_historical_weather(LAT, LON, str(start), str(end))
    df.to_csv(path, index=False)
    return df


def daily_energy(weather: pd.DataFrame) -> pd.Series:
    """Hourly weather -> the plant's AC energy per local day (kWh)."""
    phys = compute_plant_physics(weather, LAT, LON, TILT, AZIMUTH, 60)
    kw = np.clip(CAPACITY_KW * phys["poa_irradiance"] / 1000 * (1 + GAMMA * (phys["cell_temp"] - 25))
                 * INVERTER_EFFICIENCY, 0, None)
    local_day = (phys["timestamp"] - pd.Timedelta(minutes=30)).dt.tz_convert(TZ).dt.date
    hours = pd.Series(kw.to_numpy()).groupby(local_day.to_numpy())
    energy = hours.sum()
    return energy[hours.size() >= 20]  # drop partial days at the edges


def evaluate() -> pd.DataFrame:
    start, end = period()
    actual = daily_energy(archive_weather(start, end)).rename("actual")
    forecast = daily_energy(day_ahead_weather(start, end)).rename("forecast")
    df = pd.concat([actual, forecast], axis=1).dropna()
    df.index = pd.to_datetime(df.index)
    df = df.asfreq("D")
    df["persistence"] = df["actual"].shift(1)
    df["climatology"] = df["actual"].shift(1).rolling(CLIMATOLOGY_DAYS, min_periods=CLIMATOLOGY_DAYS).mean()
    return df.dropna()


def metrics(df: pd.DataFrame) -> dict:
    out = {}
    for m in METHODS:
        err = df[m] - df["actual"]
        out[m] = {"mae_kwh": round(float(err.abs().mean()), 2), "rmse_kwh": round(float(np.sqrt((err ** 2).mean())), 2),
                  "bias_kwh": round(float(err.mean()), 2),
                  "mape_pct": round(float((err.abs() / df["actual"].clip(lower=1)).mean() * 100), 1)}
    for ref in ["persistence", "climatology"]:
        out["forecast"][f"skill_vs_{ref}"] = round(1 - out["forecast"]["mae_kwh"] / out[ref]["mae_kwh"], 3)
    return out


def figures(df: pd.DataFrame) -> dict:
    import matplotlib.pyplot as plt

    paths = {}
    monthly = df.assign(month=df.index.to_period("M")).groupby("month").apply(
        lambda g: pd.Series({m: (g[m] - g["actual"]).abs().mean() for m in METHODS}), include_groups=False)
    fig, ax = plt.subplots(figsize=(8, 2.8))
    x = np.arange(len(monthly))
    for i, m in enumerate(METHODS):
        ax.bar(x + (i - 1) * 0.27, monthly[m], width=0.27, color=METHOD_COLORS[m], label=METHODS[m])
    ax.set_xticks(x, [p.strftime("%b %y") for p in monthly.index], fontsize=8)
    ax.set_ylabel("mean absolute error, kWh/day")
    ax.legend(fontsize=7)
    paths["forecast_mae_by_month"] = save(fig, "forecast_mae_by_month")

    fig, axes = plt.subplots(1, 2, figsize=(8, 3))
    lim = [0, df[["actual", "forecast", "persistence"]].max().max() * 1.05]
    for ax, m in zip(axes, ["forecast", "persistence"]):
        monsoon = df.index.month.isin([6, 7, 8, 9])
        ax.scatter(df.loc[~monsoon, "actual"], df.loc[~monsoon, m], s=6, alpha=0.6, color=METHOD_COLORS[m], label="Oct–May")
        ax.scatter(df.loc[monsoon, "actual"], df.loc[monsoon, m], s=6, alpha=0.6, color="#16a34a", label="monsoon (Jun–Sep)")
        ax.plot(lim, lim, color="#111827", lw=0.8)
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel("actual, kWh/day")
        ax.set_ylabel(f"{METHODS[m].lower()}, kWh/day")
        ax.legend(fontsize=7)
    paths["forecast_scatter"] = save(fig, "forecast_scatter")
    return paths


def main() -> dict:
    df = evaluate()
    monsoon = df.index.month.isin([6, 7, 8, 9])
    result = {
        "location": {"lat": LAT, "lon": LON, "capacity_kw": CAPACITY_KW},
        "days": int(len(df)), "from": str(df.index.min().date()), "to": str(df.index.max().date()),
        "all": metrics(df), "monsoon": metrics(df[monsoon]), "dry": metrics(df[~monsoon]),
        "monsoon_days": int(monsoon.sum()),
        "figures": figures(df),
    }
    write_json("forecast_skill", result)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(main(), indent=1))
