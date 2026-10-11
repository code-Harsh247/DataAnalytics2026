"use client";

import { useRef, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Plant } from "@/lib/plants";
import { resolvePlantDefaults } from "@/lib/generation";
import {
  MIN_INVERTERS_FOR_ANALYSIS,
  runAnalysis,
  type AnalysisInverterStatus,
  type AnalysisResult,
} from "@/lib/analysis";

const MODEL_LABELS: Record<string, string> = {
  random_forest: "Random Forest",
  isolation_forest: "Isolation Forest",
  gradient_boosting: "Gradient Boosting",
  baseline_ratio: "Physics baseline",
};

function modelLabel(name: string): string {
  return MODEL_LABELS[name] ?? name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const STATUS_STYLES: Record<AnalysisInverterStatus, string> = {
  healthy: "bg-green-100 text-green-700",
  warning: "bg-amber-100 text-amber-700",
  critical: "bg-red-100 text-red-700",
};

function fmt(x: number | null, digits = 2): string {
  return x === null ? "—" : x.toFixed(digits);
}

function hourLabel(iso: string): string {
  return new Date(iso).toISOString().slice(5, 13).replace("T", " ") + ":00"; // MM-DD HH:00 UTC
}

function dayLabel(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

export function AnalysisPanel({ plant }: { plant: Plant }) {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTrueFaults, setShowTrueFaults] = useState(false);
  // Guards against an older, slower response overwriting a newer one when the
  // user switches models quickly.
  const requestId = useRef(0);

  const { inverterCount } = resolvePlantDefaults(plant);
  const tooFewInverters = inverterCount < MIN_INVERTERS_FOR_ANALYSIS;

  const run = async (model?: string) => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const r = await runAnalysis(plant, model);
      if (id === requestId.current) setResult(r);
    } catch (e) {
      if (id === requestId.current) setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  };

  const bestModel = result?.comparison[0]?.f1 != null ? result.comparison[0].model : null;
  const hasExpected = result?.series.some((p) => p.expected_kw !== null) ?? false;
  const chartData =
    result?.series.map((p) => ({
      label: hourLabel(p.timestamp),
      actual_kw: p.actual_kw,
      expected_kw: p.expected_kw,
      flagged_kw: p.flagged ? p.actual_kw : null,
      // Fault episodes run through the night too, but scoring is daylight-only;
      // rings on the zero line at night would just be noise.
      true_fault_kw: p.true_fault && (p.actual_kw ?? 0) > 0 ? p.actual_kw : null,
    })) ?? [];
  const inverters = result ? [...result.inverters].sort((a, b) => b.est_kwh_lost - a.est_kwh_lost) : [];

  return (
    <div className="bg-white rounded-lg border shadow-sm p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-gray-700">30-day fault analysis</div>
          <p className="text-xs text-gray-500 mt-1 max-w-xl">
            Rebuilds the last 30 days from real weather at this location, trains every anomaly
            model on the first three weeks, and scores them on the rest.
          </p>
        </div>
        <button
          type="button"
          onClick={() => run(result?.model)}
          disabled={loading || tooFewInverters}
          className="bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50 shrink-0"
        >
          {loading ? "Analyzing…" : result ? "Re-run analysis" : "Run 30-day analysis"}
        </button>
      </div>

      {tooFewInverters && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          Analysis needs at least {MIN_INVERTERS_FOR_ANALYSIS} inverters: it spots faults by comparing
          each inverter against the others. This plant is configured with {inverterCount}.
        </p>
      )}

      {loading && !result && (
        <p className="text-sm text-gray-500">
          Fetching weather and training models. This usually takes a few seconds.
        </p>
      )}

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{error}</p>
      )}

      {result && (
        <div className={`space-y-4 transition-opacity ${loading ? "opacity-50" : ""}`}>
          <p className="text-xs text-gray-500">
            Showing <span className="font-medium text-gray-700">{modelLabel(result.model)}</span> ·
            scored on {dayLabel(result.period.test_start)} – {dayLabel(result.period.end)} ·{" "}
            {result.period.test_fault_hours} faulted hours in that window
          </p>

          {result.period.test_fault_hours === 0 && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              No faults occurred in the scoring window, so precision, recall and F1 can&apos;t be
              measured for this run.
            </p>
          )}

          <div>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <div className="text-sm font-medium text-gray-700">Expected vs actual output (plant total)</div>
              <label className="flex items-center gap-2 text-xs text-gray-600">
                <input
                  type="checkbox"
                  checked={showTrueFaults}
                  onChange={(e) => setShowTrueFaults(e.target.checked)}
                />
                Show true faults
              </label>
            </div>
            {!hasExpected && (
              <p className="text-xs text-gray-500 mb-2">
                {modelLabel(result.model)} has no power model, so there&apos;s no expected line. It
                flags unusual readings directly.
              </p>
            )}
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={40} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  label={{ value: "kW", angle: -90, position: "insideLeft", fontSize: 11 }}
                />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line
                  type="monotone"
                  dataKey="actual_kw"
                  name="Actual"
                  stroke="#2563eb"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
                {hasExpected && (
                  <Line
                    type="monotone"
                    dataKey="expected_kw"
                    name="Expected"
                    stroke="#9ca3af"
                    strokeWidth={1.5}
                    strokeDasharray="4 3"
                    dot={false}
                    isAnimationActive={false}
                  />
                )}
                <Line
                  dataKey="flagged_kw"
                  name="Flagged"
                  stroke="none"
                  dot={{ r: 3, fill: "#dc2626", stroke: "#dc2626" }}
                  activeDot={false}
                  isAnimationActive={false}
                />
                {showTrueFaults && (
                  <Line
                    dataKey="true_fault_kw"
                    name="True fault"
                    stroke="none"
                    dot={{ r: 6, fill: "none", stroke: "#f59e0b", strokeWidth: 1.5 }}
                    activeDot={false}
                    isAnimationActive={false}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[560px]">
              <thead className="bg-gray-50 text-left text-gray-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-2 font-medium">Inverter</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Flagged hours</th>
                  <th className="px-4 py-2 font-medium">True fault hours</th>
                  <th className="px-4 py-2 font-medium">Est. energy lost</th>
                  <th className="px-4 py-2 font-medium">Est. revenue lost</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {inverters.map((inv) => (
                  <tr key={inv.label}>
                    <td className="px-4 py-2 font-mono text-xs text-gray-700">{inv.label}</td>
                    <td className="px-4 py-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_STYLES[inv.status]}`}>
                        {inv.status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-gray-600">{inv.flagged_hours}</td>
                    <td className="px-4 py-2 text-gray-600">{inv.true_fault_hours}</td>
                    <td className="px-4 py-2 text-gray-600">{inv.est_kwh_lost.toFixed(2)} kWh</td>
                    <td className="px-4 py-2 text-gray-600">{inv.est_revenue_lost.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <div className="text-sm font-medium text-gray-700 mb-1">Model comparison</div>
            <p className="text-xs text-gray-500 mb-2">
              Scored against the known injected faults. Pick a model to see its results above.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[560px]">
                <thead className="bg-gray-50 text-left text-gray-500 text-xs uppercase tracking-wide">
                  <tr>
                    <th className="px-4 py-2 font-medium">Model</th>
                    <th className="px-4 py-2 font-medium">Precision</th>
                    <th className="px-4 py-2 font-medium">Recall</th>
                    <th className="px-4 py-2 font-medium">F1</th>
                    <th className="px-4 py-2 font-medium">R²</th>
                    <th className="px-4 py-2 font-medium">MAE (kW)</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {result.comparison.map((m) => {
                    const active = m.model === result.model;
                    return (
                      <tr key={m.model} className={active ? "bg-blue-50" : ""}>
                        <td className="px-4 py-2 text-gray-800">
                          {modelLabel(m.model)}
                          {m.model === bestModel && (
                            <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">
                              best F1
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-gray-600">{fmt(m.precision)}</td>
                        <td className="px-4 py-2 text-gray-600">{fmt(m.recall)}</td>
                        <td className="px-4 py-2 font-medium text-gray-800">{fmt(m.f1)}</td>
                        <td className="px-4 py-2 text-gray-600">{fmt(m.r2, 3)}</td>
                        <td className="px-4 py-2 text-gray-600">{fmt(m.mae_kw, 3)}</td>
                        <td className="px-4 py-2 text-right">
                          {active ? (
                            <span className="text-xs text-blue-700 font-medium">Showing</span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => run(m.model)}
                              disabled={loading}
                              className="text-xs text-blue-600 hover:underline font-medium disabled:opacity-50"
                            >
                              View
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-xs text-gray-400">
            Weather is real; panel output is simulated from it with injected faults, which is what
            makes these accuracy numbers measurable. Simulated output over the 30 days:{" "}
            {result.totals.energy_kwh.toFixed(0)} kWh.
          </p>
        </div>
      )}
    </div>
  );
}
