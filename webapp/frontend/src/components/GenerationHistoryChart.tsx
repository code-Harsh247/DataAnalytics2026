"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface AggregatedGenerationPoint {
  recorded_at: string;
  total_ac_power_kw: number;
}

function formatTime(ms: number): string {
  return new Date(ms).toISOString().slice(5, 16).replace("T", " "); // MM-DD HH:MM UTC
}

export function GenerationHistoryChart({ data }: { data: AggregatedGenerationPoint[] }) {
  // A real time axis: live readings can be 30 s apart and history 15 min
  // apart, so evenly spaced category labels would stretch the last few minutes.
  const chartData = data.map((d) => ({ ...d, t: Date.parse(d.recorded_at) }));

  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-700 mb-2">
        Total plant output over time — UTC
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={formatTime}
            tick={{ fontSize: 11 }}
            minTickGap={40}
          />
          <YAxis
            tick={{ fontSize: 11 }}
            label={{ value: "kW", angle: -90, position: "insideLeft", fontSize: 11 }}
          />
          <Tooltip labelFormatter={(t) => formatTime(Number(t))} />
          <Line
            type="monotone"
            dataKey="total_ac_power_kw"
            name="AC Power"
            stroke="#2563eb"
            strokeWidth={2}
            dot={chartData.length <= 100 ? { r: 2 } : false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
