import type { InverterStatus, Trend } from "@/lib/api";

const statusStyles: Record<InverterStatus, string> = {
  healthy: "bg-green-100 text-green-700",
  watch: "bg-amber-100 text-amber-700",
  at_risk: "bg-red-100 text-red-700",
};

const statusLabels: Record<InverterStatus, string> = {
  healthy: "Healthy",
  watch: "Watch",
  at_risk: "At risk",
};

export function StatusBadge({ status }: { status: InverterStatus }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusStyles[status]}`}>
      {statusLabels[status]}
    </span>
  );
}

const trendLabels: Record<Trend, string> = {
  worsening: "↓ Worsening",
  stable: "→ Stable",
  improving: "↑ Improving",
  insufficient_data: "—",
};

const trendStyles: Record<Trend, string> = {
  worsening: "text-red-600",
  stable: "text-gray-500",
  improving: "text-green-600",
  insufficient_data: "text-gray-400",
};

export function TrendBadge({ trend }: { trend: Trend }) {
  return <span className={`text-xs font-medium ${trendStyles[trend]}`}>{trendLabels[trend]}</span>;
}
