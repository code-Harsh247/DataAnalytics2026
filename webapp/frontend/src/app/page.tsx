"use client";

import { useEffect, useState } from "react";
import { useSimulation } from "@/context/SimulationContext";
import { api, type Overview } from "@/lib/api";
import { KpiCard } from "@/components/KpiCard";
import { DailyTrendChart } from "@/components/DailyTrendChart";

function healthTone(score: number | null): "good" | "warn" | "bad" | "neutral" {
  if (score === null) return "neutral";
  if (score >= 90) return "good";
  if (score >= 70) return "warn";
  return "bad";
}

export default function Home() {
  const { plantId, currentDate } = useSimulation();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!currentDate) return;
    setLoading(true);
    setError(null);
    api
      .getOverview(plantId, currentDate)
      .then((o) => {
        setOverview(o);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, [plantId, currentDate]);

  if (error) {
    return <p className="p-6 text-red-600">Error loading overview: {error}</p>;
  }
  if (loading || !overview) {
    return <p className="p-6 text-gray-500">Loading…</p>;
  }

  const generationDelta =
    overview.today_actual_kwh !== null && overview.today_expected_kwh !== null
      ? overview.today_actual_kwh - overview.today_expected_kwh
      : null;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Command Center</h1>
        <p className="text-sm text-gray-500">Plant 2 — as of {overview.as_of}</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <KpiCard
          label="Health score"
          value={overview.health_score !== null ? `${overview.health_score}%` : "—"}
          tone={healthTone(overview.health_score)}
        />
        <KpiCard
          label="Today's generation"
          value={
            overview.today_actual_kwh !== null ? `${overview.today_actual_kwh.toFixed(1)} kWh` : "—"
          }
          subvalue={
            generationDelta !== null
              ? `${generationDelta >= 0 ? "+" : ""}${generationDelta.toFixed(1)} kWh vs expected`
              : undefined
          }
          tone={generationDelta !== null ? (generationDelta >= 0 ? "good" : "warn") : "neutral"}
        />
        <KpiCard
          label="Active risk"
          value={`${overview.active_risk_count}`}
          subvalue={`${overview.watch_count} on watch, ${overview.healthy_count} healthy`}
          tone={overview.active_risk_count > 0 ? "bad" : "good"}
        />
        <KpiCard
          label="Tomorrow's forecast"
          value={
            overview.forecast_tomorrow_kwh !== null
              ? `${overview.forecast_tomorrow_kwh.toFixed(1)} kWh`
              : "No data yet"
          }
        />
        <KpiCard
          label="Revenue at risk"
          value={`${overview.total_revenue_lost.toFixed(0)}`}
          subvalue="illustrative tariff — see docs"
          tone={overview.total_revenue_lost > 0 ? "bad" : "good"}
        />
      </div>

      <DailyTrendChart data={overview.daily_trend} />
    </div>
  );
}
