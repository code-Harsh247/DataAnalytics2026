"""Synthetic panel-output generation: turns real weather + real plant specs
into fake-but-physically-grounded power readings. This is the deferred
"hardware part" from the brainstorm -- since there's no real inverter
hardware, we don't have real power readings, but we can still ground the
numbers in real physics (pvlib plane-of-array transposition, a standard
temperature-derating model) instead of making them up outright.

Stateless and Supabase-unaware, same as weather.py: takes weather + plant
specs + per-inverter state as input, returns computed readings. All state
(inverter identity, active faults) lives in Supabase and is read/written by
the frontend, which has the RLS-scoped session.
"""

import pandas as pd
import pvlib
from pydantic import BaseModel

TEMP_COEFFICIENT = -0.004  # per degree C above 25C, typical crystalline silicon
NOCT_C = 45.0  # Nominal Operating Cell Temperature, typical panel datasheet value
INVERTER_EFFICIENCY = 0.97


def estimate_cell_temp(ambient_temp_c: float, poa_irradiance_wm2: float) -> float:
    """Simple NOCT-based cell temperature model."""
    return ambient_temp_c + (NOCT_C - 20.0) / 800.0 * poa_irradiance_wm2


def compute_poa_irradiance(
    lat: float, lon: float, tilt_degrees: float, azimuth_degrees: float,
    timestamp: str, ghi_wm2: float, dni_wm2: float, dhi_wm2: float,
) -> float:
    location = pvlib.location.Location(lat, lon, tz="UTC")
    times = pd.DatetimeIndex([pd.Timestamp(timestamp, tz="UTC")])
    solpos = location.get_solarposition(times)

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt_degrees,
        surface_azimuth=azimuth_degrees,
        solar_zenith=solpos["apparent_zenith"].iloc[0],
        solar_azimuth=solpos["azimuth"].iloc[0],
        dni=dni_wm2,
        ghi=ghi_wm2,
        dhi=dhi_wm2,
    )
    return max(float(poa["poa_global"]), 0.0)


def compute_dc_power_kw(capacity_kw: float, poa_irradiance_wm2: float, cell_temp_c: float) -> float:
    return max(
        capacity_kw * (poa_irradiance_wm2 / 1000.0) * (1 + TEMP_COEFFICIENT * (cell_temp_c - 25.0)),
        0.0,
    )


class InverterState(BaseModel):
    id: str
    base_efficiency_factor: float = 1.0
    active_fault_severity: float = 0.0


class GenerateRequest(BaseModel):
    lat: float
    lon: float
    capacity_kw: float
    tilt_degrees: float
    azimuth_degrees: float
    timestamp: str
    ghi_wm2: float
    dni_wm2: float
    dhi_wm2: float
    temperature_c: float
    inverters: list[InverterState]


def generate(req: GenerateRequest) -> dict:
    poa = compute_poa_irradiance(
        req.lat, req.lon, req.tilt_degrees, req.azimuth_degrees,
        req.timestamp, req.ghi_wm2, req.dni_wm2, req.dhi_wm2,
    )
    cell_temp = estimate_cell_temp(req.temperature_c, poa)

    n = max(len(req.inverters), 1)
    per_inverter_capacity = req.capacity_kw / n

    readings = []
    for inv in req.inverters:
        base_dc = compute_dc_power_kw(per_inverter_capacity, poa, cell_temp)
        dc_power = base_dc * inv.base_efficiency_factor * (1 - inv.active_fault_severity)
        ac_power = dc_power * INVERTER_EFFICIENCY
        readings.append({
            "inverter_id": inv.id,
            "dc_power_kw": round(dc_power, 3),
            "ac_power_kw": round(ac_power, 3),
            "fault_active": inv.active_fault_severity > 0,
        })

    return {
        "poa_irradiance_wm2": round(poa, 1),
        "cell_temp_c": round(cell_temp, 1),
        "readings": readings,
    }
