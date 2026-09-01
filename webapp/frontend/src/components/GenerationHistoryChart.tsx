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

function formatTime(iso: string): string {
  return new Date(iso).toISOString().slice(11, 16); // HH:MM UTC
}

export function GenerationHistoryChart({ data }: { data: AggregatedGenerationPoint[] }) {
  const chartData = data.map((d) => ({ ...d, label: formatTime(d.recorded_at) }));

  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-700 mb-2">
        Total plant output over time — UTC
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis
            tick={{ fontSize: 11 }}
            label={{ value: "kW", angle: -90, position: "insideLeft", fontSize: 11 }}
          />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="total_ac_power_kw"
            name="AC Power"
            stroke="#2563eb"
            strokeWidth={2}
            dot={{ r: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
