"use client";

import { useEffect, useState } from "react";
import { useSimulation } from "@/context/SimulationContext";
import { api, type Forecast } from "@/lib/api";
import { KpiCard } from "@/components/KpiCard";
import { ForecastChart } from "@/components/ForecastChart";

function addDays(dateStr: string, days: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const ms = Date.UTC(y, m - 1, d) + days * 24 * 60 * 60 * 1000;
  return new Date(ms).toISOString().slice(0, 10);
}

export default function ForecastPage() {
  const { plantId, currentDate } = useSimulation();
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentDate) return;
    setError(null);
    api
      .getForecast(plantId, currentDate)
      .then(setForecast)
      .catch((e: Error) => setError(e.message));
  }, [plantId, currentDate]);

  if (error) return <p className="p-6 text-red-600">Error loading forecast: {error}</p>;
  if (!forecast) return <p className="p-6 text-gray-500">Loading…</p>;

  const tomorrow = currentDate ? addDays(currentDate, 1) : null;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Forecast</h1>
        <p className="text-sm text-gray-500">Plant 2 — day-ahead yield prediction</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <KpiCard
          label="Tomorrow's forecast"
          value={
            forecast.forecast_tomorrow_kwh !== null
              ? `${forecast.forecast_tomorrow_kwh.toFixed(1)} kWh`
              : "No data yet"
          }
          subvalue={
            forecast.forecast_range
              ? `range ${forecast.forecast_range.low}–${forecast.forecast_range.high} kWh`
              : undefined
          }
        />
        <KpiCard
          label="Next 30 days revenue projection"
          value={
            forecast.monthly_revenue_projection !== null
              ? `${forecast.monthly_revenue_projection.toFixed(0)}`
              : "—"
          }
          subvalue="based on last 7 days' actual average, illustrative tariff"
        />
      </div>

      <ForecastChart
        history={forecast.history}
        forecastDate={tomorrow}
        forecastKwh={forecast.forecast_tomorrow_kwh}
      />

      <p className="text-xs text-gray-400">
        Forecast uses only information available in advance (lagged actual output, calendar position, and
        a synthetic day-ahead irradiance estimate) — never same-day measured weather. Persistence and
        climatology are baselines the model is expected to beat, not just match.
      </p>
    </div>
  );
}
