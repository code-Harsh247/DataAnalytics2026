"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { usePlant } from "@/context/PlantContext";
import { supabase } from "@/lib/supabase";
import { getFinance } from "@/lib/pages";
import { usePageData } from "@/lib/usePageData";
import { kwh, money, monthLabel, pct } from "@/lib/format";
import { CHART_COLORS, LoadState, PageBody, Panel, Stat } from "@/components/ui";

const PAYBACK_YEARS_SHOWN = 15;
const ANNUAL_DEGRADATION = 0.005; // same 0.5%/year the physics uses for panel ageing

export default function FinancePage() {
  const { plant } = usePlant();
  const { data, error, refreshing, reload } = usePageData(getFinance);
  const [costInput, setCostInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  if (!plant) return null;
  if (!data) {
    return (
      <PageBody>
        <LoadState error={error} loading={refreshing || !error} />
      </PageBody>
    );
  }

  const saveCost = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = Number(costInput);
    if (!Number.isFinite(value) || value <= 0) {
      setSaveError("Enter the total system cost as a positive number.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    const { error: updateError } = await supabase.from("plants").update({ system_cost: value }).eq("id", plant.id);
    setSaving(false);
    if (updateError) {
      setSaveError(
        updateError.message.includes("system_cost")
          ? "Run webapp/supabase/006_finance.sql in Supabase first."
          : updateError.message,
      );
      return;
    }
    setCostInput("");
    reload();
  };

  // Cumulative projected earnings, with panels ageing 0.5%/year.
  const annual = data.annual?.revenue ?? 0;
  const cumulative = Array.from({ length: PAYBACK_YEARS_SHOWN + 1 }, (_, year) => {
    let total = data.lifetime.revenue;
    for (let y = 0; y < year; y++) total += annual * Math.pow(1 - ANNUAL_DEGRADATION, y);
    return { year, earnings: Math.round(total) };
  });

  return (
    <PageBody>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Earned to date" value={money(data.lifetime.revenue)} sub={`${kwh(data.lifetime.energy_kwh, 0)} at ${data.tariff_per_kwh}/kWh`} />
        <Stat
          label="Average per day"
          value={money(data.avg_daily_revenue)}
          sub={data.avg_daily_energy_kwh != null ? `${kwh(data.avg_daily_energy_kwh)} · last 30 days` : undefined}
        />
        <Stat
          label="Projected per year"
          value={data.annual ? money(data.annual.revenue) : "—"}
          sub={data.annual ? `${kwh(data.annual.energy_kwh, 0)} in a typical year` : "weather archive unavailable"}
        />
        <Stat
          label="Payback"
          value={data.payback_years != null ? `${data.payback_years.toFixed(1)} years` : "—"}
          sub={data.system_cost ? `on a system cost of ${money(data.system_cost)}` : "enter the system cost below"}
          tone={data.payback_years != null && data.payback_years > 10 ? "warn" : "neutral"}
        />
      </div>

      <Panel
        title="Payback"
        subtitle="Earnings so far plus the projected earnings of each coming year (simple payback: no interest, tariff held constant)."
        right={
          <form onSubmit={saveCost} className="flex items-center gap-2">
            <input
              type="number"
              min={0}
              step="any"
              value={costInput}
              onChange={(e) => setCostInput(e.target.value)}
              placeholder={data.system_cost ? `System cost: ${data.system_cost}` : "System cost"}
              className="border rounded px-2 py-1 text-sm w-40"
            />
            <button
              type="submit"
              disabled={saving || !costInput}
              className="bg-blue-600 text-white text-sm font-medium px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Saving…" : data.system_cost ? "Update" : "Save"}
            </button>
          </form>
        }
      >
        {saveError && <p className="text-sm text-red-600 mb-2">{saveError}</p>}
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={cumulative} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="year" tick={{ fontSize: 11 }} label={{ value: "years from now", position: "insideBottom", offset: -2, fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => money(Number(v))} width={70} />
            <Tooltip formatter={(v) => [money(Number(v)), "Cumulative earnings"]} labelFormatter={(y) => `Year ${y}`} />
            {data.system_cost && (
              <ReferenceLine
                y={data.system_cost}
                stroke={CHART_COLORS.bad}
                strokeDasharray="5 4"
                label={{ value: "system cost", position: "insideTopLeft", fontSize: 11, fill: CHART_COLORS.bad }}
              />
            )}
            <Line dataKey="earnings" stroke={CHART_COLORS.revenue} strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Earnings by month" subtitle="Whole history, in the plant's time zone.">
        {data.monthly.length === 0 ? (
          <p className="text-sm text-gray-500">
            Monthly totals need <code>webapp/supabase/006_finance.sql</code> to be run in Supabase.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.monthly.map((m) => ({ ...m, label: monthLabel(m.month) }))} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => money(Number(v))} width={70} />
              <Tooltip formatter={(v) => [money(Number(v)), "Earned"]} />
              <Bar dataKey="revenue" fill={CHART_COLORS.revenue} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Panel>

      {data.annual && (
        <p className="text-xs text-gray-400">
          The yearly projection runs the plant&apos;s physics model over the real weather at its location from{" "}
          {data.annual.weather_from} to {data.annual.weather_to}, scaled by how the plant has actually performed
          recently ({pct(data.calibration)} of the model). Earnings use your tariff of {data.tariff_per_kwh} per kWh.
        </p>
      )}
    </PageBody>
  );
}
