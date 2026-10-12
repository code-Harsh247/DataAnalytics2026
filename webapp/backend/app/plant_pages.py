"""The payload behind each plant page (Contract 7): Overview, Production,
Forecast, Health, Finance. All built on plant_metrics.load_plant(), so the
same numbers show up the same way everywhere."""

import numpy as np
import pandas as pd
import requests

from .models.base import LABEL_COLUMNS
from .plant_data import InsufficientData, UserSupabase, native_frame
from .plant_forecast import _hourly_kw, forecast, forecast_weather, typical_year, actual_curve
from .plant_metrics import (
    CO2_KG_PER_KWH, MAX_READING_HOURS, PRODUCING_SHARE, PlantData, daily, energy_summary,
    load_plant, performance_ratio, to_iso,
)
from . import plant_status

PAGE_DAYS = 30
MIN_EPISODE_READINGS = 3
MAX_ALERTS = 50
ONGOING_WITHIN = pd.Timedelta(hours=14)  # an episode still flagged at the last daylight reading, overnight included


def _lifetime(db: UserSupabase, p: PlantData) -> dict:
    totals = db.rpc("plant_totals", p_plant_id=p.row["id"])
    energy = float(totals.get("total_energy_kwh") or 0.0)
    return {"energy_kwh": round(energy, 2), "revenue": round(float(totals.get("total_revenue") or 0.0), 2),
            "co2_kg": round(energy * CO2_KG_PER_KWH, 1)}


def _monthly(db: UserSupabase, p: PlantData) -> list[dict]:
    try:
        rows = db.rpc("plant_monthly", p_plant_id=p.row["id"], p_tz=p.tz)
    except requests.HTTPError:
        return []  # 006_finance.sql not run yet
    return [{"month": r["month"], "energy_kwh": round(float(r["energy_kwh"]), 2),
             "revenue": round(float(r["revenue"]), 2)} for r in rows]


def _window(p: PlantData, days: int = PAGE_DAYS) -> pd.DataFrame:
    start = (pd.Timestamp(p.today) - pd.Timedelta(days=days - 1)).strftime("%Y-%m-%d")
    return p.frame[p.frame["local_date"] >= start]


# ---------------------------------------------------------------- Overview

def overview(db: UserSupabase, plant_id: str) -> dict:
    p = load_plant(db, plant_id)
    f = p.frame
    today = f[f["local_date"] == p.today]
    month = f[f["local_month"] == p.this_month]

    now = None
    if not f.empty:
        latest = f["timestamp"].max()
        at = f[f["timestamp"] == latest]
        now = {"power_kw": round(float(at["ac_power_kw"].sum()), 3),
               "expected_kw": round(float(at["expected_kw"].sum()) * p.calibration, 3),
               "as_of": to_iso(latest)}

    try:
        hours = _hourly_kw(p, forecast_weather(p.row["latitude"], p.row["longitude"]))
        today_hours = hours[hours["local_date"] == p.today]
        today_forecast = [{"t": to_iso(r.mid), "kw": round(float(r.kw), 3)} for r in today_hours.itertuples()]
        forecast_today_kwh = round(float(today_hours["kw"].sum()), 2)
    except requests.RequestException:
        today_forecast, forecast_today_kwh = [], None

    return {
        "capacity_kw": round(p.capacity_kw, 2),
        "timezone": p.tz,
        "date": p.today,
        "now": now,
        "today": {**energy_summary(today), "forecast_kwh": forecast_today_kwh},
        "month": energy_summary(month),
        "lifetime": _lifetime(db, p),
        "pr": {"today": performance_ratio(today), "d30": performance_ratio(_window(p))},
        "specific_yield_today": round(float(today["energy_kwh"].sum()) / p.capacity_kw, 2) if p.capacity_kw else None,
        "today_curve": {"actual": actual_curve(p, p.today), "forecast": today_forecast},
    }


# ---------------------------------------------------------------- Production

