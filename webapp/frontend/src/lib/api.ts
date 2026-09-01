const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Plant {
  id: number;
  name: string;
  description: string;
}

export interface Timeline {
  start: string;
  end: string;
}

export interface DailyTrendPoint {
  date: string;
  actual_kwh: number;
  expected_kwh: number;
}

export interface Overview {
  as_of: string;
  daily_trend: DailyTrendPoint[];
  today_actual_kwh: number | null;
  today_expected_kwh: number | null;
  active_risk_count: number;
  watch_count: number;
  healthy_count: number;
  total_revenue_lost: number;
  forecast_tomorrow_kwh: number | null;
  health_score: number | null;
}

export type InverterStatus = "healthy" | "watch" | "at_risk";
export type Trend = "worsening" | "stable" | "improving" | "insufficient_data";

export interface InverterSummary {
  source_key: string;
  status: InverterStatus;
  mean_residual: number;
  z_score: number;
  est_kwh_lost: number;
  est_revenue_lost: number;
  trend: Trend;
  projected_days_to_critical: number | null;
}

export interface ResidualPoint {
  irradiation: number;
  residual: number;
}

export interface DailySeverityPoint {
  date: string;
  mean_residual: number;
}

export interface InverterDetail {
  source_key: string;
  status: InverterStatus | null;
  mean_residual: number | null;
  z_score: number | null;
  est_kwh_lost: number | null;
  est_revenue_lost: number | null;
  points: ResidualPoint[];
  daily_severity: DailySeverityPoint[];
  trend: Trend;
  slope_per_day: number | null;
  p_value: number | null;
  projected_days_to_critical: number | null;
}

export interface ForecastHistoryPoint {
  date: string;
  actual_kwh: number;
  persistence_kwh: number | null;
  climatology_kwh: number | null;
}

export interface ForecastRange {
  low: number;
  high: number;
}

export interface Forecast {
  history: ForecastHistoryPoint[];
  forecast_tomorrow_kwh: number | null;
  forecast_range: ForecastRange | null;
  monthly_revenue_projection: number | null;
  insufficient_data?: boolean;
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API error ${res.status} on ${path}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getPlants: () => apiGet<Plant[]>("/api/plants"),
  getTimeline: (plantId: number) => apiGet<Timeline>(`/api/plants/${plantId}/timeline`),
  getOverview: (plantId: number, asOf: string) =>
    apiGet<Overview>(`/api/plants/${plantId}/overview?as_of=${asOf}`),
  getInverters: (plantId: number, asOf: string) =>
    apiGet<InverterSummary[]>(`/api/plants/${plantId}/inverters?as_of=${asOf}`),
  getInverterDetail: (plantId: number, sourceKey: string, asOf: string) =>
    apiGet<InverterDetail>(`/api/plants/${plantId}/inverters/${sourceKey}?as_of=${asOf}`),
  getForecast: (plantId: number, asOf: string) =>
    apiGet<Forecast>(`/api/plants/${plantId}/forecast?as_of=${asOf}`),
};
