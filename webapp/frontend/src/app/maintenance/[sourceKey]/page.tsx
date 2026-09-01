"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useSimulation } from "@/context/SimulationContext";
import { api, type InverterDetail } from "@/lib/api";
import { getDiagnosis } from "@/lib/diagnosis";
import { StatusBadge, TrendBadge } from "@/components/StatusBadge";
import { ResidualScatterChart } from "@/components/ResidualScatterChart";
import { DailySeverityChart } from "@/components/DailySeverityChart";

export default function InverterDetailPage() {
  const params = useParams<{ sourceKey: string }>();
  const sourceKey = params.sourceKey;
  const { plantId, currentDate } = useSimulation();
  const [detail, setDetail] = useState<InverterDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentDate || !sourceKey) return;
    setError(null);
    api
      .getInverterDetail(plantId, sourceKey, currentDate)
      .then(setDetail)
      .catch((e: Error) => setError(e.message));
  }, [plantId, sourceKey, currentDate]);

  if (error) return <p className="p-6 text-red-600">Error loading inverter: {error}</p>;
  if (!detail) return <p className="p-6 text-gray-500">Loading…</p>;

  if (detail.status === null) {
    return (
      <div className="p-6 max-w-4xl mx-auto space-y-4">
        <Link href="/maintenance" className="text-sm text-blue-600 hover:underline">
          ← Back to Maintenance Queue
        </Link>
        <p className="text-gray-500">No data yet for this inverter at this point in the timeline.</p>
      </div>
    );
  }

  const diagnosis = getDiagnosis(detail.status, detail.trend, detail.projected_days_to_critical);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <Link href="/maintenance" className="text-sm text-blue-600 hover:underline">
          ← Back to Maintenance Queue
        </Link>
        <div className="flex items-center gap-3 mt-2">
          <h1 className="text-xl font-semibold text-gray-900 font-mono">{detail.source_key}</h1>
          <StatusBadge status={detail.status} />
          <TrendBadge trend={detail.trend} />
        </div>
      </div>

      <div className="bg-white rounded-lg border p-4 shadow-sm">
        <div className="text-sm font-medium text-gray-700 mb-1">Diagnosis</div>
        <p className="text-sm text-gray-600">{diagnosis}</p>
        {detail.p_value !== null && (
          <p className="text-xs text-gray-400 mt-2">
            Trend fit: slope {detail.slope_per_day}/day, p={detail.p_value}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Mean deviation" value={detail.mean_residual} />
        <StatCard label="Z-score" value={detail.z_score} />
        <StatCard label="Est. kWh lost" value={detail.est_kwh_lost} />
        <StatCard label="Est. revenue lost" value={detail.est_revenue_lost} />
      </div>

      <ResidualScatterChart points={detail.points} />
      <DailySeverityChart data={detail.daily_severity} />
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm">
      <div className="text-sm text-gray-500">{label}</div>
      <div className="text-lg font-semibold text-gray-900 mt-1">{value ?? "—"}</div>
    </div>
  );
}