def production(db: UserSupabase, plant_id: str, days: int = PAGE_DAYS) -> dict:
    p = load_plant(db, plant_id)
    d = daily(p)
    start = (pd.Timestamp(p.today) - pd.Timedelta(days=days - 1)).strftime("%Y-%m-%d")
    d = d[d["date"] >= start] if len(d) else d
    rows = [{
        "date": r.date, "energy_kwh": round(r.energy_kwh, 2), "revenue": round(r.revenue, 2),
        "specific_yield": round(r.energy_kwh / p.capacity_kw, 2),
        "pr": round(r.energy_kwh / r.potential_kwh, 3) if r.potential_kwh > 0.05 else None,
        "peak_kw": round(r.peak_kw, 2), "insolation_kwh_m2": round(r.insolation_kwh_m2, 2),
        "partial": r.date == p.today,
    } for r in d.itertuples()]

    window = _window(p, days)
    per_kw = p.capacity_kw / max(len(p.inverters), 1)
    total = float(window["energy_kwh"].sum()) or 1.0
    inverters = []
    for inv in p.inverters:
        g = window[window["inverter"] == inv["label"]]
        energy = float(g["energy_kwh"].sum())
        inverters.append({"label": inv["label"], "energy_kwh": round(energy, 2),
                          "share": round(energy / total, 3), "pr": performance_ratio(g),
                          "specific_yield": round(energy / per_kw, 2) if per_kw else None})

    complete = [r for r in rows if not r["partial"]]
    best = max(complete, key=lambda r: r["energy_kwh"], default=None)
    worst = min(complete, key=lambda r: r["energy_kwh"], default=None)
    return {
        "capacity_kw": round(p.capacity_kw, 2), "timezone": p.tz, "days": rows,
        "monthly": _monthly(db, p), "inverters": inverters, "best_day": best, "worst_day": worst,
        "totals": {**energy_summary(window), "specific_yield": round(float(window["energy_kwh"].sum()) / p.capacity_kw, 2),
                   "pr": performance_ratio(window)},
    }


# ---------------------------------------------------------------- Forecast

def forecast_page(db: UserSupabase, plant_id: str) -> dict:
    return forecast(load_plant(db, plant_id))


# ---------------------------------------------------------------- Health

def _availability(window: pd.DataFrame, labels: list[str]) -> list[dict]:
    day = window[window["daylight"]]
    slots = day["timestamp"].nunique()
    out = []
    for label in labels:
        g = day[day["inverter"] == label]
        producing = int((g["ac_power_kw"] >= PRODUCING_SHARE * g["expected_kw"]).sum())
        out.append({"label": label, "pct": round(100 * producing / slots, 1) if slots else None})
    return out


def _alerts(db: UserSupabase, p: PlantData) -> tuple[list[dict], float]:
    """Detector episodes over the window: runs of >= 3 flagged daylight readings
    (trailing median, same rule as the live verdict). Returns (alerts, kWh lost)."""
    model = plant_status._model_for(db, p.row, p.inverters, p.now)
    if model is None or p.readings.empty:
        return [], 0.0
    since = p.now - pd.Timedelta(days=PAGE_DAYS)
    try:
        native = native_frame(p.row, p.inverters, p.readings, db.weather(p.row["id"], since))
    except InsufficientData:
        return [], 0.0
    native = native[native["timestamp"] >= since]
    if native.empty:
        return [], 0.0
    pred = model.predict(native.drop(columns=LABEL_COLUMNS))
    expected = pred["expected_kw"].to_numpy()
    pred["raw"] = (expected - pred["ac_power_kw"].to_numpy()) / np.clip(expected, plant_status.MIN_EXPECTED_KW, None)

    alerts, total_lost = [], 0.0
    for label, rows in pred[pred["is_daylight"]].groupby("inverter"):
        rows = rows.sort_values("timestamp").copy()
        rows["smoothed"] = rows["raw"].rolling(plant_status.TRAILING_READINGS, min_periods=3).median()
        rows["flagged"] = rows["smoothed"] > model.threshold
        rows["hours"] = rows["timestamp"].diff().dt.total_seconds().div(3600).clip(upper=MAX_READING_HOURS).fillna(MAX_READING_HOURS)
        rows["lost"] = (rows["expected_kw"] - rows["ac_power_kw"]).clip(lower=0) * rows["hours"]
        run_id = (rows["flagged"] != rows["flagged"].shift()).cumsum()
        last_ts = rows["timestamp"].iloc[-1]
        for _, run in rows[rows["flagged"]].groupby(run_id[rows["flagged"]]):
            if len(run) < MIN_EPISODE_READINGS:
                continue
            lost = float(run["lost"].sum())
            total_lost += lost
            end = run["timestamp"].iloc[-1]
            alerts.append({
                "label": label, "start": to_iso(run["timestamp"].iloc[0]), "end": to_iso(end),
                "ongoing": bool(end == last_ts and p.now - end < ONGOING_WITHIN),
                # the smoothed score is what the detector acted on
                "shortfall_pct": round(float(run["smoothed"].median()) * 100, 1),
                "kwh_lost": round(lost, 2), "revenue_lost": round(lost * p.tariff, 2),
            })
    alerts.sort(key=lambda a: a["start"], reverse=True)
    return alerts[:MAX_ALERTS], total_lost


