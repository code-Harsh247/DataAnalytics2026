"use client";

import Link from "next/link";
import { useLive } from "@/context/LiveContext";
import { getOverview } from "@/lib/pages";
import { usePageData } from "@/lib/usePageData";
import { co2, kwh, money, pct } from "@/lib/format";
import { LoadState, PageBody, Panel, Stat } from "@/components/ui";
import { DayCurveChart } from "@/components/DayCurveChart";

export default function OverviewPage() {
  const { data, error, refreshing } = usePageData(getOverview);
  const { status } = useLive();

  if (!data) {
    return (
      <PageBody>
        <LoadState error={error} loading={refreshing || !error} />
      </PageBody>
    );
  }

  const ratio = data.now && data.now.expected_kw > 0.05 ? data.now.power_kw / data.now.expected_kw : null;
  const verdicts = status?.inverters ?? [];
  const under = verdicts.filter((v) => v.state === "underperforming");
  const offline = verdicts.length > 0 && verdicts.every((v) => v.state === "offline");
  const learning = verdicts.length > 0 && verdicts.every((v) => v.state === "learning");

  return (
    <PageBody>
      {under.length > 0 && (
        <Link
          href="/health"
          className="block rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800 hover:bg-red-100"
        >
          <span className="font-semibold">
            {under.map((u) => u.label).join(", ")} {under.length === 1 ? "is" : "are"} under-producing
          </span>{" "}
          — see Health →
        </Link>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat
          label="Power now"
          value={data.now ? `${data.now.power_kw.toFixed(2)} kW` : "—"}
          sub={
            data.now
              ? `expected ${data.now.expected_kw.toFixed(2)} kW${ratio != null ? ` · ${pct(ratio)} of expected` : ""}`
              : "no readings yet"
          }
          tone={ratio != null && ratio < 0.85 ? "warn" : "neutral"}
        />
        <Stat
          label="Today"
          value={kwh(data.today.energy_kwh)}
          sub={`earned ${money(data.today.revenue)}${data.today.forecast_kwh != null ? ` · forecast ${kwh(data.today.forecast_kwh)}` : ""}`}
        />
        <Stat label="This month" value={kwh(data.month.energy_kwh, 0)} sub={`earned ${money(data.month.revenue)}`} />
        <Stat label="Lifetime" value={kwh(data.lifetime.energy_kwh, 0)} sub={`earned ${money(data.lifetime.revenue)}`} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat
          label="Performance ratio"
          value={pct(data.pr.today)}
          sub={`today · 30-day ${pct(data.pr.d30)}`}
          tone={data.pr.today != null && data.pr.today < 0.7 ? "warn" : "neutral"}
        />
        <Stat
          label="Specific yield"
          value={data.specific_yield_today != null ? `${data.specific_yield_today.toFixed(2)}` : "—"}
          sub="kWh per kWp today"
        />
        <Stat label="CO₂ avoided" value={co2(data.lifetime.co2_kg)} sub={`this month ${co2(data.month.co2_kg)}`} />
        <Stat
          label="Health"
          value={
            !status ? "—" : under.length > 0 ? `${under.length} issue${under.length > 1 ? "s" : ""}`
              : offline ? "Offline" : learning ? "Learning" : "All OK"
          }
          sub={
            <Link href="/health" className="text-blue-600 hover:underline">
              {verdicts.length} inverters · details
            </Link>
          }
          tone={under.length > 0 ? "bad" : offline ? "warn" : status ? "good" : "neutral"}
        />
      </div>

      <Panel
        title="Today's output"
        subtitle={`Actual so far vs the forecast for ${data.date} (plant time, ${data.timezone})`}
      >
        <DayCurveChart actual={data.today_curve.actual} forecast={data.today_curve.forecast} tz={data.timezone} />
      </Panel>

      <p className="text-xs text-gray-400">
        Performance ratio = energy delivered ÷ (sunlight on the panels × installed kWp); healthy plants run at
        about 75–85%. CO₂ uses the Indian grid average of 0.716 kg per kWh.
      </p>
    </PageBody>
  );
}
