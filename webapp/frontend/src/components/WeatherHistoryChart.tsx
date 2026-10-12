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
import type { WeatherPoint } from "@/lib/plantDashboard";

function formatTime(ms: number): string {
  return new Date(ms).toISOString().slice(5, 16).replace("T", " "); // MM-DD HH:MM UTC
}

export function WeatherHistoryChart({ data }: { data: WeatherPoint[] }) {
  // Real time axis -- see GenerationHistoryChart.
  const chartData = data.map((d) => ({ ...d, t: Date.parse(d.recorded_at) }));

  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-700 mb-2">
        Real irradiance (GHI) over time — UTC
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
            label={{ value: "W/m²", angle: -90, position: "insideLeft", fontSize: 11 }}
          />
          <Tooltip labelFormatter={(t) => formatTime(Number(t))} />
          <Line
            type="monotone"
            dataKey="ghi_wm2"
            name="GHI"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={chartData.length <= 100 ? { r: 2 } : false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