def _losses(p: PlantData, window: pd.DataFrame, fault_kwh: float) -> list[dict]:
    """Where the sunlight's potential went, in kWh, over the window."""
    gamma, degradation = p.cfg["temp_coefficient"], p.cfg["degradation_factor"]
    potential = window["potential_kwh"]
    temp_factor = 1 + gamma * (window["cell_temp"] - 25.0)
    after_temp = potential * temp_factor
    after_degradation = after_temp * degradation
    expected = window["expected_kwh"]  # = after_degradation x conversion efficiency
    not_producing = window["daylight"] & (window["ac_power_kw"] < PRODUCING_SHARE * window["expected_kw"])
    downtime = float(expected[not_producing].sum())
    actual = float(window["energy_kwh"].sum())
    other = float(expected.sum()) - downtime - fault_kwh - actual
    steps = [
        ("Sunlight potential (nameplate)", float(potential.sum())),
        ("Heat", float((potential - after_temp).sum())),
        ("Panel ageing", float((after_temp - after_degradation).sum())),
        ("Inverter conversion", float((after_degradation - expected).sum())),
        ("Downtime", downtime),
        ("Faults (detected)", fault_kwh),
        ("Other (soiling, shading, mismatch)", other),
        ("Delivered", actual),
    ]
    return [{"name": name, "kwh": round(kwh, 2)} for name, kwh in steps]


def health(db: UserSupabase, plant_id: str) -> dict:
    p = load_plant(db, plant_id)
    window = _window(p)
    alerts, fault_kwh = _alerts(db, p)
    return {
        "timezone": p.tz,
        "availability": _availability(window, [inv["label"] for inv in p.inverters]),
        "alerts": alerts,
        "losses": _losses(p, window, fault_kwh) if not window.empty else [],
        "days": PAGE_DAYS,
    }


# ---------------------------------------------------------------- Finance

def finance(db: UserSupabase, plant_id: str) -> dict:
    p = load_plant(db, plant_id)
    d = daily(p)
    complete = d[d["date"] < p.today].tail(PAGE_DAYS) if len(d) else d
    try:
        annual = typical_year(p)
    except requests.RequestException:
        annual = None
    cost = p.row.get("system_cost")
    payback = None
    if cost and annual and annual["revenue"] > 0:
        payback = round(float(cost) / annual["revenue"], 1)
    return {
        "tariff_per_kwh": p.tariff,
        "monthly": _monthly(db, p),
        "lifetime": _lifetime(db, p),
        "avg_daily_revenue": round(float(complete["revenue"].mean()), 2) if len(complete) else None,
        "avg_daily_energy_kwh": round(float(complete["energy_kwh"].mean()), 2) if len(complete) else None,
        "annual": annual,
        "calibration": round(p.calibration, 3),
        "system_cost": cost,
        "payback_years": payback,
    }
