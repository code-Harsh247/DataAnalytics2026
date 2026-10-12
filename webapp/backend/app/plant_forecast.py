"""Forecasts and projections for a plant (Contract 7): Open-Meteo weather ->
the physics model -> x the plant's calibration (plant_metrics).

- Forecast: the next 7 days, from the live forecast.
- Accuracy: the day-ahead forecast *as it was issued* for each of the last 7
  days (Open-Meteo's previous-runs API), against what the plant actually
  made -- a real day-ahead error, not hindsight. Its spread gives the
  p10-p90 band on the forecast.
- Typical year: the last 365 days of archive weather at the plant, for the
  annual projection and payback on Finance.
"""

import threading
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from .backfill import ARCHIVE_LAG_DAYS, FORECAST_URL, fetch_historical_weather
from .plant_metrics import PlantData, daily, plant_power, to_iso

PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
WEATHER_VARS = ["shortwave_radiation", "direct_normal_irradiance", "diffuse_radiation",
                "temperature_2m", "wind_speed_10m", "cloud_cover"]
RENAME = {"shortwave_radiation": "ghi", "direct_normal_irradiance": "dni", "diffuse_radiation": "dhi",
          "temperature_2m": "air_temp", "wind_speed_10m": "wind_speed", "cloud_cover": "cloud_cover"}
FORECAST_DAYS = 7
ACCURACY_DAYS = 7
MIN_COVERAGE = 0.9  # a day counts for accuracy only if the plant reported ~all of it
DEFAULT_BAND = (0.85, 1.15)
FORECAST_TTL = 15 * 60
PREVIOUS_TTL = 60 * 60
ARCHIVE_TTL = 12 * 60 * 60

_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}
_lock = threading.Lock()


def _cached(key: tuple, ttl: float, fetch) -> pd.DataFrame:
    with _lock:
        hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    frame = fetch()
    with _lock:
        _cache[key] = (time.monotonic(), frame)
    return frame


def _hourly_frame(hourly: dict, suffix: str = "") -> pd.DataFrame:
    df = pd.DataFrame({"timestamp": pd.to_datetime(hourly["time"]).tz_localize("UTC")})
    for var in WEATHER_VARS:
        if var + suffix in hourly:
            df[RENAME[var]] = hourly[var + suffix]
    return df.dropna(subset=["ghi", "dni", "dhi", "air_temp"]).reset_index(drop=True)


def forecast_weather(lat: float, lon: float) -> pd.DataFrame:
    def fetch():
        resp = requests.get(FORECAST_URL, timeout=30, params={
            "latitude": lat, "longitude": lon, "hourly": ",".join(WEATHER_VARS),
            "past_days": 1, "forecast_days": FORECAST_DAYS + 1, "timezone": "UTC",
        })
        resp.raise_for_status()
        return _hourly_frame(resp.json()["hourly"])
    return _cached(("forecast", round(lat, 2), round(lon, 2)), FORECAST_TTL, fetch)


def previous_day_forecasts(lat: float, lon: float) -> pd.DataFrame:
    """What the forecast said the day before, for each hour of the last week."""
    def fetch():
        variables = ",".join(f"{v}_previous_day1" for v in WEATHER_VARS if v != "cloud_cover")
        resp = requests.get(PREVIOUS_RUNS_URL, timeout=30, params={
            "latitude": lat, "longitude": lon, "hourly": variables,
            "past_days": ACCURACY_DAYS + 1, "forecast_days": 1, "timezone": "UTC",
        })
        resp.raise_for_status()
        return _hourly_frame(resp.json()["hourly"], suffix="_previous_day1")
    return _cached(("previous", round(lat, 2), round(lon, 2)), PREVIOUS_TTL, fetch)


def archive_year(lat: float, lon: float) -> pd.DataFrame:
    def fetch():
        end = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
        return fetch_historical_weather(lat, lon, str(end - timedelta(days=364)), str(end))
    return _cached(("archive", round(lat, 2), round(lon, 2), date.today().isoformat()), ARCHIVE_TTL, fetch)


def _hourly_kw(p: PlantData, weather: pd.DataFrame) -> pd.DataFrame:
    """Calibrated expected plant kW per hour; each point is the mean over the
    hour *ending* at its timestamp (Open-Meteo's convention), plotted mid-hour."""
    out = pd.DataFrame({"timestamp": weather["timestamp"]})
    out["kw"] = p.physics_kw(weather, 60).to_numpy() * p.calibration
    out["mid"] = out["timestamp"] - pd.Timedelta(minutes=30)
    out["local_date"] = out["mid"].dt.tz_convert(p.tz).dt.strftime("%Y-%m-%d")
    if "cloud_cover" in weather:
        out["cloud_cover"] = weather["cloud_cover"].to_numpy()
    out["ghi"] = weather["ghi"].to_numpy()
    return out


