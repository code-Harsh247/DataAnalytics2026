"use client";

import { useEffect, useState } from "react";
import type { Plant } from "@/lib/plants";
import {
  getGenerationHistory,
  getInverterStatuses,
  getPlantTotals,
  getWeatherHistory,
  type GenerationPoint,
  type InverterStatus,
  type PlantTotals,
  type WeatherPoint,
} from "@/lib/plantDashboard";
import { KpiCard } from "@/components/KpiCard";
import { WeatherHistoryChart } from "@/components/WeatherHistoryChart";
import { GenerationHistoryChart, type AggregatedGenerationPoint } from "@/components/GenerationHistoryChart";
import { AnalysisPanel } from "@/components/AnalysisPanel";

function aggregateByTimestamp(points: GenerationPoint[]): AggregatedGenerationPoint[] {
  const totals = new Map<string, number>();
  for (const p of points) {
    totals.set(p.recorded_at, (totals.get(p.recorded_at) ?? 0) + p.ac_power_kw);
  }
  return Array.from(totals.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([recorded_at, total_ac_power_kw]) => ({ recorded_at, total_ac_power_kw: Math.round(total_ac_power_kw * 1000) / 1000 }));
}

export function PlantDashboardView({ plant }: { plant: Plant }) {
  const [weather, setWeather] = useState<WeatherPoint[] | null>(null);
  const [generation, setGeneration] = useState<GenerationPoint[] | null>(null);
  const [inverters, setInverters] = useState<InverterStatus[] | null>(null);
  const [totals, setTotals] = useState<PlantTotals | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);

    Promise.all([
      getWeatherHistory(plant.id),
      getGenerationHistory(plant.id),
      getInverterStatuses(plant.id),
      getPlantTotals(plant.id),
    ])
      .then(([w, g, i, t]) => {
        if (cancelled) return;
        setWeather(w);
        setGeneration(g);
        setInverters(i);
        setTotals(t);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });

    return () => {
      cancelled = true;
    };
  }, [plant.id]);

  if (error) {
    return <p className="p-6 text-red-600">Error loading plant data: {error}</p>;
  }
  if (!weather || !generation || !inverters || !totals) {
    return <p className="p-6 text-gray-500">Loading your plant&apos;s data…</p>;
  }

  const activeFaultCount = inverters.filter((i) => i.latest_fault_active).length;
  const latestWeather = weather[weather.length - 1] ?? null;
  const aggregatedGeneration = aggregateByTimestamp(generation);

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">{plant.name}</h1>
        <p className="text-sm text-gray-500">
          {plant.latitude.toFixed(2)}, {plant.longitude.toFixed(2)} · tariff {plant.tariff_per_kwh}/kWh
        </p>
      </div>

      {totals.reading_count < 5 && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          Only {totals.reading_count} reading{totals.reading_count === 1 ? "" : "s"} collected so far
          (ingestion runs every 15 minutes while this app is open) — charts below will fill in as more
          data arrives.
        </p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Energy to date" value={`${totals.total_energy_kwh.toFixed(2)} kWh`} />
        <KpiCard
          label="Revenue to date"
          value={totals.total_revenue.toFixed(2)}
          subvalue="illustrative tariff"
        />
        <KpiCard
          label="Active faults"
          value={`${activeFaultCount} / ${inverters.length}`}
          tone={activeFaultCount > 0 ? "bad" : "good"}
        />
        <KpiCard
          label="Latest conditions"
          value={latestWeather ? `${latestWeather.temperature_c?.toFixed(1)}°C` : "—"}
          subvalue={latestWeather ? `${latestWeather.ghi_wm2?.toFixed(0)} W/m² GHI` : undefined}
        />
      </div>

      <WeatherHistoryChart data={weather} />
      <GenerationHistoryChart data={aggregatedGeneration} />

      <div className="bg-white rounded-lg border shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-gray-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-2 font-medium">Inverter</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Latest output</th>
              <th className="px-4 py-2 font-medium">As of</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {inverters.map((inv) => (
              <tr key={inv.id}>
                <td className="px-4 py-2 font-mono text-xs text-gray-700">{inv.label}</td>
                <td className="px-4 py-2">
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      inv.latest_fault_active ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"
                    }`}
                  >
                    {inv.latest_fault_active ? "Fault active" : "Healthy"}
                  </span>
                </td>
                <td className="px-4 py-2 text-gray-600">
                  {inv.latest_ac_power_kw !== null ? `${inv.latest_ac_power_kw.toFixed(3)} kW` : "—"}
                </td>
                <td className="px-4 py-2 text-gray-400 text-xs">
                  {inv.latest_recorded_at ? new Date(inv.latest_recorded_at).toISOString().slice(11, 16) + " UTC" : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <AnalysisPanel plant={plant} />
    </div>
  );
}
