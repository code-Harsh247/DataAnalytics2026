"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { usePlant } from "@/context/PlantContext";
import { useLive } from "@/context/LiveContext";
import { getHealth } from "@/lib/pages";
import { usePageData } from "@/lib/usePageData";
import { kwh, localDateTime, money } from "@/lib/format";
import { getInverterLatest, type InverterLatest } from "@/lib/plantDashboard";
import type { InverterState } from "@/lib/status";
import { CHART_COLORS, LoadState, PageBody, Panel } from "@/components/ui";
import { VerdictBanner } from "@/components/VerdictBanner";
import { AnalysisPanel } from "@/components/AnalysisPanel";

const STATE_BADGES: Record<InverterState, { text: string; className: string }> = {
  ok: { text: "OK", className: "bg-green-100 text-green-700" },
  underperforming: { text: "Under-producing", className: "bg-red-100 text-red-700" },
  offline: { text: "Not reporting", className: "bg-gray-200 text-gray-600" },
  learning: { text: "Learning", className: "bg-blue-100 text-blue-700" },
  no_data: { text: "No data", className: "bg-gray-100 text-gray-500" },
};

// Waterfall bars: the first step is the full potential, each loss floats down
// from the running total, the last step (delivered) stands on zero.
function buildWaterfall(losses: { name: string; kwh: number }[]) {
  const bars: { name: string; base: number; value: number; kind: "start" | "loss" | "end" }[] = [];
  let running = 0;
  losses.forEach((step, i) => {
    if (i === 0) {
      running = step.kwh;
      bars.push({ name: step.name, base: 0, value: step.kwh, kind: "start" });
    } else if (i === losses.length - 1) {
      bars.push({ name: step.name, base: 0, value: step.kwh, kind: "end" });
    } else {
      running -= step.kwh;
      bars.push({ name: step.name, base: Math.max(running, 0), value: step.kwh, kind: "loss" });
    }
  });
  return bars;
}

export default function HealthPage() {
  const { plant } = usePlant();
  const { status, statusError, version } = useLive();
  const { data, error, refreshing } = usePageData(getHealth);
  const [latest, setLatest] = useState<InverterLatest[]>([]);

  useEffect(() => {
    if (!plant) return;
    let cancelled = false;
    getInverterLatest(plant.id)
      .then((rows) => {
        if (!cancelled) setLatest(rows);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [plant, version]);

  if (!plant) return null;
  const verdicts = new Map((status?.inverters ?? []).map((v) => [v.label, v]));
  const tz = data?.timezone ?? "UTC";

  const waterfall = buildWaterfall(data?.losses ?? []);

  return (
    <PageBody>
      <VerdictBanner status={status} error={statusError} />

      <Panel title="Inverters right now" subtitle="Health comes from the detector: each inverter vs what the weather and its neighbours say it should make.">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[600px]">
            <thead className="text-left text-gray-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="py-1.5 font-medium">Inverter</th>
                <th className="py-1.5 font-medium">Health</th>
                <th className="py-1.5 font-medium">Vs expected</th>
                <th className="py-1.5 font-medium">Output</th>
                <th className="py-1.5 font-medium">Availability ({data?.days ?? 30} d)</th>
                <th className="py-1.5 font-medium">Last reading</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {latest.map((inv) => {
                const v = verdicts.get(inv.label);
                const badge = v ? STATE_BADGES[v.state] : null;
                const shortfall = v?.shortfall_pct;
                const availability = data?.availability.find((a) => a.label === inv.label)?.pct;
                return (
                  <tr key={inv.id}>
                    <td className="py-2 font-mono text-xs text-gray-700">{inv.label}</td>
                    <td className="py-2">
                      {badge ? (
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badge.className}`}>{badge.text}</span>
                      ) : (
                        <span className="text-xs text-gray-400">—</span>
                      )}
                    </td>
                    <td className="py-2 text-gray-600">
                      {shortfall == null ? "—" : shortfall > 0 ? `${shortfall.toFixed(1)}% below` : `${Math.abs(shortfall).toFixed(1)}% above`}
                    </td>
                    <td className="py-2 text-gray-600">{inv.latest_ac_power_kw != null ? `${inv.latest_ac_power_kw.toFixed(2)} kW` : "—"}</td>
                    <td className="py-2 text-gray-600">{availability != null ? `${availability.toFixed(1)}%` : "—"}</td>
                    <td className="py-2 text-gray-400 text-xs">{inv.latest_recorded_at ? localDateTime(inv.latest_recorded_at, tz) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {!data ? (
        <LoadState error={error} loading={refreshing || !error} />
      ) : (
        <>
          <Panel
            title="Alert history"
            subtitle={`Every stretch the detector flagged in the last ${data.days} days (3+ readings in a row), with what it cost.`}
          >
            {data.alerts.length === 0 ? (
              <p className="text-sm text-gray-500">No alerts. Every inverter has produced what it should.</p>
            ) : (
              <div className="overflow-x-auto max-h-80 overflow-y-auto">
                <table className="w-full text-sm min-w-[600px]">
                  <thead className="text-left text-gray-500 text-xs uppercase tracking-wide sticky top-0 bg-white">
                    <tr>
                      <th className="py-1.5 font-medium">Inverter</th>
                      <th className="py-1.5 font-medium">From</th>
                      <th className="py-1.5 font-medium">To</th>
                      <th className="py-1.5 font-medium">Shortfall</th>
                      <th className="py-1.5 font-medium">Lost</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {data.alerts.map((a) => (
                      <tr key={`${a.label}-${a.start}`}>
                        <td className="py-2 font-mono text-xs text-gray-700">{a.label}</td>
                        <td className="py-2 text-gray-600">{localDateTime(a.start, tz)}</td>
                        <td className="py-2 text-gray-600">
                          {a.ongoing ? <span className="text-red-600 font-medium">ongoing</span> : localDateTime(a.end, tz)}
                        </td>
                        <td className="py-2 text-gray-600">~{a.shortfall_pct.toFixed(0)}%</td>
                        <td className="py-2 text-gray-600">
                          {kwh(a.kwh_lost, 2)} · {money(a.revenue_lost, 2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          {waterfall.length > 0 && (
            <Panel
              title="Where the energy went"
              subtitle={`Last ${data.days} days: from what the sunlight could have given at nameplate, down to what was delivered.`}
            >
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={waterfall} margin={{ top: 5, right: 10, left: 0, bottom: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" />
                  <YAxis tick={{ fontSize: 11 }} label={{ value: "kWh", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <Tooltip
                    formatter={(v, name) => (name === "base" ? [null, null] : [`${Number(v).toFixed(1)} kWh`, "Energy"])}
                  />
                  <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
                  <Bar dataKey="value" stackId="w" isAnimationActive={false}>
                    {waterfall.map((w) => (
                      <Cell
                        key={w.name}
                        fill={w.kind === "start" ? CHART_COLORS.sun : w.kind === "end" ? CHART_COLORS.revenue : CHART_COLORS.bad}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Panel>
          )}
        </>
      )}

      <AnalysisPanel plant={plant} />
    </PageBody>
  );
}
