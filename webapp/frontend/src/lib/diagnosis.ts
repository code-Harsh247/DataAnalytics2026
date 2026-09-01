import type { InverterStatus, Trend } from "./api";

// Rule-based, not generated text — derived transparently from the same
// status/trend/z-score fields shown elsewhere on the page. No claim of a
// deeper diagnosis model than what's actually computed (see PRODUCT_PLAN.md
// Phase 3 on why trend scoring is framed honestly, not as predictive AI).
export function getDiagnosis(
  status: InverterStatus,
  trend: Trend,
  projectedDays: number | null,
): string {
  if (status === "healthy") {
    if (trend === "worsening") {
      return projectedDays !== null
        ? `Currently healthy, but output is trending down. At this rate, expect it to cross a concerning threshold in about ${projectedDays} days — worth keeping an eye on.`
        : "Currently healthy, but output is trending down. Worth keeping an eye on.";
    }
    if (trend === "improving") return "Performing well, and trending better than the plant average.";
    return "Performing as expected — no action needed.";
  }

  const severity = status === "at_risk" ? "Significantly" : "Somewhat";
  if (trend === "worsening") {
    return (
      `${severity} underperforming and getting worse. Recommend prioritizing an inspection` +
      (projectedDays !== null ? ` — projected ~${projectedDays} days until critical.` : ".")
    );
  }
  if (trend === "improving") {
    return `${severity} underperforming, but recovering. May resolve on its own — monitor before dispatching a technician.`;
  }
  return (
    `Consistently ${severity.toLowerCase()} underperforming its expected output. Pattern suggests a ` +
    "persistent issue (e.g. wiring, partial shading, or inverter inefficiency) rather than a new, developing fault."
  );
}
