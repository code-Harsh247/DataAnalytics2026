import type { Plant } from "./plants";
import { resolvePlantDefaults } from "./generation";

// Client for POST /api/plants/analyze -- see Contract 3 in PRODUCT_PLAN.md.
// Talks to the real endpoint directly; the planned mock was skipped because
// the endpoint landed on main before this panel was built.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// The backend detects faults by comparing each inverter against its peers,
// so it rejects plants with fewer than this many inverters.
export const MIN_INVERTERS_FOR_ANALYSIS = 2;

export interface AnalysisPeriod {
  start: string;
  end: string;
  test_start: string;
  test_fault_hours: number; // 0 -> precision/recall/f1 are null
}

export interface AnalysisSeriesPoint {
  timestamp: string;
  actual_kw: number | null;
  expected_kw: number | null; // null for models without a power model
  flagged: boolean;
  true_fault: boolean;
}

export type AnalysisInverterStatus = "healthy" | "warning" | "critical";

export interface AnalysisInverter {
  label: string;
  flagged_hours: number;
  true_fault_hours: number;
  est_kwh_lost: number;
  est_revenue_lost: number;
  status: AnalysisInverterStatus;
}

export interface ModelComparison {
  model: string;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  r2: number | null;
  mae_kw: number | null;
}

export interface AnalysisResult {
  model: string;
  period: AnalysisPeriod;
  series: AnalysisSeriesPoint[];
  inverters: AnalysisInverter[];
  comparison: ModelComparison[]; // sorted by f1 desc
  totals: { energy_kwh: number; revenue: number };
}

// FastAPI returns `detail` as a string for our own errors (400/502) and as a
// list of validation errors for 422.
function describeError(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(-1)[0] ?? "field"}: ${d.msg ?? "invalid"}`)
      .join("; ");
  }
  return `Analysis failed (HTTP ${status})`;
}

export async function runAnalysis(plant: Plant, model?: string): Promise<AnalysisResult> {
  const d = resolvePlantDefaults(plant);
  const res = await fetch(`${API_BASE}/api/plants/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lat: plant.latitude,
      lon: plant.longitude,
      capacity_kw: d.capacityKw,
      tilt_degrees: d.tiltDegrees,
      azimuth_degrees: d.azimuthDegrees,
      temp_coefficient: d.tempCoefficient,
      degradation_factor: d.degradationFactor,
      inverter_count: d.inverterCount,
      tariff_per_kwh: plant.tariff_per_kwh,
      ...(model ? { model } : {}),
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(describeError(res.status, body));
  }
  return res.json() as Promise<AnalysisResult>;
}
