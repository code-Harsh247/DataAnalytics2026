"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSimulation } from "@/context/SimulationContext";
import { api, type InverterSummary } from "@/lib/api";
import { StatusBadge, TrendBadge } from "@/components/StatusBadge";

export default function MaintenancePage() {
  const { plantId, currentDate } = useSimulation();
  const [inverters, setInverters] = useState<InverterSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentDate) return;
    setError(null);
    api
      .getInverters(plantId, currentDate)
      .then(setInverters)
      .catch((e: Error) => setError(e.message));
  }, [plantId, currentDate]);

  if (error) return <p className="p-6 text-red-600">Error loading inverters: {error}</p>;
  if (!inverters) return <p className="p-6 text-gray-500">Loading…</p>;

  const atRiskCount = inverters.filter((i) => i.status === "at_risk").length;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Maintenance Queue</h1>
        <p className="text-sm text-gray-500">
          {inverters.length} inverters, {atRiskCount} need attention — sorted by risk
        </p>
      </div>

      <div className="bg-white rounded-lg border shadow-sm overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead className="bg-gray-50 text-left text-gray-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-2 font-medium">Inverter</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Trend</th>
              <th className="px-4 py-2 font-medium">Output vs expected</th>
              <th className="px-4 py-2 font-medium">Est. revenue lost</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {inverters.map((inv) => (
              <tr key={inv.source_key} className="hover:bg-gray-50">
                <td className="px-4 py-2 font-mono text-xs text-gray-700">{inv.source_key}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={inv.status} />
                </td>
                <td className="px-4 py-2">
                  <TrendBadge trend={inv.trend} />
                </td>
                <td
                  className={`px-4 py-2 font-medium ${inv.mean_residual < 0 ? "text-red-600" : "text-green-600"}`}
                >
                  {inv.mean_residual >= 0 ? "+" : ""}
                  {inv.mean_residual.toFixed(1)} kW
                </td>
                <td className="px-4 py-2 text-gray-600">{inv.est_revenue_lost.toFixed(0)}</td>
                <td className="px-4 py-2 text-right">
                  <Link
                    href={`/maintenance/${inv.source_key}`}
                    className="text-blue-600 hover:underline text-xs font-medium"
                  >
                    View →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
