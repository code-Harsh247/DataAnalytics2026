"use client";

import { useEffect, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { usePlant } from "@/context/PlantContext";
import { useLive } from "@/context/LiveContext";
import { getProduction } from "@/lib/pages";
import { usePageData } from "@/lib/usePageData";
import { dayLabel, kwh, money, monthLabel, pct } from "@/lib/format";
import { getGenerationHistory, getWeatherHistory, type GenerationPoint, type WeatherPoint } from "@/lib/plantDashboard";
import { CHART_COLORS, LoadState, PageBody, Panel, Stat } from "@/components/ui";
import { GenerationHistoryChart, type AggregatedGenerationPoint } from "@/components/GenerationHistoryChart";
import { WeatherHistoryChart } from "@/components/WeatherHistoryChart";

function aggregate(points: GenerationPoint[]): AggregatedGenerationPoint[] {
  const totals = new Map<string, number>();
  for (const p of points) totals.set(p.recorded_at, (totals.get(p.recorded_at) ?? 0) + p.ac_power_kw);
  return Array.from(totals.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([recorded_at, total_ac_power_kw]) => ({ recorded_at, total_ac_power_kw }));
}

export default function ProductionPage() {
  const { data, error, refreshing } = usePageData(getProduction);
  const { plant } = usePlant();
  const { version } = useLive();
  const [history, setHistory] = useState<{ weather: WeatherPoint[]; output: AggregatedGenerationPoint[] } | null>(null);

  useEffect(() => {
    if (!plant) return;
    let cancelled = false;
    Promise.all([getWeatherHistory(plant.id), getGenerationHistory(plant.id)])
      .then(([weather, generation]) => {
        if (!cancelled) setHistory({ weather, output: aggregate(generation) });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [plant, version]);

  if (!data) {
    return (
      <PageBody>
        <LoadState error={error} loading={refreshing || !error} />
      </PageBody>
    );
  }

  const chartDays = data.days.map((d) => ({ ...d, label: dayLabel(d.date), prPct: d.pr != null ? d.pr * 100 : null }));
  const maxInverter = Math.max(...data.inverters.map((i) => i.energy_kwh), 1);

  return (
    <PageBody>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Last 30 days" value={kwh(data.totals.energy_kwh, 0)} sub={`earned ${money(data.totals.revenue)}`} />
        <Stat label="Specific yield" value={data.totals.specific_yield.toFixed(1)} sub={`kWh per kWp · ${data.capacity_kw} kWp installed`} />
        <Stat label="Performance ratio" value={pct(data.totals.pr)} sub="30-day, healthy ≈ 75–85%" />
        <Stat
          label="Best day"
          value={data.best_day ? kwh(data.best_day.energy_kwh) : "—"}
          sub={
            data.best_day && data.worst_day
              ? `${dayLabel(data.best_day.date)} · worst ${kwh(data.worst_day.energy_kwh)} on ${dayLabel(data.worst_day.date)}`
              : undefined
          }
        />
      </div>

      <Panel title="Daily energy" subtitle="Bars: energy per day (today so far is lighter). Line: performance ratio.">
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={chartDays} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={20} />
            <YAxis yAxisId="kwh" tick={{ fontSize: 11 }} label={{ value: "kWh", angle: -90, position: "insideLeft", fontSize: 11 }} />
            <YAxis yAxisId="pr" orientation="right" domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
            <Tooltip
              formatter={(v, name) =>
                name === "Performance ratio" ? `${Number(v).toFixed(0)}%` : `${Number(v).toFixed(1)} kWh`
              }
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar
              yAxisId="kwh"
              dataKey="energy_kwh"
              name="Energy"
              fill={CHART_COLORS.actual}
              isAnimationActive={false}
              shape={(props: unknown) => {
                const { x, y, width, height, payload } = props as {
                  x: number; y: number; width: number; height: number; payload: { partial: boolean };
                };
                return <rect x={x} y={y} width={width} height={height} fill={CHART_COLORS.actual} opacity={payload.partial ? 0.35 : 1} />;
              }}
            />
            <Line yAxisId="pr" dataKey="prPct" name="Performance ratio" stroke={CHART_COLORS.sun} strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </Panel>

      <div className="grid lg:grid-cols-2 gap-5">
        <Panel title="Inverters" subtitle="Last 30 days. Similar inverters should land close together.">
          <table className="w-full text-sm">
            <thead className="text-left text-gray-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="py-1.5 font-medium">Inverter</th>
                <th className="py-1.5 font-medium">Energy</th>
                <th className="py-1.5 font-medium">Share</th>
                <th className="py-1.5 font-medium">PR</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.inverters.map((inv) => (
                <tr key={inv.label}>
                  <td className="py-2 font-mono text-xs text-gray-700">{inv.label}</td>
                  <td className="py-2 text-gray-700">
                    <div className="flex items-center gap-2">
                      <div className="h-2 rounded bg-blue-500" style={{ width: `${(inv.energy_kwh / maxInverter) * 120}px` }} />
                      {kwh(inv.energy_kwh, 0)}
                    </div>
                  </td>
                  <td className="py-2 text-gray-600">{pct(inv.share, 1)}</td>
                  <td className="py-2 text-gray-600">{pct(inv.pr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="By month" subtitle="Whole history, in the plant's time zone.">
          {data.monthly.length === 0 ? (
            <p className="text-sm text-gray-500">
              Monthly totals need <code>webapp/supabase/006_finance.sql</code> to be run in Supabase.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-gray-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="py-1.5 font-medium">Month</th>
                  <th className="py-1.5 font-medium">Energy</th>
                  <th className="py-1.5 font-medium">Earned</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {[...data.monthly].reverse().map((m) => (
                  <tr key={m.month}>
                    <td className="py-2 text-gray-700">{monthLabel(m.month)}</td>
                    <td className="py-2 text-gray-700">{kwh(m.energy_kwh, 0)}</td>
                    <td className="py-2 text-gray-600">{money(m.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      {history && (
        <>
          <GenerationHistoryChart data={history.output} />
          <WeatherHistoryChart data={history.weather} />
        </>
      )}
    </PageBody>
  );
}
