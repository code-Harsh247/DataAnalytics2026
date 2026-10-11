import { supabase } from "./supabase";
import type { Plant } from "./plants";

const DEFAULT_INVERTER_COUNT = 4;
const DEFAULT_CAPACITY_KW = 5.0;
const TYPICAL_PANEL_DENSITY_W_PER_SQM = 150; // installed-area density, not bare panel density
const REVENUE_INTERVAL_HOURS = 0.25; // 15-minute ticks
// Same fault model as the backend backfill (app/backfill.py), so the live
// dashboard and the 30-day analysis describe the same plant: ~8-10% of
// hours faulted, not the ~50% the old 4%-per-tick rate produced.
const FAULT_START_PROB_PER_HOUR = 0.02; // per currently-healthy inverter
const FAULT_START_PROBABILITY = FAULT_START_PROB_PER_HOUR * REVENUE_INTERVAL_HOURS; // per tick
const FAULT_MIN_HOURS = 2;
const FAULT_MAX_HOURS = 8;
const FAULT_MIN_SEVERITY = 0.05;
const FAULT_MAX_SEVERITY = 0.4;

// Real per-module-type temperature coefficients (%/deg C above 25C STC).
// Thin-film genuinely tolerates heat better than crystalline silicon in
// practice -- this isn't a made-up spread.
const MODULE_TEMP_COEFFICIENTS: Record<string, number> = {
  Monocrystalline: -0.0035,
  Polycrystalline: -0.0041,
  "Thin-film": -0.0025,
  Other: -0.0038,
};
const DEFAULT_TEMP_COEFFICIENT = -0.0038;

const ANNUAL_DEGRADATION_RATE = 0.005; // ~0.5%/year, typical crystalline silicon
const MIN_DEGRADATION_FACTOR = 0.7; // floor so a bad/old date can't zero out output

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PlantDefaults {
  capacityKw: number;
  tiltDegrees: number;
  azimuthDegrees: number;
  inverterCount: number;
  tempCoefficient: number;
  degradationFactor: number;
}

function resolveTempCoefficient(moduleType: string | null): number {
  if (!moduleType) return DEFAULT_TEMP_COEFFICIENT;
  return MODULE_TEMP_COEFFICIENTS[moduleType] ?? DEFAULT_TEMP_COEFFICIENT;
}

function resolveDegradationFactor(commissioningDate: string | null): number {
  if (!commissioningDate) return 1.0;
  const ageMs = Date.now() - new Date(commissioningDate).getTime();
  const ageYears = ageMs / (365.25 * 24 * 60 * 60 * 1000);
  if (ageYears <= 0) return 1.0; // future/invalid date -- don't apply negative "aging"
  return Math.max(1 - ANNUAL_DEGRADATION_RATE * ageYears, MIN_DEGRADATION_FACTOR);
}

// Fallback chain for the optional Tier 2 fields from plant setup -- see
// PRODUCT_PLAN.md Phase 13/14 for the reasoning behind each default.
export function resolvePlantDefaults(plant: Plant): PlantDefaults {
  let capacityKw = plant.capacity_kw ?? undefined;
  if (!capacityKw && plant.panel_count && plant.module_wattage_w) {
    capacityKw = (plant.panel_count * plant.module_wattage_w) / 1000;
  }
  if (!capacityKw && plant.area_sqm) {
    capacityKw = (plant.area_sqm * TYPICAL_PANEL_DENSITY_W_PER_SQM) / 1000;
  }
  if (!capacityKw) capacityKw = DEFAULT_CAPACITY_KW;

  // Lightweight plausibility check, not a blocking validation -- if both an
  // explicit capacity and an area were given and they're wildly
  // inconsistent (e.g. 100kW claimed on a 10 sqm plot), that's worth a
  // signal even with no UI yet to show it in.
  if (plant.capacity_kw && plant.area_sqm) {
    const impliedCapacityKw = (plant.area_sqm * TYPICAL_PANEL_DENSITY_W_PER_SQM) / 1000;
    const ratio = plant.capacity_kw / impliedCapacityKw;
    if (ratio > 3 || ratio < 1 / 3) {
      console.warn(
        `Plant ${plant.id}: entered capacity (${plant.capacity_kw}kW) and area ` +
          `(${plant.area_sqm} sqm, implies ~${impliedCapacityKw.toFixed(1)}kW at ` +
          `${TYPICAL_PANEL_DENSITY_W_PER_SQM}W/sqm) are inconsistent -- worth a data check.`,
      );
    }
  }

  const tiltDegrees = plant.tilt_degrees ?? Math.min(Math.max(Math.abs(plant.latitude), 10), 40);
  const azimuthDegrees = plant.azimuth_degrees ?? (plant.latitude >= 0 ? 180 : 0);
  const inverterCount = plant.inverter_count ?? DEFAULT_INVERTER_COUNT;
  const tempCoefficient = resolveTempCoefficient(plant.module_type);
  const degradationFactor = resolveDegradationFactor(plant.commissioning_date);

  return { capacityKw, tiltDegrees, azimuthDegrees, inverterCount, tempCoefficient, degradationFactor };
}

