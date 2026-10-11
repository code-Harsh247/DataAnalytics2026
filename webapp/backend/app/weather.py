"""Real current weather ingestion for a user-configured plant's location.

Uses Open-Meteo (free, no API key) for live conditions, and pvlib for the
theoretical clear-sky GHI at that same location/moment -- same physics
approach as solar_features.py, but parameterized per-request instead of the
hardcoded Plant 1/2 constants there. Deliberately kept separate from that
module: this handles arbitrary real-world coordinates for a single "now"
timestamp, not the fixed historical Plant 1/2 dataframe pipeline.
"""

from datetime import datetime, timezone

import pandas as pd
import pvlib
import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_VARS = "temperature_2m,cloud_cover,shortwave_radiation,direct_normal_irradiance,diffuse_radiation"


def fetch_current_weather(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": CURRENT_VARS,
        "timezone": "UTC",
    }
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
    resp.raise_for_status()
    current = resp.json()["current"]

    return {
        "timestamp": current["time"],
        "temperature_c": current["temperature_2m"],
        "cloud_cover_pct": current["cloud_cover"],
        "ghi_wm2": current["shortwave_radiation"],
        "dni_wm2": current["direct_normal_irradiance"],
        "dhi_wm2": current["diffuse_radiation"],
    }


def get_clearsky_ghi(lat: float, lon: float, timestamp: str) -> tuple[float, float]:
    """Returns (clearsky_ghi_wm2, solar_elevation_deg) for lat/lon at timestamp."""
    location = pvlib.location.Location(lat, lon, tz="UTC")
    times = pd.DatetimeIndex([pd.Timestamp(timestamp, tz="UTC")])

    solpos = location.get_solarposition(times)
    clearsky = location.get_clearsky(times, model="ineichen")

    return float(clearsky["ghi"].iloc[0]), float(solpos["apparent_elevation"].iloc[0])


def get_current_conditions(lat: float, lon: float) -> dict:
    weather = fetch_current_weather(lat, lon)
    clearsky_ghi, elevation = get_clearsky_ghi(lat, lon, weather["timestamp"])

    clearsky_index = None
    if elevation > 5 and clearsky_ghi > 0:
        clearsky_index = round(weather["ghi_wm2"] / clearsky_ghi, 3)

    return {
        **weather,
        "clearsky_ghi_wm2": round(clearsky_ghi, 1),
        "clearsky_index": clearsky_index,
    }
