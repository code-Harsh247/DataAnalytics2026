"""Shared building blocks for the plant pages (Contract 7, PRODUCT_PLAN.md
"Product MVP"): one cached frame of a plant's recent readings with energy,
physics-expected output and irradiance per reading, plus the plant's time
zone and calibration. Every page metric is computed from this one frame, so
Overview, Production, Forecast, Health and Finance agree with each other.

Definitions (performance ratio, specific yield, calibration, ...) are in the
plan; the short version is in each function's docstring.
"""

import threading
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import requests

from .backfill import FORECAST_URL, compute_plant_physics
from .plant_data import UserSupabase
from .seed_supabase import resolve_plant_defaults
from .synthetic_generation import INVERTER_EFFICIENCY

CO2_KG_PER_KWH = 0.716  # CEA baseline, Indian grid
WINDOW_DAYS = 35  # enough for "this month" plus a 30-day view
CALIBRATION_DAYS = 14
CACHE_SECONDS = 60
MAX_READING_HOURS = 0.25  # a reading never stands for more than 15 min (gaps aren't energy)
DAYLIGHT_POA_WM2 = 20.0
PRODUCING_SHARE = 0.02  # "producing" = more than 2% of its expected output

_tz_cache: dict[tuple[float, float], str] = {}
_frame_cache: dict[str, tuple[float, pd.DataFrame, pd.DataFrame]] = {}
_lock = threading.Lock()


def plant_timezone(lat: float, lon: float) -> str:
    """IANA time zone for the plant (Open-Meteo `timezone=auto`), cached."""
    key = (round(lat, 2), round(lon, 2))
    with _lock:
        if key in _tz_cache:
            return _tz_cache[key]
    try:
        resp = requests.get(FORECAST_URL, timeout=15, params={
            "latitude": lat, "longitude": lon, "hourly": "temperature_2m",
            "forecast_days": 1, "timezone": "auto",
        })
        resp.raise_for_status()
        tz = resp.json()["timezone"]
    except (requests.RequestException, KeyError, ValueError):
        return "UTC"  # not cached: try again next time
    with _lock:
        _tz_cache[key] = tz
    return tz


@dataclass
class PlantData:
    row: dict
    inverters: list[dict]
    cfg: dict  # resolve_plant_defaults(): capacity_kw, tilt, azimuth, temp_coefficient, ...
    tz: str
    frame: pd.DataFrame  # one row per inverter per reading, see _metrics_frame
    readings: pd.DataFrame  # the raw rows behind it (for the detector)
    now: pd.Timestamp
    _calibration: float | None = field(default=None, repr=False)

    @property
    def capacity_kw(self) -> float:
        return float(self.cfg["capacity_kw"])

    @property
    def tariff(self) -> float:
        return float(self.row.get("tariff_per_kwh") or 0.0)

    @property
    def today(self) -> str:
        return self.now.tz_convert(self.tz).date().isoformat()

    @property
    def this_month(self) -> str:
        return self.today[:7]

    @property
    def calibration(self) -> float:
        """Actual / physics-expected energy over the last 14 days of daylight.
        Folds soiling, mismatch, shading and the site's sky bias into one
        factor; every forecast is physics x this. 1.0 until there's data."""
        if self._calibration is None:
            f = self.frame
            recent = f[(f["timestamp"] >= self.now - pd.Timedelta(days=CALIBRATION_DAYS)) & f["daylight"]]
            expected = recent["expected_kwh"].sum()
            self._calibration = float(np.clip(recent["energy_kwh"].sum() / expected, 0.5, 1.2)) if expected > 1 else 1.0
        return self._calibration

    def physics_kw(self, weather: pd.DataFrame, step_minutes: int) -> pd.Series:
        """Plant AC output (kW) the physics model expects for a weather frame
        (columns timestamp, ghi, dni, dhi, air_temp), uncalibrated."""
        phys = compute_plant_physics(weather, self.row["latitude"], self.row["longitude"],
                                     self.cfg["tilt"], self.cfg["azimuth"], step_minutes)
        kw = (self.capacity_kw * phys["poa_irradiance"] / 1000.0
              * (1 + self.cfg["temp_coefficient"] * (phys["cell_temp"] - 25.0))
              * self.cfg["degradation_factor"] * INVERTER_EFFICIENCY)
        return pd.Series(np.clip(kw.to_numpy(), 0, None), index=weather.index)


