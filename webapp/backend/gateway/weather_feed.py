"""Real weather for the gateway: Open-Meteo's 15-minute data, which the live
loop interpolates to each reading's timestamp (readings can be every 30 s,
so stepping between 15-minute values would show visible stairs)."""

import time

import numpy as np
import pandas as pd
import requests

from app.backfill import FORECAST_URL, MINUTELY_15_VARS

REFRESH_SECONDS = 15 * 60
COLUMNS = ["ghi", "dni", "dhi", "air_temp", "wind_speed", "cloud_cover"]


def fetch_weather_15min(lat: float, lon: float, past_days: int) -> pd.DataFrame:
    """Past `past_days` days plus today's forecast, at 15-minute resolution.
    Same source and variables as backfill.fetch_recent_weather_15min, but
    keeps the next few forecast points so "now" can be interpolated."""
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
    clouds = pd.Series(hourly["cloud_cover"], index=pd.to_datetime(hourly["time"]).tz_localize("UTC"))
    df["cloud_cover"] = clouds.reindex(df["timestamp"], method="ffill").to_numpy()
    return df.dropna().reset_index(drop=True)


class LiveWeather:
    """Caches the 15-minute feed and interpolates it to any moment."""

    def __init__(self, lat: float, lon: float):
        self.lat, self.lon = lat, lon
        self.frame: pd.DataFrame | None = None
        self.fetched_at = 0.0

    def at(self, ts: pd.Timestamp) -> dict:
        if self.frame is None or time.monotonic() - self.fetched_at > REFRESH_SECONDS:
            try:
                self.frame = fetch_weather_15min(self.lat, self.lon, past_days=1)
                self.fetched_at = time.monotonic()
            except requests.RequestException:
                if self.frame is None:
                    raise  # nothing cached yet; the caller retries next tick
        # Same unit on both sides: pandas may store these in us, Timestamp.value is ns.
        x = pd.DatetimeIndex(self.frame["timestamp"]).as_unit("ns").asi8
        t = ts.as_unit("ns").value
        return {c: float(np.interp(t, x, self.frame[c].to_numpy())) for c in COLUMNS}
