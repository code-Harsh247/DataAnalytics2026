"""Seed a real, configured plant in Supabase with ~30 days of history, so the
live dashboard has a month of weather, generation, revenue and faults to show
immediately instead of only what accumulated while a browser tab was open.

Same data the live pipeline would have produced (real Open-Meteo weather at
15-minute resolution, the backfill physics, per-inverter efficiency from the
plant's stored inverters), written to the same tables. Signs in as the plant
owner with email/password, so Row Level Security applies exactly as it does
in the browser -- no service_role key involved.

Usage (from webapp/backend; Supabase URL/key are read from
webapp/frontend/.env.local):
    .venv/bin/python -m app.seed_supabase --dry-run       # generate only, no login
    SEED_EMAIL=you@example.com .venv/bin/python -m app.seed_supabase
        (password is prompted; or set SEED_PASSWORD)

Safe to re-run: readings at an existing timestamp are skipped, and fault
episodes already stored are not duplicated.
"""

import argparse
import getpass
import os
import random
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pvlib
import requests

from .backfill import build_dataset, fetch_recent_weather_15min

ENV_FILE = Path(__file__).resolve().parents[2] / "frontend" / ".env.local"
BATCH_SIZE = 1000
INTERVAL_HOURS = 0.25
SEED = 7

# Mirrors resolvePlantDefaults() in frontend/src/lib/generation.ts -- keep in sync.
DEFAULT_INVERTER_COUNT = 4
DEFAULT_CAPACITY_KW = 5.0
TYPICAL_PANEL_DENSITY_W_PER_SQM = 150
MODULE_TEMP_COEFFICIENTS = {
    "Monocrystalline": -0.0035, "Polycrystalline": -0.0041, "Thin-film": -0.0025, "Other": -0.0038,
}
DEFAULT_TEMP_COEFFICIENT = -0.0038
ANNUAL_DEGRADATION_RATE = 0.005
MIN_DEGRADATION_FACTOR = 0.7


def resolve_plant_defaults(plant: dict) -> dict:
    capacity = plant.get("capacity_kw")
    if not capacity and plant.get("panel_count") and plant.get("module_wattage_w"):
        capacity = plant["panel_count"] * plant["module_wattage_w"] / 1000
    if not capacity and plant.get("area_sqm"):
        capacity = plant["area_sqm"] * TYPICAL_PANEL_DENSITY_W_PER_SQM / 1000
    capacity = capacity or DEFAULT_CAPACITY_KW

    lat = plant["latitude"]
    tilt = plant.get("tilt_degrees")
    azimuth = plant.get("azimuth_degrees")

    degradation = 1.0
    if plant.get("commissioning_date"):
        age_years = (date.today() - date.fromisoformat(plant["commissioning_date"][:10])).days / 365.25
        if age_years > 0:
            degradation = max(1 - ANNUAL_DEGRADATION_RATE * age_years, MIN_DEGRADATION_FACTOR)

    return {
        "capacity_kw": capacity,
        "tilt": tilt if tilt is not None else min(max(abs(lat), 10), 40),
        "azimuth": azimuth if azimuth is not None else (180 if lat >= 0 else 0),
        "inverter_count": plant.get("inverter_count") or DEFAULT_INVERTER_COUNT,
        "temp_coefficient": MODULE_TEMP_COEFFICIENTS.get(plant.get("module_type"), DEFAULT_TEMP_COEFFICIENT),
        "degradation_factor": degradation,
    }


def read_env_file() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


