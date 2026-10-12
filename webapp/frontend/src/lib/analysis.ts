import type { Plant } from "./plants";
import { backendFetch } from "./backend";

// Client for POST /api/plants/{id}/analyze (Contract 6a in PRODUCT_PLAN.md):
// the 30-day analysis of the readings stored for this plant -- the same data
// the dashboard shows. Response shape = Contract 3, plus source/coverage.

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
  source?: "stored";
  period: AnalysisPeriod;
  coverage?: { expected_rows: number; present_rows: number };
  series: AnalysisSeriesPoint[];
  inverters: AnalysisInverter[];
  comparison: ModelComparison[]; // sorted by f1 desc
  totals: { energy_kwh: number; revenue: number };
}

export function runAnalysis(plant: Plant, model?: string): Promise<AnalysisResult> {
  return backendFetch<AnalysisResult>(`/api/plants/${plant.id}/analyze`, {
    method: "POST",
    body: JSON.stringify(model ? { model } : {}),
  });
}
