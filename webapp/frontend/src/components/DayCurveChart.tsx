"use client";

import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CurvePoint } from "@/lib/pages";
import { localTime } from "@/lib/format";
import { CHART_COLORS } from "@/components/ui";

// One day's plant output: actual so far (area) and the forecast (dashed),
// on a real time axis in the plant's time zone.
export function DayCurveChart({
  actual,
  forecast,
  tz,
  height = 260,
}: {
  actual: CurvePoint[];
  forecast: CurvePoint[];
  tz: string;
  height?: number;
}) {
  const a = actual.map((p) => ({ t: Date.parse(p.t), actual: p.kw }));
  const f = forecast.map((p) => ({ t: Date.parse(p.t), forecast: p.kw }));
  const all = [...a, ...f].map((p) => p.t);
  if (all.length === 0) return <p className="text-sm text-gray-500">No data for today yet.</p>;
  const fmt = (t: number) => localTime(new Date(t).toISOString(), tz);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={[Math.min(...all), Math.max(...all)]}
          tickFormatter={fmt}
          tick={{ fontSize: 11 }}
          minTickGap={40}
          allowDuplicatedCategory={false}
        />
        <YAxis tick={{ fontSize: 11 }} label={{ value: "kW", angle: -90, position: "insideLeft", fontSize: 11 }} />
        <Tooltip labelFormatter={(t) => fmt(Number(t))} formatter={(v) => `${Number(v).toFixed(2)} kW`} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area
          data={a}
          dataKey="actual"
          name="Actual"
          type="monotone"
          stroke={CHART_COLORS.actual}
          fill={CHART_COLORS.actual}
          fillOpacity={0.15}
          strokeWidth={2}
          isAnimationActive={false}
        />
        <Line
          data={f}
          dataKey="forecast"
          name="Forecast"
          type="monotone"
          stroke={CHART_COLORS.forecast}
          strokeDasharray="5 4"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