class Supabase:
    def __init__(self, url: str, anon_key: str):
        self.url = url.rstrip("/")
        self.headers = {"apikey": anon_key, "Content-Type": "application/json"}

    def sign_in(self, email: str, password: str) -> None:
        resp = requests.post(
            f"{self.url}/auth/v1/token?grant_type=password",
            headers=self.headers, json={"email": email, "password": password}, timeout=20,
        )
        if not resp.ok:
            raise SystemExit(f"Sign-in failed ({resp.status_code}): {resp.text}")
        self.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"

    def _check(self, resp: requests.Response) -> requests.Response:
        if not resp.ok:
            raise SystemExit(f"Supabase error ({resp.status_code}) on {resp.request.method} "
                             f"{resp.url}: {resp.text}")
        return resp

    def select(self, table: str, params: dict) -> list[dict]:
        return self._check(requests.get(
            f"{self.url}/rest/v1/{table}", headers=self.headers, params=params, timeout=30,
        )).json()

    def insert(self, table: str, rows: list[dict], on_conflict: str | None = None) -> list[dict]:
        prefer = "return=representation"
        params = {}
        if on_conflict:
            prefer += ",resolution=ignore-duplicates"
            params["on_conflict"] = on_conflict
        out = []
        for i in range(0, len(rows), BATCH_SIZE):
            resp = self._check(requests.post(
                f"{self.url}/rest/v1/{table}", params=params, json=rows[i:i + BATCH_SIZE],
                headers={**self.headers, "Prefer": prefer}, timeout=60,
            ))
            out.extend(resp.json())
        return out


def iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def weather_rows(dataset: pd.DataFrame, lat: float, lon: float, plant_id: str) -> list[dict]:
    """One row per timestamp, with the clear-sky fields weather.py computes live."""
    w = dataset.drop_duplicates("timestamp").reset_index(drop=True)
    location = pvlib.location.Location(lat, lon, tz="UTC")
    times = pd.DatetimeIndex(w["timestamp"])
    clearsky = location.get_clearsky(times, model="ineichen")["ghi"].to_numpy()
    elevation = location.get_solarposition(times)["apparent_elevation"].to_numpy()

    rows = []
    for i, r in w.iterrows():
        index = None
        if elevation[i] > 5 and clearsky[i] > 0:
            index = round(float(r.ghi) / float(clearsky[i]), 3)
        rows.append({
            "plant_id": plant_id, "recorded_at": iso(r.timestamp),
            "temperature_c": float(r.air_temp), "cloud_cover_pct": float(r.cloud_cover),
            "ghi_wm2": float(r.ghi), "dni_wm2": float(r.dni), "dhi_wm2": float(r.dhi),
            "clearsky_ghi_wm2": round(float(clearsky[i]), 1), "clearsky_index": index,
        })
    return rows


def generation_rows(dataset: pd.DataFrame, inverter_ids: dict, tariff: float) -> list[dict]:
    return [
        {
            "inverter_id": inverter_ids[r.inverter], "recorded_at": iso(r.timestamp),
            "dc_power_kw": float(r.dc_power_kw), "ac_power_kw": float(r.ac_power_kw),
            "cell_temp_c": float(r.cell_temp), "poa_irradiance_wm2": float(r.poa_irradiance),
            "fault_active": bool(r.is_fault),
            "revenue_per_interval": round(float(r.ac_power_kw) * INTERVAL_HOURS * tariff, 4),
        }
        for r in dataset.itertuples()
    ]


