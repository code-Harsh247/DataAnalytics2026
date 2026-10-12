import { backendFetch } from "./backend";

// Clients for the plant pages' endpoints (Contract 7 in PRODUCT_PLAN.md).
// Definitions -- performance ratio, specific yield, calibration -- are in the plan.

export interface EnergySummary {
  energy_kwh: number;
  revenue: number;
  co2_kg: number;
}

export interface CurvePoint {
  t: string;
  kw: number;
}

export interface Overview {
  capacity_kw: number;
  timezone: string;
  date: string;
  now: { power_kw: number; expected_kw: number; as_of: string } | null;
  today: EnergySummary & { forecast_kwh: number | null };
  month: EnergySummary;
  lifetime: EnergySummary;
  pr: { today: number | null; d30: number | null };
  specific_yield_today: number | null;
  today_curve: { actual: CurvePoint[]; forecast: CurvePoint[] };
}

export interface ProductionDay {
  date: string;
  energy_kwh: number;
  revenue: number;
  specific_yield: number;
  pr: number | null;
  peak_kw: number;
  insolation_kwh_m2: number;
  partial: boolean; // today, still in progress
}

export interface MonthTotal {
  month: string;
  energy_kwh: number;
  revenue: number;
}

export interface Production {
  capacity_kw: number;
  timezone: string;
  days: ProductionDay[];
  monthly: MonthTotal[];
  inverters: { label: string; energy_kwh: number; share: number; pr: number | null; specific_yield: number | null }[];
  best_day: ProductionDay | null;
  worst_day: ProductionDay | null;
  totals: EnergySummary & { specific_yield: number; pr: number | null };
}

export interface ForecastDay {
  date: string;
  energy_kwh: number;
  revenue: number;
  p10_kwh: number;
  p90_kwh: number;
  cloud_cover: number | null;
}

export interface Forecast {
  calibration: number;
  timezone: string;
  days: ForecastDay[];
  today: { forecast: CurvePoint[]; actual: CurvePoint[]; actual_kwh: number };
  accuracy: { days: { date: string; forecast_kwh: number; actual_kwh: number; error_pct: number }[]; mape: number | null };
  band: { low: number; high: number; from_accuracy: boolean };
  month_projection_kwh: number;
  month_projection_revenue: number;
}

export interface Alert {
  label: string;
  start: string;
  end: string;
  ongoing: boolean;
  shortfall_pct: number;
  kwh_lost: number;
  revenue_lost: number;
}

export interface Health {
  timezone: string;
  availability: { label: string; pct: number | null }[];
  alerts: Alert[];
  losses: { name: string; kwh: number }[];
  days: number;
}

export interface Finance {
  tariff_per_kwh: number;
  monthly: MonthTotal[];
  lifetime: EnergySummary;
  avg_daily_revenue: number | null;
  avg_daily_energy_kwh: number | null;
  annual: { energy_kwh: number; revenue: number; weather_from: string; weather_to: string } | null;
  calibration: number;
  system_cost: number | null;
  payback_years: number | null;
}

export const getOverview = (id: string) => backendFetch<Overview>(`/api/plants/${id}/overview`);
export const getProduction = (id: string) => backendFetch<Production>(`/api/plants/${id}/production`);
export const getForecast = (id: string) => backendFetch<Forecast>(`/api/plants/${id}/forecast`);
export const getHealth = (id: string) => backendFetch<Health>(`/api/plants/${id}/health`);
export const getFinance = (id: string) => backendFetch<Finance>(`/api/plants/${id}/finance`);