export interface Inverter {
  id: string;
  plant_id: string;
  label: string;
  base_efficiency_factor: number;
}

export async function getOrCreateInverters(plant: Plant): Promise<Inverter[]> {
  const { data: existing, error: fetchError } = await supabase
    .from("inverters")
    .select("*")
    .eq("plant_id", plant.id);
  if (fetchError) throw fetchError;
  if (existing && existing.length > 0) return existing;

  const { inverterCount } = resolvePlantDefaults(plant);
  const rows = Array.from({ length: inverterCount }, (_, i) => ({
    plant_id: plant.id,
    label: `INV-${i + 1}`,
    base_efficiency_factor: 0.96 + Math.random() * 0.06, // persistent healthy spread
  }));

  const { data: created, error: insertError } = await supabase.from("inverters").insert(rows).select();
  if (insertError) throw insertError;
  return created ?? [];
}

async function getActiveFaultSeverities(inverterIds: string[]): Promise<Map<string, number>> {
  if (inverterIds.length === 0) return new Map();
  const nowIso = new Date().toISOString();
  const { data, error } = await supabase
    .from("inverter_faults")
    .select("inverter_id, severity")
    .in("inverter_id", inverterIds)
    .lte("started_at", nowIso)
    .gt("ends_at", nowIso);
  if (error) throw error;

  const map = new Map<string, number>();
  for (const row of (data ?? []) as { inverter_id: string; severity: number }[]) {
    map.set(row.inverter_id, Math.max(map.get(row.inverter_id) ?? 0, row.severity));
  }
  return map;
}

async function maybeStartFaults(inverterIds: string[], alreadyFaulted: Set<string>): Promise<void> {
  const candidates = inverterIds.filter(
    (id) => !alreadyFaulted.has(id) && Math.random() < FAULT_START_PROBABILITY,
  );
  if (candidates.length === 0) return;

  const now = new Date();
  const rows = candidates.map((inverter_id) => {
    const hours = FAULT_MIN_HOURS + Math.random() * (FAULT_MAX_HOURS - FAULT_MIN_HOURS);
    const severity = FAULT_MIN_SEVERITY + Math.random() * (FAULT_MAX_SEVERITY - FAULT_MIN_SEVERITY);
    return {
      inverter_id,
      started_at: now.toISOString(),
      ends_at: new Date(now.getTime() + hours * 60 * 60 * 1000).toISOString(),
      severity: Math.round(severity * 1000) / 1000,
    };
  });

  const { error } = await supabase.from("inverter_faults").insert(rows);
  if (error) throw error;
}

interface GenerationApiResponse {
  poa_irradiance_wm2: number;
  cell_temp_c: number;
  readings: { inverter_id: string; dc_power_kw: number; ac_power_kw: number; fault_active: boolean }[];
}

export interface WeatherForGeneration {
  timestamp: string;
  ghi_wm2: number;
  dni_wm2: number;
  dhi_wm2: number;
  temperature_c: number;
}

export async function generateReadings(plant: Plant, weather: WeatherForGeneration): Promise<void> {
  const defaults = resolvePlantDefaults(plant);
  const inverters = await getOrCreateInverters(plant);
  const inverterIds = inverters.map((inv) => inv.id);

  const activeFaults = await getActiveFaultSeverities(inverterIds);
  await maybeStartFaults(inverterIds, new Set(activeFaults.keys()));
  // Re-fetch in case a fault was just started, so this tick reflects it too.
  const faultsAfterStart = await getActiveFaultSeverities(inverterIds);

  const res = await fetch(`${API_BASE}/api/synthetic/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lat: plant.latitude,
      lon: plant.longitude,
      capacity_kw: defaults.capacityKw,
      tilt_degrees: defaults.tiltDegrees,
      azimuth_degrees: defaults.azimuthDegrees,
      timestamp: weather.timestamp,
      ghi_wm2: weather.ghi_wm2,
      dni_wm2: weather.dni_wm2,
      dhi_wm2: weather.dhi_wm2,
      temperature_c: weather.temperature_c,
      temp_coefficient: defaults.tempCoefficient,
      degradation_factor: defaults.degradationFactor,
      inverters: inverters.map((inv) => ({
        id: inv.id,
        base_efficiency_factor: inv.base_efficiency_factor,
        active_fault_severity: faultsAfterStart.get(inv.id) ?? 0,
      })),
    }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Synthetic generation failed (${res.status}): ${body}`);
  }
  const result: GenerationApiResponse = await res.json();

  const rows = result.readings.map((r) => ({
    inverter_id: r.inverter_id,
    recorded_at: weather.timestamp,
    dc_power_kw: r.dc_power_kw,
    ac_power_kw: r.ac_power_kw,
    cell_temp_c: result.cell_temp_c,
    poa_irradiance_wm2: result.poa_irradiance_wm2,
    fault_active: r.fault_active,
    revenue_per_interval: r.ac_power_kw * REVENUE_INTERVAL_HOURS * plant.tariff_per_kwh,
  }));

  const { error } = await supabase
    .from("generation_readings")
    .upsert(rows, { onConflict: "inverter_id,recorded_at", ignoreDuplicates: true });
  if (error) throw error;
}
