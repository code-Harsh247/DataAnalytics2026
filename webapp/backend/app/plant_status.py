"""GET /api/plants/{plant_id}/status (Contract 6b): the live verdict -- is
each inverter producing what it should, right now?

- The fixed model (Random Forest, chosen once on the canonical benchmark) is
  trained on the plant's stored history up to 24 h ago, at the hourly
  cadence it was built for, and cached per plant for RETRAIN_AFTER.
- Recent readings are scored at their native interval with a *trailing*
  median (only past readings), so this works live. The retrospective 30-day
  analysis keeps its centred smoothing; a live verdict can't look ahead.
- Fault labels are never read here.
"""

import threading

import numpy as np
import pandas as pd

from .models.base import LABEL_COLUMNS
from .models.random_forest import RandomForestModel
from .plant_data import InsufficientData, UserSupabase, load_hourly, native_frame

MODEL_NAME = "random_forest"
HISTORY_DAYS = 30
RECENT_HOURS = 24
RETRAIN_AFTER = pd.Timedelta(hours=6)
TRAILING_READINGS = 6      # smoothing window, in readings
CONSECUTIVE_FLAGS = 3      # flagged daylight readings in a row before we say so
MIN_EXPECTED_KW = 0.05
MIN_TRAIN_DAYLIGHT_HOURS = 40  # per inverter, ~4 days
MIN_OFFLINE_AFTER = pd.Timedelta(minutes=2)  # offline = no reading for 3 intervals, at least this
MAX_READING_HOURS = 0.25   # cap on the energy one reading can stand for

_cache: dict[str, tuple[RandomForestModel, pd.Timestamp, tuple[str, ...]]] = {}
_cache_lock = threading.Lock()


def _model_for(db: UserSupabase, plant: dict, inverters: list[dict], now: pd.Timestamp) -> RandomForestModel | None:
    labels = tuple(inv["label"] for inv in inverters)
    with _cache_lock:
        cached = _cache.get(plant["id"])
    if cached and now - cached[1] < RETRAIN_AFTER and cached[2] == labels:
        return cached[0]

    cutoff = now - pd.Timedelta(hours=RECENT_HOURS)
    history = load_hourly(db, plant, inverters, now - pd.Timedelta(days=HISTORY_DAYS), cutoff)
    if history.empty or history["is_daylight"].sum() / len(inverters) < MIN_TRAIN_DAYLIGHT_HOURS:
        return None
    model = RandomForestModel()
    model.fit(history.drop(columns=LABEL_COLUMNS))
    with _cache_lock:
        _cache[plant["id"]] = (model, now, labels)
    return model


def _offline_after(native: pd.DataFrame) -> pd.Timedelta:
    times = pd.Series(native["timestamp"].unique()).sort_values()
    if len(times) < 3:
        return MIN_OFFLINE_AFTER
    interval = times.diff().iloc[-20:].median()
    return max(3 * interval, MIN_OFFLINE_AFTER)


def _iso(ts: pd.Timestamp | None) -> str | None:
    return None if ts is None or pd.isna(ts) else ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def plant_status(db: UserSupabase, plant_id: str) -> dict:
    now = pd.Timestamp.now(tz="UTC")
    plant = db.plant(plant_id)
    inverters = db.inverters(plant_id)
    gateway = db.gateway(plant_id)
    tariff = plant.get("tariff_per_kwh") or 0.0

    since = now - pd.Timedelta(hours=RECENT_HOURS)
    readings = db.readings([inv["id"] for inv in inverters], since) if inverters else pd.DataFrame()
    try:
        native = native_frame(plant, inverters, readings, db.weather(plant_id, since))
    except InsufficientData:
        native = pd.DataFrame()

    offline_after = _offline_after(native) if not native.empty else MIN_OFFLINE_AFTER
    connected = bool(gateway and gateway.get("last_seen_at")
                     and now - pd.Timestamp(gateway["last_seen_at"]) <= offline_after)
    result = {
        "as_of": _iso(now),
        "model": MODEL_NAME,
        "gateway": None if gateway is None else {
            "connected": connected, "serial": gateway.get("serial"),
            "last_seen_at": gateway.get("last_seen_at"),
        },
        "inverters": [],
    }
    if len(inverters) < 2 or native.empty:
        result["inverters"] = [{"label": inv["label"], "state": "no_data"} for inv in inverters]
        return result

    model = _model_for(db, plant, inverters, now)
    if model is None:
        result["inverters"] = [{"label": inv["label"], "state": "learning"} for inv in inverters]
        return result

    pred = model.predict(native.drop(columns=LABEL_COLUMNS))
    expected = pred["expected_kw"].to_numpy()
    pred["raw_score"] = (expected - pred["ac_power_kw"].to_numpy()) / np.clip(expected, MIN_EXPECTED_KW, None)

    for inv in inverters:
        label = inv["label"]
        rows = pred[pred["inverter"] == label].sort_values("timestamp")
        latest = rows["timestamp"].max() if len(rows) else None
        entry = {"label": label, "state": "ok", "shortfall_pct": None, "since": None,
                 "est_kwh_lost_24h": 0.0, "est_revenue_lost_24h": 0.0,
                 "latest_at": _iso(latest)}

        day = rows[rows["is_daylight"]].copy()
        if len(day):
            day["smoothed"] = day["raw_score"].rolling(TRAILING_READINGS, min_periods=3).median()
            day["flagged"] = day["smoothed"] > model.threshold
            hours = day["timestamp"].diff().dt.total_seconds().div(3600).clip(upper=MAX_READING_HOURS)
            hours = hours.fillna(MAX_READING_HOURS)
            lost = (day["expected_kw"] - day["ac_power_kw"]).clip(lower=0) * hours
            kwh_lost = float(lost[day["flagged"]].sum())
            entry["est_kwh_lost_24h"] = round(kwh_lost, 3)
            entry["est_revenue_lost_24h"] = round(kwh_lost * tariff, 2)
            entry["shortfall_pct"] = round(float(day["raw_score"].iloc[-TRAILING_READINGS:].median()) * 100, 1)

            tail = day["flagged"].iloc[-CONSECUTIVE_FLAGS:]
            if len(tail) == CONSECUTIVE_FLAGS and tail.all():
                entry["state"] = "underperforming"
                run_start = day["timestamp"].iloc[-1]
                for ts, flagged in zip(day["timestamp"].iloc[::-1], day["flagged"].iloc[::-1]):
                    if not flagged:
                        break
                    run_start = ts
                entry["since"] = _iso(run_start)

        if latest is None or now - latest > offline_after:
            entry["state"] = "offline"
        result["inverters"].append(entry)
    return result
