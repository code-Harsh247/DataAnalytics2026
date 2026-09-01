"""Combines Thread 1 (fault) and Thread 2 (forecast) into the Command
Center's single overview payload."""

import pandas as pd

from . import fault_model, forecast_model


def get_overview(plant: int, as_of: pd.Timestamp) -> dict:
    daily_trend = fault_model.daily_plant_trend(plant, as_of)
    inverters = fault_model.inverter_summary(plant, as_of)
    fc = forecast_model.forecast_series(plant, as_of)

    active_risk_count = sum(1 for i in inverters if i["status"] == "at_risk")
    watch_count = sum(1 for i in inverters if i["status"] == "watch")
    total_revenue_lost = round(sum(i["est_revenue_lost"] for i in inverters), 2)

    today = daily_trend.iloc[-1] if len(daily_trend) else None
    health_score = round(100 * (1 - active_risk_count / max(len(inverters), 1)), 1) if inverters else None

    return {
        "as_of": as_of.date().isoformat(),
        "daily_trend": daily_trend.to_dict("records"),
        "today_actual_kwh": float(today["actual_kwh"]) if today is not None else None,
        "today_expected_kwh": float(today["expected_kwh"]) if today is not None else None,
        "active_risk_count": active_risk_count,
        "watch_count": watch_count,
        "healthy_count": len(inverters) - active_risk_count - watch_count,
        "total_revenue_lost": total_revenue_lost,
        "forecast_tomorrow_kwh": fc.get("forecast_tomorrow_kwh"),
        "health_score": health_score,
    }
