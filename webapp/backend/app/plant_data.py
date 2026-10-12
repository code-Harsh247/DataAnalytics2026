"""A user's stored plant data, read from Supabase *as that user* and shaped
into the Contract 1 dataset the anomaly models already understand.

The backend holds no Supabase admin key: every read carries the caller's own
access token (from the app's `Authorization: Bearer ...` header) plus the
public anon key, so row-level security decides what is visible -- exactly as
in the browser. A plant that isn't yours simply comes back empty (404).
"""

import os

import numpy as np
import pandas as pd
import pvlib
import requests

from .backfill import DAYLIGHT_MIN_ELEVATION_DEG
from .seed_supabase import read_env_file

PAGE_SIZE = 1000  # Supabase's response cap
NATIVE_STEP_FALLBACK_MINUTES = 15  # rows from before telemetry carried energy_kwh were 15-min


class AuthError(Exception):
    pass


class NotFound(Exception):
    pass


class InsufficientData(Exception):
    pass


def _z(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _settings() -> tuple[str, str]:
    env = {**read_env_file(), **os.environ}
    url = env.get("SUPABASE_URL") or env.get("NEXT_PUBLIC_SUPABASE_URL")
    key = env.get("SUPABASE_ANON_KEY") or env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("Backend needs SUPABASE_URL and SUPABASE_ANON_KEY (or webapp/frontend/.env.local)")
    return url.rstrip("/"), key


class UserSupabase:
    def __init__(self, access_token: str):
        self.url, key = _settings()
        self.session = requests.Session()
        self.session.headers.update({"apikey": key, "Authorization": f"Bearer {access_token}"})

    def select(self, table: str, params: dict) -> list[dict]:
        """All matching rows, paged past the 1000-row cap."""
        rows: list[dict] = []
        while True:
            resp = self.session.get(
                f"{self.url}/rest/v1/{table}", timeout=30,
                params={**params, "limit": PAGE_SIZE, "offset": len(rows)},
            )
            if resp.status_code in (401, 403):
                raise AuthError("Session expired or invalid -- sign in again.")
            resp.raise_for_status()
            page = resp.json()
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                return rows

    def rpc(self, fn: str, **params):
        resp = self.session.post(f"{self.url}/rest/v1/rpc/{fn}", json=params, timeout=30)
        if resp.status_code in (401, 403):
            raise AuthError("Session expired or invalid -- sign in again.")
        resp.raise_for_status()
        return resp.json()

    def plant(self, plant_id: str) -> dict:
        rows = self.select("plants", {"select": "*", "id": f"eq.{plant_id}"})
        if not rows:
            raise NotFound("Plant not found.")
        return rows[0]

    def inverters(self, plant_id: str) -> list[dict]:
        rows = self.select("inverters", {"select": "id,label", "plant_id": f"eq.{plant_id}"})
        return sorted(rows, key=lambda r: int(r["label"].split("-")[-1]))

    def gateway(self, plant_id: str) -> dict | None:
        rows = self.select("gateways", {
            "select": "serial,paired_at,last_seen_at", "plant_id": f"eq.{plant_id}",
        })
        return rows[0] if rows and rows[0].get("paired_at") else None

    def readings(self, inverter_ids: list[str], since: pd.Timestamp,
                 until: pd.Timestamp | None = None) -> pd.DataFrame:
        params = {
            "select": "inverter_id,recorded_at,ac_power_kw,dc_power_kw,cell_temp_c,"
                      "poa_irradiance_wm2,energy_kwh,revenue_per_interval,fault_active,fault_severity",
            "inverter_id": f"in.({','.join(inverter_ids)})",
            "order": "recorded_at.asc,inverter_id.asc",
        }
        params["and"] = f"(recorded_at.gte.{_z(since)}" + (
            f",recorded_at.lt.{_z(until)})" if until is not None else ")")
        return pd.DataFrame(self.select("generation_readings", params))

    def weather(self, plant_id: str, since: pd.Timestamp) -> pd.DataFrame:
        return pd.DataFrame(self.select("weather_readings", {
            "select": "recorded_at,temperature_c,cloud_cover_pct,ghi_wm2,dni_wm2,dhi_wm2,wind_speed_kmh",
            "plant_id": f"eq.{plant_id}",
            "recorded_at": f"gte.{_z(since - pd.Timedelta(minutes=30))}",
            "order": "recorded_at.asc",
        }))


def _solar_elevation(lat: float, lon: float, times: pd.DatetimeIndex) -> np.ndarray:
    location = pvlib.location.Location(lat, lon, tz="UTC")
    return location.get_solarposition(times)["apparent_elevation"].to_numpy()


def native_frame(plant: dict, inverters: list[dict], readings: pd.DataFrame,
                 weather: pd.DataFrame) -> pd.DataFrame:
    """One row per inverter per stored reading, with Contract 1 columns.
    Only timestamps where every inverter reported are kept: the models
    compare each inverter with its peers at the same moment."""
    if readings.empty:
        return pd.DataFrame()
    labels = {inv["id"]: inv["label"] for inv in inverters}
    df = readings.copy()
    df["timestamp"] = pd.to_datetime(df["recorded_at"], utc=True)
    df["inverter"] = df["inverter_id"].map(labels)
    df = df.dropna(subset=["inverter", "ac_power_kw"]).drop_duplicates(["timestamp", "inverter"])
    complete = df.groupby("timestamp")["inverter"].transform("nunique") == len(inverters)
    df = df[complete].sort_values("timestamp")

    if weather.empty:
        raise InsufficientData("No weather readings stored for this plant.")
    w = weather.copy()
    w["timestamp"] = pd.to_datetime(w["recorded_at"], utc=True)
    w = w.drop(columns="recorded_at").sort_values("timestamp")
    # Weather and power are written together, but older browser-tick rows may
    # be a few minutes apart: join each reading to the nearest weather row.
    df = pd.merge_asof(df, w, on="timestamp", direction="nearest", tolerance=pd.Timedelta(minutes=20))

    out = pd.DataFrame({
        "timestamp": df["timestamp"],
        "inverter": df["inverter"],
        "ghi": df["ghi_wm2"], "dni": df["dni_wm2"], "dhi": df["dhi_wm2"],
        "poa_irradiance": df["poa_irradiance_wm2"],
        "air_temp": df["temperature_c"], "cell_temp": df["cell_temp_c"],
        "wind_speed": df["wind_speed_kmh"], "cloud_cover": df["cloud_cover_pct"],
        "dc_power_kw": df["dc_power_kw"], "ac_power_kw": df["ac_power_kw"],
        "energy_kwh": df["energy_kwh"],
        # Labels, for scoring only (Contract 5). Rows from before severity was
        # stored count as faulted with unknown severity (0 here).
        "is_fault": df["fault_active"].fillna(False).astype(bool),
        "fault_severity": df["fault_severity"].astype(float),
    })
    # Wind wasn't stored before telemetry carried it; a constant fill keeps the
    # feature harmless rather than dropping those rows.
    numeric = ["ghi", "dni", "dhi", "poa_irradiance", "air_temp", "cell_temp", "wind_speed", "cloud_cover"]
    out[numeric] = out[numeric].astype(float)
    out["wind_speed"] = out["wind_speed"].fillna(out["wind_speed"].median()).fillna(0.0)
    out = out.dropna(subset=["ghi", "dni", "dhi", "poa_irradiance", "air_temp", "cell_temp", "cloud_cover"])
    out["fault_severity"] = out["fault_severity"].fillna(0.0)

    mid = pd.DatetimeIndex(out["timestamp"]) - pd.Timedelta(minutes=NATIVE_STEP_FALLBACK_MINUTES / 2)
    out["solar_elevation"] = _solar_elevation(plant["latitude"], plant["longitude"], mid).round(2)
    out["is_daylight"] = out["solar_elevation"] > DAYLIGHT_MIN_ELEVATION_DEG
    return out.reset_index(drop=True)


def hourly_frame(plant: dict, native: pd.DataFrame) -> pd.DataFrame:
    """Native readings -> one row per inverter per hour (interval end), the
    cadence the models were built and evaluated on."""
    if native.empty:
        return native
    df = native.copy()
    df["timestamp"] = df["timestamp"].dt.ceil("h")
    values = ["ghi", "dni", "dhi", "poa_irradiance", "air_temp", "cell_temp", "wind_speed",
              "cloud_cover", "dc_power_kw", "ac_power_kw", "fault_severity"]
    hourly = df.groupby(["timestamp", "inverter"], as_index=False).agg(
        **{c: (c, "mean") for c in values}, is_fault=("is_fault", "any"),
    )
    mid = pd.DatetimeIndex(hourly["timestamp"]) - pd.Timedelta(minutes=30)
    hourly["solar_elevation"] = _solar_elevation(plant["latitude"], plant["longitude"], mid).round(2)
    hourly["is_daylight"] = hourly["solar_elevation"] > DAYLIGHT_MIN_ELEVATION_DEG
    cols = ["timestamp", "inverter", "ghi", "dni", "dhi", "poa_irradiance", "air_temp", "cell_temp",
            "wind_speed", "cloud_cover", "solar_elevation", "is_daylight", "dc_power_kw", "ac_power_kw",
            "is_fault", "fault_severity"]
    return hourly[cols].sort_values(["timestamp", "inverter"]).reset_index(drop=True)


def load_hourly(db: UserSupabase, plant: dict, inverters: list[dict], since: pd.Timestamp,
                until: pd.Timestamp | None = None) -> pd.DataFrame:
    ids = [inv["id"] for inv in inverters]
    readings = db.readings(ids, since, until)
    weather = db.weather(plant["id"], since)
    return hourly_frame(plant, native_frame(plant, inverters, readings, weather))
