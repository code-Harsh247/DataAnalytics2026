"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Plant } from "@/lib/plants";
import { supabase } from "@/lib/supabase";
import {
  getGenerationHistory,
  getInverterLatest,
  getPlantTotals,
  getWeatherHistory,
  readingEnergyKwh,
  type GenerationPoint,
  type InverterLatest,
  type PlantTotals,
  type WeatherPoint,
} from "@/lib/plantDashboard";
import { getGateway, type Gateway } from "@/lib/gateway";
import { getPlantStatus, type InverterState, type PlantStatus } from "@/lib/status";
import { KpiCard } from "@/components/KpiCard";
import { WeatherHistoryChart } from "@/components/WeatherHistoryChart";
import { GenerationHistoryChart, type AggregatedGenerationPoint } from "@/components/GenerationHistoryChart";
import { AnalysisPanel } from "@/components/AnalysisPanel";
import { ConnectDevice } from "@/components/ConnectDevice";
import { DeviceBadge } from "@/components/DeviceBadge";
import { VerdictBanner } from "@/components/VerdictBanner";

const STATUS_REFRESH_MS = 60_000; // also catches a gateway going quiet
const STATUS_MIN_GAP_MS = 10_000; // new readings refresh the verdict at most this often
const WEATHER_MIN_GAP_MS = 60_000;
const FLUSH_MS = 1000; // batch realtime inserts (a catch-up can send thousands)
const RECENTLY_SEEN_MS = 120_000;

function aggregateByTimestamp(points: GenerationPoint[]): AggregatedGenerationPoint[] {
  const totals = new Map<string, number>();
  for (const p of points) {
    totals.set(p.recorded_at, (totals.get(p.recorded_at) ?? 0) + p.ac_power_kw);
  }
  return Array.from(totals.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([recorded_at, total_ac_power_kw]) => ({ recorded_at, total_ac_power_kw: Math.round(total_ac_power_kw * 1000) / 1000 }));
}

// Realtime sends timestamps as "2026-10-12 03:12:30+00"; REST sends ISO. Normalise
// so live rows sort and group with the fetched ones.
function toIso(ts: string): string {
  return new Date(ts).toISOString().replace(".000Z", "+00:00");
}

const STATE_BADGES: Record<InverterState, { text: string; className: string }> = {
  ok: { text: "OK", className: "bg-green-100 text-green-700" },
  underperforming: { text: "Under-producing", className: "bg-red-100 text-red-700" },
  offline: { text: "Not reporting", className: "bg-gray-200 text-gray-600" },
  learning: { text: "Learning", className: "bg-blue-100 text-blue-700" },
  no_data: { text: "No data", className: "bg-gray-100 text-gray-500" },
};

interface DashboardData {
  weather: WeatherPoint[];
  generation: GenerationPoint[];
  inverters: InverterLatest[];
  totals: PlantTotals;
  gateway: Gateway | null;
}

