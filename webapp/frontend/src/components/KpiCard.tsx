type Tone = "neutral" | "good" | "warn" | "bad";

interface KpiCardProps {
  label: string;
  value: string;
  subvalue?: string;
  tone?: Tone;
}

const toneClasses: Record<Tone, string> = {
  neutral: "text-gray-900",
  good: "text-green-600",
  warn: "text-amber-600",
  bad: "text-red-600",
};

export function KpiCard({ label, value, subvalue, tone = "neutral" }: KpiCardProps) {
  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm">
      <div className="text-sm text-gray-500">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${toneClasses[tone]}`}>{value}</div>
      {subvalue && <div className="text-xs text-gray-400 mt-1">{subvalue}</div>}
    </div>
  );
}