def fault_episodes(dataset: pd.DataFrame, inverter_ids: dict, step: pd.Timedelta) -> list[dict]:
    """Contiguous runs of the same nonzero severity -> inverter_faults rows."""
    episodes = []
    for label, g in dataset.sort_values("timestamp").groupby("inverter"):
        run_id = (g["fault_severity"] != g["fault_severity"].shift()).cumsum()
        for _, run in g[g["fault_severity"] > 0].groupby(run_id[g["fault_severity"] > 0]):
            episodes.append({
                "inverter_id": inverter_ids[label],
                "started_at": iso(run["timestamp"].min()),
                "ends_at": iso(run["timestamp"].max() + step),
                "severity": float(run["fault_severity"].iloc[0]),
            })
    return episodes


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--plant-id", help="which plant, if the account has several")
    p.add_argument("--dry-run", action="store_true",
                   help="generate for a sample plant (18N, 80E, 7.5kW) and print counts; no login, no writes")
    args = p.parse_args()

    if args.dry_run:
        plant = {"id": "dry-run", "latitude": 18.0, "longitude": 80.0, "capacity_kw": 7.5,
                 "inverter_count": 4, "tariff_per_kwh": 6.0, "module_type": "Monocrystalline"}
        inverters = [{"id": f"inv-{i}", "label": f"INV-{i}", "base_efficiency_factor": 1.0} for i in range(1, 5)]
        db = None
    else:
        env = {**read_env_file(), **os.environ}
        url, key = env.get("NEXT_PUBLIC_SUPABASE_URL"), env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        if not url or not key:
            raise SystemExit(f"Missing NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY (looked in {ENV_FILE} and env)")
        email = env.get("SEED_EMAIL") or input("Supabase account email: ")
        password = env.get("SEED_PASSWORD") or getpass.getpass("Password: ")

        db = Supabase(url, key)
        db.sign_in(email, password)
        plants = db.select("plants", {"select": "*"})
        if args.plant_id:
            plants = [pl for pl in plants if pl["id"] == args.plant_id]
        if not plants:
            raise SystemExit("No plant found for this account -- set one up in the app first.")
        plant = plants[0]

        inverters = db.select("inverters", {"select": "*", "plant_id": f"eq.{plant['id']}"})
        if not inverters:
            count = resolve_plant_defaults(plant)["inverter_count"]
            inverters = db.insert("inverters", [
                {"plant_id": plant["id"], "label": f"INV-{i + 1}",
                 "base_efficiency_factor": 0.96 + random.random() * 0.06}  # same spread as the app
                for i in range(count)
            ])

    inverters.sort(key=lambda inv: int(inv["label"].split("-")[-1]))
    cfg = resolve_plant_defaults(plant)
    lat, lon = plant["latitude"], plant["longitude"]
    print(f"Plant '{plant.get('name', plant['id'])}' at ({lat}, {lon}): {cfg['capacity_kw']:.2f} kW, "
          f"{len(inverters)} inverters, tilt {cfg['tilt']}, azimuth {cfg['azimuth']}")

    weather = fetch_recent_weather_15min(lat, lon, args.days)
    dataset = build_dataset(
        lat, lon, "", "", capacity_kw=cfg["capacity_kw"], tilt=cfg["tilt"], azimuth=cfg["azimuth"],
        inverter_count=len(inverters), temp_coefficient=cfg["temp_coefficient"],
        degradation_factor=cfg["degradation_factor"], seed=SEED, weather=weather, step_minutes=15,
        efficiencies=[inv["base_efficiency_factor"] for inv in inverters],
    )
    inverter_ids = {f"INV-{i + 1}": inv["id"] for i, inv in enumerate(inverters)}
    tariff = plant.get("tariff_per_kwh") or 0.0

    w_rows = weather_rows(dataset, lat, lon, plant["id"])
    g_rows = generation_rows(dataset, inverter_ids, tariff)
    f_rows = fault_episodes(dataset, inverter_ids, pd.Timedelta(minutes=15))
    energy = dataset["ac_power_kw"].sum() * INTERVAL_HOURS
    print(f"Generated {iso(dataset['timestamp'].min())} .. {iso(dataset['timestamp'].max())}: "
          f"{len(w_rows)} weather rows, {len(g_rows)} generation rows, {len(f_rows)} fault episodes, "
          f"{energy:.0f} kWh, revenue {energy * tariff:.0f}")

    if db is None:
        print("Dry run -- nothing written.")
        return

    existing = db.select("inverter_faults", {
        "select": "inverter_id,started_at",
        "inverter_id": f"in.({','.join(inverter_ids.values())})",
    })
    seen = {(f["inverter_id"], pd.Timestamp(f["started_at"])) for f in existing}
    f_rows = [f for f in f_rows if (f["inverter_id"], pd.Timestamp(f["started_at"])) not in seen]

    new_w = db.insert("weather_readings", w_rows, on_conflict="plant_id,recorded_at")
    new_g = db.insert("generation_readings", g_rows, on_conflict="inverter_id,recorded_at")
    new_f = db.insert("inverter_faults", f_rows) if f_rows else []
    print(f"Inserted {len(new_w)} weather, {len(new_g)} generation, {len(new_f)} fault rows "
          f"(existing timestamps skipped). Reload the dashboard.")


if __name__ == "__main__":
    main()
