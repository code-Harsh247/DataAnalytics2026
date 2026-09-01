import { supabase } from "./supabase";

export interface WeatherPoint {
  recorded_at: string;
  temperature_c: number | null;
  cloud_cover_pct: number | null;
  ghi_wm2: number | null;
  clearsky_index: number | null;
}

export async function getWeatherHistory(plantId: string, limit = 200): Promise<WeatherPoint[]> {
  const { data, error } = await supabase
    .from("weather_readings")
    .select("recorded_at, temperature_c, cloud_cover_pct, ghi_wm2, clearsky_index")
    .eq("plant_id", plantId)
    .order("recorded_at", { ascending: true })
    .limit(limit);
  if (error) throw error;
  return data ?? [];
}

export interface GenerationPoint {
  recorded_at: string;
  inverter_id: string;
  ac_power_kw: number;
  dc_power_kw: number;
  fault_active: boolean;
  revenue_per_interval: number | null;
}

async function getPlantInverterIds(plantId: string): Promise<string[]> {
  const { data, error } = await supabase.from("inverters").select("id").eq("plant_id", plantId);
  if (error) throw error;
  return (data ?? []).map((i) => i.id as string);
}

export async function getGenerationHistory(plantId: string, limit = 800): Promise<GenerationPoint[]> {
  // generation_readings has no plant_id directly -- go via inverters.
  const inverterIds = await getPlantInverterIds(plantId);
  if (inverterIds.length === 0) return [];

  const { data, error } = await supabase
    .from("generation_readings")
    .select("recorded_at, inverter_id, ac_power_kw, dc_power_kw, fault_active, revenue_per_interval")
    .in("inverter_id", inverterIds)
    .order("recorded_at", { ascending: true })
    .limit(limit);
  if (error) throw error;
  return data ?? [];
}

export interface InverterStatus {
  id: string;
  label: string;
  latest_ac_power_kw: number | null;
  latest_fault_active: boolean;
  latest_recorded_at: string | null;
}

export async function getInverterStatuses(plantId: string): Promise<InverterStatus[]> {
  const { data: inverters, error: invError } = await supabase
    .from("inverters")
    .select("id, label")
    .eq("plant_id", plantId)
    .order("label", { ascending: true });
  if (invError) throw invError;
  if (!inverters || inverters.length === 0) return [];

  const inverterIds = inverters.map((i) => i.id as string);
  const { data: readings, error: readError } = await supabase
    .from("generation_readings")
    .select("inverter_id, ac_power_kw, fault_active, recorded_at")
    .in("inverter_id", inverterIds)
    .order("recorded_at", { ascending: false })
    .limit(inverterIds.length * 5); // small buffer, find latest per inverter client-side
  if (readError) throw readError;

  const latestByInverter = new Map<
    string,
    { ac_power_kw: number; fault_active: boolean; recorded_at: string }
  >();
  for (const r of readings ?? []) {
    if (!latestByInverter.has(r.inverter_id)) {
      latestByInverter.set(r.inverter_id, r);
    }
  }

  return inverters.map((inv) => {
    const latest = latestByInverter.get(inv.id);
    return {
      id: inv.id,
      label: inv.label,
      latest_ac_power_kw: latest?.ac_power_kw ?? null,
      latest_fault_active: latest?.fault_active ?? false,
      latest_recorded_at: latest?.recorded_at ?? null,
    };
  });
}

export interface PlantTotals {
  total_energy_kwh: number;
  total_revenue: number;
  reading_count: number;
}

const INTERVAL_HOURS = 0.25;

export async function getPlantTotals(plantId: string): Promise<PlantTotals> {
  const inverterIds = await getPlantInverterIds(plantId);
  if (inverterIds.length === 0) return { total_energy_kwh: 0, total_revenue: 0, reading_count: 0 };

  const { data, error } = await supabase
    .from("generation_readings")
    .select("ac_power_kw, revenue_per_interval")
    .in("inverter_id", inverterIds);
  if (error) throw error;

  const rows = data ?? [];
  const total_energy_kwh = rows.reduce((sum, r) => sum + (r.ac_power_kw ?? 0) * INTERVAL_HOURS, 0);
  const total_revenue = rows.reduce((sum, r) => sum + (r.revenue_per_interval ?? 0), 0);
  return { total_energy_kwh, total_revenue, reading_count: rows.length };
}
