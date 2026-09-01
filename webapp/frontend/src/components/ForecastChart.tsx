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
import type { ForecastHistoryPoint } from "@/lib/api";

interface ChartPoint {
  date: string;
  actual_kwh?: number | null;
  persistence_kwh?: number | null;
  climatology_kwh?: number | null;
  forecast_kwh?: number | null;
}

interface ForecastChartProps {
  history: ForecastHistoryPoint[];
  forecastDate: string | null;
  forecastKwh: number | null;
}

export function ForecastChart({ history, forecastDate, forecastKwh }: ForecastChartProps) {
  const data: ChartPoint[] = [...history];
  if (forecastDate && forecastKwh !== null) {
    data.push({ date: forecastDate, forecast_kwh: forecastKwh });
  }

  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-700 mb-2">Forecast vs actual vs baselines</div>
      <ResponsiveContainer width="100%" height={300}>
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
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="persistence_kwh"
            name="Persistence"
            stroke="#f59e0b"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="climatology_kwh"
            name="Climatology"
            stroke="#9ca3af"
            strokeWidth={1.5}
            strokeDasharray="2 2"
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="forecast_kwh"
            name="Tomorrow's forecast"
            stroke="#16a34a"
            strokeWidth={0}
            dot={{ r: 6, fill: "#16a34a" }}
            isAnimationActive={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
