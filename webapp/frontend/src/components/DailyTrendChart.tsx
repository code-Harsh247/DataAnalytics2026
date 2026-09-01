"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailyTrendPoint } from "@/lib/api";

export function DailyTrendChart({ data }: { data: DailyTrendPoint[] }) {
  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-700 mb-2">
        Daily generation: actual vs expected
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d: string) => d.slice(5)} />
          <YAxis
            tick={{ fontSize: 11 }}
            label={{ value: "kWh", angle: -90, position: "insideLeft", fontSize: 11 }}
          />
          <Tooltip />
          <Legend />
          <Line
            type="monotone"
            dataKey="actual_kwh"
            name="Actual"
            stroke="#2563eb"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="expected_kwh"
            name="Expected"
            stroke="#9ca3af"
            strokeWidth={2}
            strokeDasharray="4 4"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