export function PlantDashboardView({ plant }: { plant: Plant }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<PlantStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [replacingGateway, setReplacingGateway] = useState(false);

  const lastStatusAt = useRef(0);
  const lastWeatherAt = useRef(0);
  const pending = useRef<GenerationPoint[]>([]);

  // ---------------------------------------------------------------- loading

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getWeatherHistory(plant.id),
      getGenerationHistory(plant.id),
      getInverterLatest(plant.id),
      getPlantTotals(plant.id),
      getGateway(plant.id),
    ])
      .then(([weather, generation, inverters, totals, gateway]) => {
        if (cancelled) return;
        setData({ weather, generation, inverters, totals, gateway });
        setError(null);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [plant.id, reloadKey]);

  const refreshStatus = useCallback(async () => {
    lastStatusAt.current = Date.now();
    try {
      const s = await getPlantStatus(plant.id);
      setStatus(s);
      setStatusError(null);
    } catch (e) {
      setStatusError(e instanceof Error ? e.message : "status unavailable");
    }
  }, [plant.id]);

  useEffect(() => {
    const first = setTimeout(refreshStatus, 0);
    const timer = setInterval(() => {
      setNow(Date.now());
      refreshStatus();
    }, STATUS_REFRESH_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [refreshStatus, reloadKey]);

  // ---------------------------------------------------------------- realtime

  const inverterKey = (data?.inverters ?? []).map((i) => i.id).join(",");

  useEffect(() => {
    if (!inverterKey) return;
    const channel = supabase
      .channel(`plant-${plant.id}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "generation_readings", filter: `inverter_id=in.(${inverterKey})` },
        (payload) => {
          const r = payload.new as GenerationPoint;
          pending.current.push({
            recorded_at: toIso(r.recorded_at),
            inverter_id: r.inverter_id,
            ac_power_kw: r.ac_power_kw,
            dc_power_kw: r.dc_power_kw,
            energy_kwh: r.energy_kwh,
            revenue_per_interval: r.revenue_per_interval,
          });
        },
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "gateways", filter: `plant_id=eq.${plant.id}` },
        (payload) => {
          const g = payload.new as Gateway;
          setNow(Date.now());
          setData((prev) =>
            prev ? { ...prev, gateway: { serial: g.serial, paired_at: g.paired_at, last_seen_at: g.last_seen_at } } : prev,
          );
        },
      )
      .subscribe();

    const flush = setInterval(() => {
      if (pending.current.length === 0) return;
      const rows = pending.current.splice(0);
      setNow(Date.now());
      setData((prev) => {
        if (!prev) return prev;
        const latest = new Map(prev.inverters.map((i) => [i.id, i]));
        for (const r of rows) {
          const cur = latest.get(r.inverter_id);
          if (cur && (!cur.latest_recorded_at || r.recorded_at >= cur.latest_recorded_at)) {
            latest.set(r.inverter_id, { ...cur, latest_ac_power_kw: r.ac_power_kw, latest_recorded_at: r.recorded_at });
          }
        }
        return {
          ...prev,
          generation: [...prev.generation, ...rows],
          inverters: prev.inverters.map((i) => latest.get(i.id) ?? i),
          totals: {
            total_energy_kwh: prev.totals.total_energy_kwh + rows.reduce((s, r) => s + readingEnergyKwh(r), 0),
            total_revenue: prev.totals.total_revenue + rows.reduce((s, r) => s + (r.revenue_per_interval ?? 0), 0),
            reading_count: prev.totals.reading_count + rows.length,
          },
        };
      });
      if (Date.now() - lastStatusAt.current > STATUS_MIN_GAP_MS) refreshStatus();
      if (Date.now() - lastWeatherAt.current > WEATHER_MIN_GAP_MS) {
        lastWeatherAt.current = Date.now();
        getWeatherHistory(plant.id)
          .then((weather) => setData((prev) => (prev ? { ...prev, weather } : prev)))
          .catch(() => {});
      }
    }, FLUSH_MS);

    return () => {
      clearInterval(flush);
      supabase.removeChannel(channel);
    };
  }, [plant.id, inverterKey, refreshStatus]);

  const onPaired = useCallback(() => {
    setReplacingGateway(false);
    setReloadKey((k) => k + 1);
  }, []);

  // ---------------------------------------------------------------- render

  if (error) {
    return <p className="p-6 text-red-600">Error loading plant data: {error}</p>;
  }
  if (!data) {
    return <p className="p-6 text-gray-500">Loading your plant&apos;s data…</p>;
  }

  const { weather, generation, inverters, totals, gateway } = data;
  const verdicts = new Map((status?.inverters ?? []).map((v) => [v.label, v]));
  const needsAttention = (status?.inverters ?? []).filter((v) => v.state === "underperforming").length;
  const latestWeather = weather[weather.length - 1] ?? null;
  const seenRecently = gateway?.last_seen_at != null && now - new Date(gateway.last_seen_at).getTime() < RECENTLY_SEEN_MS;
  const connected = Boolean(status?.gateway?.connected) || seenRecently;

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">{plant.name}</h1>
          <p className="text-sm text-gray-500">
            {plant.latitude.toFixed(2)}, {plant.longitude.toFixed(2)} · tariff {plant.tariff_per_kwh}/kWh
          </p>
        </div>
        {gateway?.paired_at && (
          <div className="flex flex-col items-end gap-1">
            <DeviceBadge gateway={gateway} connected={connected} />
            <button
              type="button"
              onClick={() => setReplacingGateway((v) => !v)}
              className="text-xs text-blue-600 hover:underline"
            >
              {replacingGateway ? "Cancel" : "Replace gateway"}
            </button>
          </div>
        )}
      </div>

      {(!gateway?.paired_at || replacingGateway) && <ConnectDevice plantId={plant.id} onPaired={onPaired} />}

      <VerdictBanner status={status} error={statusError} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Energy to date" value={`${totals.total_energy_kwh.toFixed(2)} kWh`} />
        <KpiCard label="Revenue to date" value={totals.total_revenue.toFixed(2)} subvalue="illustrative tariff" />
        <KpiCard
          label="Needs attention"
          value={status ? `${needsAttention} / ${inverters.length}` : "—"}
          subvalue="inverters under-producing"
          tone={needsAttention > 0 ? "bad" : "good"}
        />
        <KpiCard
          label="Latest conditions"
          value={latestWeather ? `${latestWeather.temperature_c?.toFixed(1)}°C` : "—"}
          subvalue={latestWeather ? `${latestWeather.ghi_wm2?.toFixed(0)} W/m² GHI` : undefined}
        />
      </div>

      <WeatherHistoryChart data={weather} />
      <GenerationHistoryChart data={aggregateByTimestamp(generation)} />

      <div className="bg-white rounded-lg border shadow-sm overflow-x-auto">
        <table className="w-full text-sm min-w-[560px]">
          <thead className="bg-gray-50 text-left text-gray-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-2 font-medium">Inverter</th>
              <th className="px-4 py-2 font-medium">Health</th>
              <th className="px-4 py-2 font-medium">Vs expected</th>
              <th className="px-4 py-2 font-medium">Latest output</th>
              <th className="px-4 py-2 font-medium">As of</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {inverters.map((inv) => {
              const verdict = verdicts.get(inv.label);
              const badge = verdict ? STATE_BADGES[verdict.state] : null;
              const shortfall = verdict?.shortfall_pct;
              return (
                <tr key={inv.id}>
                  <td className="px-4 py-2 font-mono text-xs text-gray-700">{inv.label}</td>
                  <td className="px-4 py-2">
                    {badge ? (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badge.className}`}>{badge.text}</span>
                    ) : (
                      <span className="text-xs text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-gray-600">
                    {shortfall == null
                      ? "—"
                      : shortfall > 0
                        ? `${shortfall.toFixed(1)}% below`
                        : `${Math.abs(shortfall).toFixed(1)}% above`}
                  </td>
                  <td className="px-4 py-2 text-gray-600">
                    {inv.latest_ac_power_kw !== null ? `${inv.latest_ac_power_kw.toFixed(3)} kW` : "—"}
                  </td>
                  <td className="px-4 py-2 text-gray-400 text-xs">
                    {inv.latest_recorded_at ? new Date(inv.latest_recorded_at).toISOString().slice(11, 19) + " UTC" : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <AnalysisPanel plant={plant} />
    </div>
  );
}
