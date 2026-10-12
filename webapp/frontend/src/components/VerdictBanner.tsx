import type { PlantStatus } from "@/lib/status";
import { formatUtcTime } from "@/lib/time";

// The one-line answer to "is my plant OK right now?", from the live detector
// (GET /api/plants/{id}/status).
export function VerdictBanner({ status, error }: { status: PlantStatus | null; error: string | null }) {
  if (error) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600">
        Couldn&apos;t check inverter health right now: {error}
      </div>
    );
  }
  if (!status) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-500">
        Checking inverter health…
      </div>
    );
  }

  const inverters = status.inverters;
  const under = inverters.filter((i) => i.state === "underperforming");
  const offline = inverters.filter((i) => i.state === "offline");

  if (inverters.length === 0 || inverters.every((i) => i.state === "no_data")) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600">
        No readings yet. Connect a gateway to start monitoring.
      </div>
    );
  }
  if (inverters.every((i) => i.state === "learning")) {
    return (
      <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
        Learning what normal output looks like for this plant. Health checks start after a few days of
        readings.
      </div>
    );
  }
  if (under.length > 0) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 space-y-1">
        {under.map((inv) => (
          <div key={inv.label} className="text-sm text-red-800">
            <span className="font-semibold">{inv.label} is under-producing</span>
            {inv.shortfall_pct != null && <> by ~{Math.round(inv.shortfall_pct)}%</>}
            {inv.since && <> since {formatUtcTime(inv.since)}</>}
            {inv.est_revenue_lost_24h != null && inv.est_revenue_lost_24h > 0 && (
              <span className="text-red-700">
                {" "}· ≈{inv.est_revenue_lost_24h.toFixed(2)} lost in the last 24 h ({inv.est_kwh_lost_24h?.toFixed(2)} kWh)
              </span>
            )}
          </div>
        ))}
        <div className="text-xs text-red-700/80">
          Compared with what the weather and its neighbouring inverters say it should be producing.
        </div>
      </div>
    );
  }
  if (offline.length === inverters.length) {
    return (
      <div className="rounded-lg border border-gray-300 bg-gray-100 px-4 py-3 text-sm text-gray-700">
        No readings from the plant recently. The gateway may be offline.
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
      <span className="font-semibold">All {inverters.length - offline.length} inverters are producing as expected</span>
      {offline.length > 0 && <> ({offline.map((i) => i.label).join(", ")} not reporting)</>}.
    </div>
  );
}
