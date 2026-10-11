"""Historical backfill: real past weather -> synthetic per-inverter output
with ground-truth fault labels, as a training/evaluation dataset for the
anomaly models in app/models/.

Same physics as synthetic_generation.py (pvlib plane-of-array irradiance +
NOCT cell temperature + linear temperature derating), but vectorized over a
whole date range instead of one live tick. Weather comes from Open-Meteo's
archive API, which takes fixed start/end dates -- so a given (location,
dates, seed) always produces the same dataset, and teammates can regenerate
identical data independently.

Things added on top of the live pipeline's physics, deliberately -- a first
draft without them was so clean that a one-line power/irradiance ratio
threshold scored F1 0.99, making any model comparison meaningless:
- Site irradiance error: Open-Meteo is gridded reanalysis, not an on-site
  sensor, so the sun the panels actually see differs hour to hour from the
  reported value. Shared by all inverters (it's the same sky).
- Measurement noise and slow per-inverter soiling drift.
- Unlabeled partial-shading dips: short (1-2h), inverter-specific losses
  that look like faults but aren't -- realistic false-alarm bait.
- Fault labels (is_fault / fault_severity) kept on every row, so detection
  can be scored with real precision/recall.

Usage (from webapp/backend):
    .venv/bin/python -m app.backfill --lat 18.0 --lon 80.0 \
        --start 2026-09-01 --end 2026-09-30 --out data/backfill/my_plant.csv
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib
import requests

from .synthetic_generation import DEFAULT_TEMP_COEFFICIENT, INVERTER_EFFICIENCY, NOCT_C

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MINUTELY_15_VARS = (
    "shortwave_radiation,direct_normal_irradiance,diffuse_radiation,"
    "temperature_2m,wind_speed_10m"
)
HOURLY_VARS = (
    "shortwave_radiation,direct_normal_irradiance,diffuse_radiation,"
    "temperature_2m,wind_speed_10m,cloud_cover"
)
ARCHIVE_LAG_DAYS = 6  # archive (ERA5) data trails real time by ~5 days

# Fault injection. Lower start rate than the live pipeline's 0.04 per 15-min
# tick (~15%/hour), which over a month would leave inverters faulted almost
# half the time -- too dense to be a realistic anomaly-detection problem.
# 0.02 gives ~8-10% faulted daylight hours: rare, but enough positives in a
# held-out week for precision/recall to mean something.
FAULT_START_PROB_PER_HOUR = 0.02
FAULT_MIN_HOURS = 2
FAULT_MAX_HOURS = 8
FAULT_MIN_SEVERITY = 0.05
FAULT_MAX_SEVERITY = 0.4

SITE_IRRADIANCE_ERROR_STD = 0.06  # reported vs. actual on-site irradiance, plant-wide
NOISE_STD = 0.03  # multiplicative per-inverter measurement noise
SHADING_START_PROB_PER_HOUR = 0.03
SHADING_MIN_HOURS = 1
SHADING_MAX_HOURS = 2
SHADING_MIN_LOSS = 0.05
SHADING_MAX_LOSS = 0.2
MAX_SOILING_LOSS = 0.04  # per-inverter linear soiling drift over the period
EFFICIENCY_SPREAD_STD = 0.02  # persistent per-inverter variance, as in Supabase
DAYLIGHT_MIN_ELEVATION_DEG = 5.0


def fetch_historical_weather(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "hourly": HOURLY_VARS, "timezone": "UTC",
    }
    resp = requests.get(ARCHIVE_URL, params=params, timeout=30)
    resp.raise_for_status()
    hourly = resp.json()["hourly"]

    df = pd.DataFrame({
        "timestamp": pd.to_datetime(hourly["time"]).tz_localize("UTC"),
        "ghi": hourly["shortwave_radiation"],
        "dni": hourly["direct_normal_irradiance"],
        "dhi": hourly["diffuse_radiation"],
        "air_temp": hourly["temperature_2m"],
        "wind_speed": hourly["wind_speed_10m"],
        "cloud_cover": hourly["cloud_cover"],
    })
    return df.dropna().reset_index(drop=True)


def fetch_recent_weather_15min(lat: float, lon: float, past_days: int) -> pd.DataFrame:
    """Last `past_days` days up to now at 15-minute resolution, from the
    forecast API (no archive lag, unlike fetch_historical_weather) -- the same
    cadence as live ingestion, for seeding a real plant's history. Cloud cover
    is only hourly there, so it's forward-filled."""
    params = {
        "latitude": lat, "longitude": lon,
        "past_days": past_days, "forecast_days": 1,
        "minutely_15": MINUTELY_15_VARS, "hourly": "cloud_cover", "timezone": "UTC",
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    m15, hourly = body["minutely_15"], body["hourly"]

    df = pd.DataFrame({
        "timestamp": pd.to_datetime(m15["time"]).tz_localize("UTC"),
        "ghi": m15["shortwave_radiation"],
        "dni": m15["direct_normal_irradiance"],
        "dhi": m15["diffuse_radiation"],
        "air_temp": m15["temperature_2m"],
        "wind_speed": m15["wind_speed_10m"],
    })
    clouds = pd.Series(
        hourly["cloud_cover"], index=pd.to_datetime(hourly["time"]).tz_localize("UTC"),
    )
    df["cloud_cover"] = clouds.reindex(df["timestamp"], method="ffill").to_numpy()
    df = df[df["timestamp"] <= pd.Timestamp.now(tz="UTC")]  # drop the forecast part
    return df.dropna().reset_index(drop=True)


def compute_plant_physics(
    weather: pd.DataFrame, lat: float, lon: float, tilt: float, azimuth: float,
    step_minutes: int = 60,
) -> pd.DataFrame:
    """Adds solar_elevation, poa_irradiance, cell_temp. Open-Meteo radiation is
    the mean over the *preceding* interval, so sun position is taken mid-interval."""
    location = pvlib.location.Location(lat, lon, tz="UTC")
    mid = pd.DatetimeIndex(weather["timestamp"]) - pd.Timedelta(minutes=step_minutes / 2)
    solpos = location.get_solarposition(mid)

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt, surface_azimuth=azimuth,
        solar_zenith=solpos["apparent_zenith"].to_numpy(),
        solar_azimuth=solpos["azimuth"].to_numpy(),
        dni=weather["dni"].to_numpy(), ghi=weather["ghi"].to_numpy(), dhi=weather["dhi"].to_numpy(),
    )["poa_global"]

    out = weather.copy()
    out["solar_elevation"] = solpos["apparent_elevation"].to_numpy().round(2)
    out["poa_irradiance"] = np.clip(np.nan_to_num(np.asarray(poa, dtype=float)), 0, None).round(1)
    out["cell_temp"] = (out["air_temp"] + (NOCT_C - 20.0) / 800.0 * out["poa_irradiance"]).round(2)
    return out


