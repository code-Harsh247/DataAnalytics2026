"""The gateway's only link to the cloud: Supabase RPC calls with the public
anon key plus its own device token. It never holds a user's credentials."""

import json
import os
import secrets
from pathlib import Path

import requests

from app.seed_supabase import read_env_file

STATE_FILE = Path(__file__).resolve().parent / ".gateway.json"
BATCH_ROWS = 1500  # ingest_telemetry accepts at most 2000 rows of each kind


class GatewayError(RuntimeError):
    pass


def supabase_settings() -> tuple[str, str]:
    env = {**read_env_file(), **os.environ}
    url = env.get("SUPABASE_URL") or env.get("NEXT_PUBLIC_SUPABASE_URL")
    key = env.get("SUPABASE_ANON_KEY") or env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not url or not key:
        raise GatewayError(
            "Missing Supabase URL / anon key: set SUPABASE_URL and SUPABASE_ANON_KEY, "
            "or create webapp/frontend/.env.local")
    return url.rstrip("/"), key


def new_serial() -> str:
    return f"SIM-GW-{secrets.token_hex(2).upper()}"


class Cloud:
    def __init__(self, token: str | None = None):
        self.url, key = supabase_settings()
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"apikey": key, "Content-Type": "application/json"})

    def rpc(self, fn: str, **params) -> dict:
        resp = self.session.post(f"{self.url}/rest/v1/rpc/{fn}", json=params, timeout=60)
        if not resp.ok:
            try:
                message = resp.json().get("message", resp.text)
            except ValueError:
                message = resp.text
            if resp.status_code == 404 and "function" in message.lower():
                message += " -- has webapp/supabase/005_devices.sql been run?"
            raise GatewayError(f"{fn} failed ({resp.status_code}): {message}")
        return resp.json()

    def pair(self, code: str, serial: str) -> dict:
        return self.rpc("pair_gateway", p_code=code, p_serial=serial)

    def state(self) -> dict:
        return self.rpc("gateway_state", p_token=self.token)

    def ingest(self, weather: list[dict], readings: list[dict]) -> tuple[int, int]:
        """Uploads in batches; returns (weather rows, readings) actually inserted."""
        inserted_w = inserted_r = 0
        steps = max(len(weather), len(readings), 1)
        for i in range(0, steps, BATCH_ROWS):
            result = self.rpc(
                "ingest_telemetry", p_token=self.token,
                p_weather=weather[i:i + BATCH_ROWS], p_readings=readings[i:i + BATCH_ROWS],
            )
            inserted_w += result["inserted_weather"]
            inserted_r += result["inserted_readings"]
        return inserted_w, inserted_r


def save_state(token: str, serial: str) -> None:
    STATE_FILE.write_text(json.dumps({"token": token, "serial": serial}, indent=2) + "\n")


def load_state() -> dict:
    if not STATE_FILE.exists():
        raise GatewayError("Not paired yet: run `python -m gateway pair <CODE>` with the code from the app.")
    return json.loads(STATE_FILE.read_text())
