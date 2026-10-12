// Small layout pieces shared by the plant pages.

export function PageBody({ children }: { children: React.ReactNode }) {
  return <div className="max-w-6xl w-full mx-auto px-6 py-5 space-y-5">{children}</div>;
}

export function Panel({
  title,
  subtitle,
  right,
  children,
}: {
  title?: string;
  subtitle?: React.ReactNode;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-white rounded-lg border shadow-sm p-4">
      {(title || right) && (
        <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
          <div>
            {title && <h2 className="text-sm font-medium text-gray-800">{title}</h2>}
            {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  const color = { neutral: "text-gray-900", good: "text-green-600", warn: "text-amber-600", bad: "text-red-600" }[tone];
  return (
    <div className="bg-white rounded-lg border shadow-sm p-4">
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${color}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

export function LoadState({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) return <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{error}</p>;
  if (loading) return <p className="text-sm text-gray-500">Loading…</p>;
  return null;
}

export const CHART_COLORS = {
  actual: "#2563eb",
  forecast: "#9ca3af",
  revenue: "#16a34a",
  sun: "#f59e0b",
  bad: "#dc2626",
};