def inject_episodes(
    n_steps: int, rng: np.random.Generator, start_prob: float,
    min_steps: int, max_steps: int, min_loss: float, max_loss: float,
) -> np.ndarray:
    """Per-step fractional loss for one inverter from random episodes (0 = none)."""
    loss = np.zeros(n_steps)
    t = 0
    while t < n_steps:
        if rng.random() < start_prob:
            duration = int(rng.integers(min_steps, max_steps + 1))
            loss[t:t + duration] = rng.uniform(min_loss, max_loss)
            t += duration
        else:
            t += 1
    return loss


def build_dataset(
    lat: float, lon: float, start: str, end: str,
    capacity_kw: float = 7.5, tilt: float = 18.0, azimuth: float = 180.0,
    inverter_count: int = 4, temp_coefficient: float = DEFAULT_TEMP_COEFFICIENT,
    degradation_factor: float = 1.0, seed: int = 42,
    weather: pd.DataFrame | None = None, step_minutes: int = 60,
    efficiencies: list[float] | None = None,
) -> pd.DataFrame:
    """Hourly from the archive API by default. Pass `weather` (e.g. from
    fetch_recent_weather_15min) with its `step_minutes` to build at another
    cadence; episode durations and start rates are converted so faults look
    the same in hours either way. `efficiencies` pins per-inverter efficiency
    (e.g. a real plant's stored base_efficiency_factor) instead of drawing it."""
    rng = np.random.default_rng(seed)
    if weather is None:
        weather = fetch_historical_weather(lat, lon, start, end)
    plant = compute_plant_physics(weather, lat, lon, tilt, azimuth, step_minutes)
    n = len(plant)
    steps_per_hour = 60 // step_minutes
    per_inverter_kw = capacity_kw / inverter_count

    clean_dc = np.clip(
        per_inverter_kw * (plant["poa_irradiance"] / 1000.0)
        * (1 + temp_coefficient * (plant["cell_temp"] - 25.0)),
        0, None,
    ) * degradation_factor
    clean_dc = clean_dc * np.clip(rng.normal(1.0, SITE_IRRADIANCE_ERROR_STD, n), 0.8, 1.2)

    frames = []
    for i in range(inverter_count):
        if efficiencies is not None:
            efficiency = efficiencies[i]
        else:
            efficiency = float(np.clip(rng.normal(1.0, EFFICIENCY_SPREAD_STD), 0.9, 1.1))
        soiling = 1 - np.linspace(0, rng.uniform(0, MAX_SOILING_LOSS), n)
        fault_severity = inject_episodes(
            n, rng, FAULT_START_PROB_PER_HOUR / steps_per_hour,
            FAULT_MIN_HOURS * steps_per_hour, FAULT_MAX_HOURS * steps_per_hour,
            FAULT_MIN_SEVERITY, FAULT_MAX_SEVERITY,
        )
        shading = inject_episodes(
            n, rng, SHADING_START_PROB_PER_HOUR / steps_per_hour,
            SHADING_MIN_HOURS * steps_per_hour, SHADING_MAX_HOURS * steps_per_hour,
            SHADING_MIN_LOSS, SHADING_MAX_LOSS,
        )
        noise = np.clip(rng.normal(1.0, NOISE_STD, n), 0.85, 1.15)

        dc = clean_dc * efficiency * soiling * (1 - fault_severity) * (1 - shading) * noise
        frame = plant.copy()
        frame["inverter"] = f"INV-{i + 1}"
        frame["dc_power_kw"] = dc.round(4)
        frame["ac_power_kw"] = (dc * INVERTER_EFFICIENCY).round(4)
        frame["fault_severity"] = fault_severity.round(3)
        frame["is_fault"] = fault_severity > 0
        frames.append(frame)

    df = pd.concat(frames, ignore_index=True)
    df["is_daylight"] = df["solar_elevation"] > DAYLIGHT_MIN_ELEVATION_DEG
    cols = [
        "timestamp", "inverter", "ghi", "dni", "dhi", "poa_irradiance", "air_temp",
        "cell_temp", "wind_speed", "cloud_cover", "solar_elevation", "is_daylight",
        "dc_power_kw", "ac_power_kw", "is_fault", "fault_severity",
    ]
    return df[cols].sort_values(["timestamp", "inverter"]).reset_index(drop=True)


def main() -> None:
    default_end = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--start", default=str(default_end - timedelta(days=29)))
    p.add_argument("--end", default=str(default_end))
    p.add_argument("--capacity-kw", type=float, default=7.5)
    p.add_argument("--tilt", type=float, default=18.0)
    p.add_argument("--azimuth", type=float, default=180.0)
    p.add_argument("--inverters", type=int, default=4)
    p.add_argument("--temp-coefficient", type=float, default=DEFAULT_TEMP_COEFFICIENT)
    p.add_argument("--degradation-factor", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    df = build_dataset(
        args.lat, args.lon, args.start, args.end, args.capacity_kw, args.tilt, args.azimuth,
        args.inverters, args.temp_coefficient, args.degradation_factor, args.seed,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    out.with_suffix(".meta.json").write_text(json.dumps(vars(args), indent=2) + "\n")

    day = df[df["is_daylight"]]
    print(f"wrote {len(df)} rows ({df['timestamp'].nunique()} hours x {args.inverters} inverters) -> {out}")
    print(f"daylight rows: {len(day)}, faulted daylight rows: {int(day['is_fault'].sum())} "
          f"({day['is_fault'].mean():.1%})")


if __name__ == "__main__":
    main()
