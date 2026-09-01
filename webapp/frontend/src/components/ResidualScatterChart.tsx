"use client";

import {
  CartesianGrid,
  ReferenceLine,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ResponsiveContainer,
} from "recharts";
import type { ResidualPoint } from "@/lib/api";

export function ResidualScatterChart({ points }: { points: ResidualPoint[] }) {
  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-700 mb-2">Residual vs irradiance</div>
      <ResponsiveContainer width="100%" height={280}>
        <ScatterChart margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis type="number" dataKey="irradiation" name="Irradiation" tick={{ fontSize: 11 }} />
          <YAxis type="number" dataKey="residual" name="Residual" tick={{ fontSize: 11 }} />
          <ReferenceLine y={0} stroke="#9ca3af" />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} />
          <Scatter data={points} fill="#2563eb" fillOpacity={0.35} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