def accuracy(p: PlantData) -> dict:
    """Day-ahead forecast vs actual for the last complete days the plant fully reported."""
    lat, lon = p.row["latitude"], p.row["longitude"]
    try:
        prev = _hourly_kw(p, previous_day_forecasts(lat, lon))
    except requests.RequestException:
        return {"days": [], "mape": None, "ratios": []}
    forecast_by_day = prev.groupby("local_date")["kw"].sum()  # hourly kW -> kWh

    d = daily(p).set_index("date") if not p.frame.empty else pd.DataFrame()
    hours = p.frame.groupby("local_date")["hours"].sum() / max(len(p.inverters), 1) if not p.frame.empty else pd.Series()
    days, ratios = [], []
    for day in sorted(forecast_by_day.index):
        if day >= p.today or day not in d.index or hours.get(day, 0) < 24 * MIN_COVERAGE:
            continue
        actual, predicted = float(d.loc[day, "energy_kwh"]), float(forecast_by_day[day])
        if actual <= 0.1 or predicted <= 0.1:
            continue
        days.append({"date": day, "forecast_kwh": round(predicted, 2), "actual_kwh": round(actual, 2),
                     "error_pct": round((predicted - actual) / actual * 100, 1)})
        ratios.append(actual / predicted)
    days = days[-ACCURACY_DAYS:]
    ratios = ratios[-ACCURACY_DAYS:]
    mape = round(float(np.mean([abs(x["error_pct"]) for x in days])), 1) if days else None
    return {"days": days, "mape": mape, "ratios": ratios}


def _band(ratios: list[float]) -> tuple[float, float]:
    if len(ratios) < 3:
        return DEFAULT_BAND
    return float(np.quantile(ratios, 0.1)), float(np.quantile(ratios, 0.9))


def forecast(p: PlantData) -> dict:
    lat, lon = p.row["latitude"], p.row["longitude"]
    hourly = _hourly_kw(p, forecast_weather(lat, lon))
    acc = accuracy(p)
    low, high = _band(acc["ratios"])

    days = []
    for day, g in hourly.groupby("local_date"):
        if day < p.today:
            continue
        energy = float(g["kw"].sum())
        sunny = g[g["ghi"] > 0]
        days.append({
            "date": day, "energy_kwh": round(energy, 2), "revenue": round(energy * p.tariff, 2),
            "p10_kwh": round(energy * low, 2), "p90_kwh": round(energy * high, 2),
            "cloud_cover": round(float(sunny["cloud_cover"].mean()), 0) if len(sunny) and "cloud_cover" in sunny else None,
        })
    days = days[:FORECAST_DAYS]

    today_hours = hourly[hourly["local_date"] == p.today]
    today_forecast = [{"t": to_iso(r.mid), "kw": round(float(r.kw), 3)} for r in today_hours.itertuples()]
    today_curve = actual_curve(p, p.today)

    # Month projection: actual so far + forecast for the rest of the month in
    # the forecast horizon + recent average daily energy beyond it.
    d = daily(p)
    month_actual = float(d[d["date"].str.startswith(p.this_month)]["energy_kwh"].sum()) if len(d) else 0.0
    today_actual = float(d[d["date"] == p.today]["energy_kwh"].sum()) if len(d) else 0.0
    now_mid = p.now
    rest_today = float(today_hours[today_hours["timestamp"] > now_mid]["kw"].sum())
    future = [x for x in days if x["date"] > p.today and x["date"].startswith(p.this_month)]
    complete = d[(d["date"] < p.today)].tail(14) if len(d) else d
    avg_daily = float(complete["energy_kwh"].mean()) if len(complete) else 0.0
    last_day = (pd.Timestamp(p.today) + pd.offsets.MonthEnd(0)).date()
    horizon_end = date.fromisoformat(future[-1]["date"]) if future else date.fromisoformat(p.today)
    beyond = max((last_day - horizon_end).days, 0)
    projection = month_actual + rest_today + sum(x["energy_kwh"] for x in future) + beyond * avg_daily

    return {
        "calibration": round(p.calibration, 3),
        "timezone": p.tz,
        "days": days,
        "today": {"forecast": today_forecast, "actual": today_curve, "actual_kwh": round(today_actual, 2)},
        "accuracy": {"days": acc["days"], "mape": acc["mape"]},
        "band": {"low": round(low, 3), "high": round(high, 3), "from_accuracy": len(acc["ratios"]) >= 3},
        "month_projection_kwh": round(projection, 1),
        "month_projection_revenue": round(projection * p.tariff, 2),
    }


def actual_curve(p: PlantData, day: str) -> list[dict]:
    """Plant kW through one local day, as 15-minute means (live readings can
    be 30 s apart; the chart doesn't need that resolution)."""
    f = p.frame[p.frame["local_date"] == day]
    if f.empty:
        return []
    power = plant_power(f)
    buckets = power.groupby(power.index.floor("15min")).mean()
    return [{"t": to_iso(ts + pd.Timedelta(minutes=7, seconds=30)), "kw": round(float(kw), 3)}
            for ts, kw in buckets.items()]


def typical_year(p: PlantData) -> dict:
    """Projected annual production: last year's real weather at the plant ->
    physics x calibration."""
    weather = archive_year(p.row["latitude"], p.row["longitude"])
    energy = float((p.physics_kw(weather, 60) * p.calibration).sum())  # hourly kW -> kWh
    return {"energy_kwh": round(energy, 0), "revenue": round(energy * p.tariff, 0),
            "weather_from": weather["timestamp"].min().date().isoformat(),
            "weather_to": weather["timestamp"].max().date().isoformat()}