def _metrics_frame(readings: pd.DataFrame, inverters: list[dict], cfg: dict, tariff: float, tz: str) -> pd.DataFrame:
    """Readings -> one row per inverter per reading with:
    energy_kwh, revenue, hours (what the reading stands for), expected_kw /
    expected_kwh (physics, healthy), potential_kwh (nameplate x irradiance,
    the performance-ratio denominator), insolation_kwh_m2, local_date/month."""
    cols = ["timestamp", "inverter", "ac_power_kw", "energy_kwh", "revenue", "hours", "poa", "cell_temp",
            "expected_kw", "expected_kwh", "potential_kwh", "insolation_kwh_m2", "daylight",
            "local_date", "local_month"]
    if readings.empty:
        return pd.DataFrame(columns=cols)
    labels = {inv["id"]: inv["label"] for inv in inverters}
    df = readings.copy()
    df["timestamp"] = pd.to_datetime(df["recorded_at"], utc=True)
    df["inverter"] = df["inverter_id"].map(labels)
    df = df.dropna(subset=["inverter"]).drop_duplicates(["timestamp", "inverter"])
    df = df.sort_values(["inverter", "timestamp"]).reset_index(drop=True)

    df["ac_power_kw"] = df["ac_power_kw"].astype(float).fillna(0.0)
    hours = df.groupby("inverter")["timestamp"].diff().dt.total_seconds().div(3600)
    df["hours"] = hours.clip(lower=0, upper=MAX_READING_HOURS).fillna(MAX_READING_HOURS)
    df["energy_kwh"] = df["energy_kwh"].astype(float).fillna(df["ac_power_kw"] * df["hours"])
    df["revenue"] = df["revenue_per_interval"].astype(float).fillna(df["energy_kwh"] * tariff)
    df["poa"] = df["poa_irradiance_wm2"].astype(float).fillna(0.0)
    df["cell_temp"] = df["cell_temp_c"].astype(float).fillna(25.0)

    per_inverter_kw = cfg["capacity_kw"] / max(len(inverters), 1)
    df["expected_kw"] = np.clip(
        per_inverter_kw * df["poa"] / 1000.0 * (1 + cfg["temp_coefficient"] * (df["cell_temp"] - 25.0))
        * cfg["degradation_factor"] * INVERTER_EFFICIENCY, 0, None)
    df["expected_kwh"] = df["expected_kw"] * df["hours"]
    df["insolation_kwh_m2"] = df["poa"] * df["hours"] / 1000.0
    df["potential_kwh"] = per_inverter_kw * df["insolation_kwh_m2"]
    df["daylight"] = df["poa"] > DAYLIGHT_POA_WM2
    local = df["timestamp"].dt.tz_convert(tz)
    df["local_date"] = local.dt.strftime("%Y-%m-%d")
    df["local_month"] = local.dt.strftime("%Y-%m")
    return df[cols]


def load_plant(db: UserSupabase, plant_id: str, days: int = WINDOW_DAYS) -> PlantData:
    """The plant (access checked as the user on every call), its inverters and
    the cached readings frame."""
    plant = db.plant(plant_id)  # raises NotFound if this user can't see it
    inverters = db.inverters(plant_id)
    cfg = resolve_plant_defaults(plant)
    tz = plant_timezone(plant["latitude"], plant["longitude"])
    now = pd.Timestamp.now(tz="UTC")

    key = f"{plant_id}:{days}"
    with _lock:
        cached = _frame_cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        frame, readings = cached[1], cached[2]
    else:
        ids = [inv["id"] for inv in inverters]
        readings = db.readings(ids, now - pd.Timedelta(days=days)) if ids else pd.DataFrame()
        frame = _metrics_frame(readings, inverters, cfg, float(plant.get("tariff_per_kwh") or 0.0), tz)
        with _lock:
            _frame_cache[key] = (time.monotonic(), frame, readings)
    return PlantData(row=plant, inverters=inverters, cfg=cfg, tz=tz, frame=frame, readings=readings, now=now)


# ---------------------------------------------------------------- aggregations

def energy_summary(df: pd.DataFrame) -> dict:
    energy = float(df["energy_kwh"].sum())
    return {"energy_kwh": round(energy, 3), "revenue": round(float(df["revenue"].sum()), 2),
            "co2_kg": round(energy * CO2_KG_PER_KWH, 2)}


def performance_ratio(df: pd.DataFrame) -> float | None:
    """IEC 61724 PR: AC energy / (plane-of-array insolation x kWp)."""
    potential = df["potential_kwh"].sum()
    return round(float(df["energy_kwh"].sum() / potential), 3) if potential > 0.05 else None


def plant_power(df: pd.DataFrame) -> pd.Series:
    """Plant AC power (kW) per reading timestamp: the sum over inverters."""
    return df.groupby("timestamp")["ac_power_kw"].sum().sort_index()


def daily(p: PlantData) -> pd.DataFrame:
    """One row per plant-local day."""
    f = p.frame
    if f.empty:
        return pd.DataFrame(columns=["date", "energy_kwh", "revenue", "potential_kwh", "insolation_kwh_m2",
                                     "peak_kw", "readings"])
    g = f.groupby("local_date")
    out = pd.DataFrame({
        "energy_kwh": g["energy_kwh"].sum(),
        "revenue": g["revenue"].sum(),
        "potential_kwh": g["potential_kwh"].sum(),
        # plant-level insolation: the inverters share one sky, so average them
        "insolation_kwh_m2": g["insolation_kwh_m2"].sum() / max(len(p.inverters), 1),
        "readings": g.size(),
    })
    peak = f.groupby(["local_date", "timestamp"])["ac_power_kw"].sum().groupby(level=0).max()
    out["peak_kw"] = peak
    return out.reset_index().rename(columns={"local_date": "date"})


def to_iso(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
