"use client";

import { Bar, BarChart, CartesianGrid, ErrorBar, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getForecast } from "@/lib/pages";
import { usePageData } from "@/lib/usePageData";
import { dayLabel, kwh, money, pct } from "@/lib/format";
import { CHART_COLORS, LoadState, PageBody, Panel, Stat } from "@/components/ui";
import { DayCurveChart } from "@/components/DayCurveChart";

export default function ForecastPage() {
  const { data, error, refreshing } = usePageData(getForecast);

  if (!data) {
    return (
      <PageBody>
        <LoadState error={error} loading={refreshing || !error} />
      </PageBody>
    );
  }

  const today = data.days[0];
  const week = data.days.reduce((s, d) => s + d.energy_kwh, 0);
  const weekRevenue = data.days.reduce((s, d) => s + d.revenue, 0);
  const soFar = data.today.actual_kwh;
  const bars = data.days.map((d) => ({
    ...d,
    label: dayLabel(d.date),
    range: [d.energy_kwh - d.p10_kwh, d.p90_kwh - d.energy_kwh],
    cloud: d.cloud_cover != null ? `☁ ${d.cloud_cover.toFixed(0)}%` : "",
  }));

  return (
    <PageBody>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat
          label="Today"
          value={today ? kwh(today.energy_kwh) : "—"}
          sub={`expected · ${kwh(soFar)} so far`}
        />
        <Stat label="Next 7 days" value={kwh(week, 0)} sub={`≈ ${money(weekRevenue)} earned`} />
        <Stat
          label="This month (projected)"
          value={kwh(data.month_projection_kwh, 0)}
          sub={`≈ ${money(data.month_projection_revenue)} · actual so far + forecast`}
        />
        <Stat
          label="Forecast accuracy"
          value={data.accuracy.mape != null ? `±${data.accuracy.mape.toFixed(1)}%` : "—"}
          sub={
            data.accuracy.days.length
              ? `average day-ahead error, last ${data.accuracy.days.length} days`
              : "needs a few complete days of readings"
          }
          tone={data.accuracy.mape != null && data.accuracy.mape > 20 ? "warn" : "neutral"}
        />
      </div>

      <Panel
        title="Next 7 days"
        subtitle={`Expected energy per day. Whiskers: likely range (${pct(data.band.low)}–${pct(data.band.high)} of the forecast${
          data.band.from_accuracy ? ", from this plant's recent forecast errors" : ", default until there's history"
        }).`}
      >
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={bars} margin={{ top: 25, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} label={{ value: "kWh", angle: -90, position: "insideLeft", fontSize: 11 }} />
            <Tooltip
              formatter={(v, _n, item) => {
                const d = item.payload as (typeof bars)[number];
                return [`${Number(v).toFixed(1)} kWh (${d.p10_kwh.toFixed(0)}–${d.p90_kwh.toFixed(0)}) · ≈ ${money(d.revenue)}`, "Forecast"];
              }}
            />
            <Bar dataKey="energy_kwh" fill={CHART_COLORS.actual} isAnimationActive={false}>
              <ErrorBar dataKey="range" width={6} stroke="#1e3a8a" />
              <LabelList dataKey="cloud" position="top" offset={14} style={{ fontSize: 10, fill: "#6b7280" }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Today, hour by hour" subtitle={`Forecast vs what the plant has made so far (plant time, ${data.timezone}).`}>
        <DayCurveChart actual={data.today.actual} forecast={data.today.forecast} tz={data.timezone} />
      </Panel>

      <Panel
        title="How good is the forecast?"
        subtitle="Each day's forecast as it was issued the day before (not hindsight), against what the plant actually produced."
      >
        {data.accuracy.days.length === 0 ? (
          <p className="text-sm text-gray-500">Not enough complete days of readings yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-gray-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="py-1.5 font-medium">Day</th>
                <th className="py-1.5 font-medium">Forecast</th>
                <th className="py-1.5 font-medium">Actual</th>
                <th className="py-1.5 font-medium">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {[...data.accuracy.days].reverse().map((d) => (
                <tr key={d.date}>
                  <td className="py-2 text-gray-700">{dayLabel(d.date)}</td>
                  <td className="py-2 text-gray-600">{kwh(d.forecast_kwh)}</td>
                  <td className="py-2 text-gray-700">{kwh(d.actual_kwh)}</td>
                  <td className={`py-2 ${Math.abs(d.error_pct) > 15 ? "text-amber-700" : "text-gray-600"}`}>
                    {d.error_pct > 0 ? "+" : ""}
                    {d.error_pct.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <p className="text-xs text-gray-400">
        How it works: the weather forecast for the plant&apos;s location (Open-Meteo) goes through the same physics
        model as the rest of the app, then is scaled by how this plant has actually performed over the last 14 days
        (currently {pct(data.calibration)} of the physics model). That factor absorbs dirt, shading and wiring losses
        the physics doesn&apos;t know about.
      </p>
    </PageBody>
  );
}
