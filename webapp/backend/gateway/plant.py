"""The simulated hardware: a plant's inverters, stepped through time.

Same physics and realism layers as the backfill (app/backfill.py) -- pvlib
plane-of-array irradiance, NOCT cell temperature, temperature derating,
degradation, site irradiance error, per-inverter efficiency and soiling,
unlabelled shading dips, measurement noise, random fault episodes -- but
stateful, one interval at a time, so it can run live and be poked from the
console (`inject`, `clear`).

What a real inverter would *not* know is kept out of the telemetry it
"reports": fault_active / fault_severity travel along only as ground-truth
labels for scoring, per the rule in PRODUCT_PLAN.md Contract 5.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pvlib

from app.backfill import (
    FAULT_MAX_HOURS, FAULT_MAX_SEVERITY, FAULT_MIN_HOURS, FAULT_MIN_SEVERITY,
    FAULT_START_PROB_PER_HOUR, MAX_SOILING_LOSS, NOISE_STD, SHADING_MAX_HOURS,
    SHADING_MAX_LOSS, SHADING_MIN_HOURS, SHADING_MIN_LOSS, SHADING_START_PROB_PER_HOUR,
    SITE_IRRADIANCE_ERROR_STD, compute_plant_physics,
)
from app.seed_supabase import resolve_plant_defaults
from app.synthetic_generation import INVERTER_EFFICIENCY

SITE_ERROR_CORRELATION_MINUTES = 30.0  # the sky's error drifts, it doesn't jump per reading
STRING_VMP_STC = 360.0  # V, a typical residential string at its max-power point
VMP_TEMP_COEFFICIENT = -0.0029  # per degree C
INVERTER_HEATING_C = 18.0  # inverter heatsink rise above ambient at full load


def iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Episode:
    loss: float
    until: pd.Timestamp | None  # None = until cleared from the console


@dataclass
class VirtualInverter:
    id: str
    label: str
    efficiency: float
    soiling: float
    fault: Episode | None = None
    shading: Episode | None = None
    energy_today_kwh: float = 0.0
    day: int | None = None
    last_ac_kw: float = 0.0
    manual_fault: bool = field(default=False)


class VirtualPlant:
    def __init__(self, plant: dict, inverters: list[dict], random_faults: bool = True,
                 seed: int | None = None):
        self.plant = plant
        self.cfg = resolve_plant_defaults(plant)
        self.lat, self.lon = plant["latitude"], plant["longitude"]
        self.tariff = plant.get("tariff_per_kwh") or 0.0
        self.random_faults = random_faults
        self.rng = np.random.default_rng(seed)
        self.location = pvlib.location.Location(self.lat, self.lon, tz="UTC")
        self.per_inverter_kw = self.cfg["capacity_kw"] / max(len(inverters), 1)
        self.site_error = 1.0
        inverters = sorted(inverters, key=lambda inv: int(inv["label"].split("-")[-1]))
        self.inverters = [
            VirtualInverter(
                id=inv["id"], label=inv["label"],
                efficiency=float(inv.get("base_efficiency_factor") or 1.0),
                soiling=float(self.rng.uniform(0, MAX_SOILING_LOSS / 2)),
            )
            for inv in inverters
        ]

    # ------------------------------------------------------------ console hooks

    def find(self, label: str) -> VirtualInverter:
        for inv in self.inverters:
            if inv.label.upper() == label.upper():
                return inv
        raise KeyError(f"No inverter {label!r}; have {', '.join(i.label for i in self.inverters)}")

    def inject(self, label: str, loss: float, until: pd.Timestamp | None) -> None:
        inv = self.find(label)
        inv.fault = Episode(loss=loss, until=until)
        inv.manual_fault = True

    def clear(self, label: str | None = None) -> None:
        for inv in self.inverters:
            if label is None or inv.label.upper() == label.upper():
                inv.fault = None
                inv.manual_fault = False

    # ------------------------------------------------------------ simulation

    def physics(self, weather: pd.DataFrame, step_minutes: float) -> pd.DataFrame:
        """Vectorised sun position / panel irradiance / cell temperature /
        clear-sky irradiance for a batch of timestamps (one row per interval end)."""
        out = compute_plant_physics(weather, self.lat, self.lon, self.cfg["tilt"],
                                    self.cfg["azimuth"], step_minutes)
        times = pd.DatetimeIndex(out["timestamp"])
        out["clearsky_ghi"] = self.location.get_clearsky(times, model="ineichen")["ghi"].to_numpy()
        return out

    def _episode(self, current: Episode | None, ts: pd.Timestamp, hours: float, start_prob_per_hour: float,
                 min_hours: float, max_hours: float, min_loss: float, max_loss: float) -> Episode | None:
        if current is not None and (current.until is None or ts < current.until):
            return current
        if self.rng.random() < start_prob_per_hour * hours:
            duration = pd.Timedelta(hours=float(self.rng.uniform(min_hours, max_hours)))
            return Episode(loss=float(self.rng.uniform(min_loss, max_loss)), until=ts + duration)
        return None

    def step(self, row: pd.Series, step_minutes: float) -> tuple[dict, list[dict]]:
        """One interval ending at row.timestamp -> (weather row, one reading per
        inverter), both in the Contract 5 payload shape."""
        ts: pd.Timestamp = row["timestamp"]
        hours = step_minutes / 60.0

        # Shared sky error: AR(1) around 1, so it drifts smoothly at any cadence.
        rho = float(np.exp(-step_minutes / SITE_ERROR_CORRELATION_MINUTES))
        shock = self.rng.normal(0, SITE_IRRADIANCE_ERROR_STD * np.sqrt(1 - rho ** 2))
        self.site_error = float(np.clip(1 + rho * (self.site_error - 1) + shock, 0.8, 1.2))

        poa, cell = float(row["poa_irradiance"]), float(row["cell_temp"])
        clean_dc = max(
            self.per_inverter_kw * (poa / 1000.0) * (1 + self.cfg["temp_coefficient"] * (cell - 25.0)), 0.0,
        ) * self.cfg["degradation_factor"] * self.site_error

        local_day = (ts + pd.Timedelta(hours=self.lon / 15.0)).dayofyear  # resets near local midnight
        readings = []
        for inv in self.inverters:
            if inv.manual_fault:
                if inv.fault is not None and inv.fault.until is not None and ts >= inv.fault.until:
                    inv.fault, inv.manual_fault = None, False
            elif self.random_faults:
                inv.fault = self._episode(inv.fault, ts, hours, FAULT_START_PROB_PER_HOUR,
                                          FAULT_MIN_HOURS, FAULT_MAX_HOURS, FAULT_MIN_SEVERITY, FAULT_MAX_SEVERITY)
            inv.shading = self._episode(inv.shading, ts, hours, SHADING_START_PROB_PER_HOUR,
                                        SHADING_MIN_HOURS, SHADING_MAX_HOURS, SHADING_MIN_LOSS, SHADING_MAX_LOSS)
            fault_loss = inv.fault.loss if inv.fault else 0.0
            shading_loss = inv.shading.loss if inv.shading else 0.0
            noise = float(np.clip(self.rng.normal(1.0, NOISE_STD), 0.85, 1.15))

            dc = clean_dc * inv.efficiency * (1 - inv.soiling) * (1 - fault_loss) * (1 - shading_loss) * noise
            ac = dc * INVERTER_EFFICIENCY
            energy = ac * hours
            if inv.day != local_day:
                inv.day, inv.energy_today_kwh = local_day, 0.0
            inv.energy_today_kwh += energy
            inv.last_ac_kw = ac

            producing = ac > 0.005
            voltage = STRING_VMP_STC * (1 + VMP_TEMP_COEFFICIENT * (cell - 25.0)) if producing else 0.0
            readings.append({
                "inverter_id": inv.id, "recorded_at": iso(ts),
                "ac_power_kw": round(ac, 4), "dc_power_kw": round(dc, 4),
                "energy_kwh": round(energy, 5), "revenue_per_interval": round(energy * self.tariff, 4),
                "dc_voltage_v": round(voltage, 1),
                "dc_current_a": round(dc * 1000 / voltage, 3) if producing else 0.0,
                "inverter_temp_c": round(float(row["air_temp"]) + INVERTER_HEATING_C * ac / self.per_inverter_kw, 1),
                "cell_temp_c": round(cell, 2), "poa_irradiance_wm2": round(poa, 1),
                "energy_today_kwh": round(inv.energy_today_kwh, 4),
                "status_code": "producing" if producing else "standby",
                # Ground-truth labels: for scoring only, never displayed.
                "fault_active": fault_loss > 0, "fault_severity": round(fault_loss, 3),
            })

        clearsky = float(row["clearsky_ghi"])
        index = None
        if float(row["solar_elevation"]) > 5 and clearsky > 0:
            index = round(float(row["ghi"]) / clearsky, 3)
        weather = {
            "recorded_at": iso(ts), "temperature_c": round(float(row["air_temp"]), 2),
            "cloud_cover_pct": round(float(row["cloud_cover"]), 1),
            "ghi_wm2": round(float(row["ghi"]), 1), "dni_wm2": round(float(row["dni"]), 1),
            "dhi_wm2": round(float(row["dhi"]), 1), "wind_speed_kmh": round(float(row["wind_speed"]), 1),
            "clearsky_ghi_wm2": round(clearsky, 1), "clearsky_index": index,
        }
        return weather, readings
