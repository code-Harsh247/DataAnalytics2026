import type { Plant } from "./plants";

// The browser no longer generates readings: a gateway (today the simulated
// one, `python -m gateway` in webapp/backend) pushes telemetry straight to
// Supabase -- see "Working MVP" in PRODUCT_PLAN.md. What's left here is how
// the plant's optional setup fields resolve to the physics inputs, mirrored
// by resolve_plant_defaults() in webapp/backend/app/seed_supabase.py.

const DEFAULT_INVERTER_COUNT = 4;
const DEFAULT_CAPACITY_KW = 5.0;
const TYPICAL_PANEL_DENSITY_W_PER_SQM = 150; // installed-area density, not bare panel density

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
