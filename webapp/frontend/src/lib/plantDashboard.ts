import { supabase } from "./supabase";

// Supabase caps every response at 1000 rows, so anything that can grow past
// that (a seeded month is ~12k generation rows) has to be read in pages.
const PAGE_SIZE = 1000;
const HISTORY_DAYS = 7; // chart window; totals still cover all readings

type PageQuery<T> = (from: number, to: number) => PromiseLike<{ data: T[] | null; error: unknown }>;

async function fetchAllPages<T>(query: PageQuery<T>): Promise<T[]> {
  const rows: T[] = [];
  for (let from = 0; ; from += PAGE_SIZE) {
    const { data, error } = await query(from, from + PAGE_SIZE - 1);
    if (error) throw error;
    rows.push(...(data ?? []));
    if (!data || data.length < PAGE_SIZE) return rows;
  }
}

function historyStartIso(): string {
  return new Date(Date.now() - HISTORY_DAYS * 24 * 60 * 60 * 1000).toISOString();
}

export interface WeatherPoint {
  recorded_at: string;
  temperature_c: number | null;
  cloud_cover_pct: number | null;
  ghi_wm2: number | null;
  clearsky_index: number | null;
}

export async function getWeatherHistory(plantId: string): Promise<WeatherPoint[]> {
  const since = historyStartIso();
  return fetchAllPages<WeatherPoint>((from, to) =>
    supabase
      .from("weather_readings")
      .select("recorded_at, temperature_c, cloud_cover_pct, ghi_wm2, clearsky_index")
      .eq("plant_id", plantId)
      .gte("recorded_at", since)
      .order("recorded_at", { ascending: true })
      .range(from, to),
  );
}

// fault_active / fault_severity are deliberately never read here: they're
// the simulator's ground truth, for scoring the detector only. Inverter
// status comes from the detector (lib/status.ts).
export interface GenerationPoint {
  recorded_at: string;
  inverter_id: string;
  ac_power_kw: number;
  dc_power_kw: number;
  energy_kwh: number | null;
  revenue_per_interval: number | null;
}

async function getPlantInverterIds(plantId: string): Promise<string[]> {
  const { data, error } = await supabase.from("inverters").select("id").eq("plant_id", plantId);
  if (error) throw error;
  return (data ?? []).map((i) => i.id as string);
}

export async function getGenerationHistory(plantId: string): Promise<GenerationPoint[]> {
  // generation_readings has no plant_id directly -- go via inverters.
  const inverterIds = await getPlantInverterIds(plantId);
  if (inverterIds.length === 0) return [];

  const since = historyStartIso();
  return fetchAllPages<GenerationPoint>((from, to) =>
    supabase
      .from("generation_readings")
      .select("recorded_at, inverter_id, ac_power_kw, dc_power_kw, energy_kwh, revenue_per_interval")
      .in("inverter_id", inverterIds)
      .gte("recorded_at", since)
      .order("recorded_at", { ascending: true })
      .order("inverter_id", { ascending: true })
      .range(from, to),
  );
}

export interface InverterLatest {
  id: string;
  label: string;
  latest_ac_power_kw: number | null;
  latest_recorded_at: string | null;
}

export async function getInverterLatest(plantId: string): Promise<InverterLatest[]> {
  const { data: inverters, error: invError } = await supabase
    .from("inverters")
    .select("id, label")
    .eq("plant_id", plantId);
  if (invError) throw invError;
  if (!inverters || inverters.length === 0) return [];
  // Numeric order: INV-10 after INV-9, not after INV-1.
  inverters.sort((a, b) => Number(a.label.split("-").pop()) - Number(b.label.split("-").pop()));

  const inverterIds = inverters.map((i) => i.id as string);
  const { data: readings, error: readError } = await supabase
    .from("generation_readings")
    .select("inverter_id, ac_power_kw, recorded_at")
    .in("inverter_id", inverterIds)
    .order("recorded_at", { ascending: false })
    .limit(inverterIds.length * 5); // small buffer, find latest per inverter client-side
  if (readError) throw readError;

  const latestByInverter = new Map<string, { ac_power_kw: number; recorded_at: string }>();
  for (const r of readings ?? []) {
    if (!latestByInverter.has(r.inverter_id)) latestByInverter.set(r.inverter_id, r);
  }

  return inverters.map((inv) => {
    const latest = latestByInverter.get(inv.id);
    return {
      id: inv.id,
      label: inv.label,
      latest_ac_power_kw: latest?.ac_power_kw ?? null,
      latest_recorded_at: latest?.recorded_at ?? null,
    };
  });
}

export interface PlantTotals {
  total_energy_kwh: number;
  total_revenue: number;
  reading_count: number;
}

// Summed in SQL (plant_totals, 005_devices.sql) rather than paging every
// reading into the browser.
export async function getPlantTotals(plantId: string): Promise<PlantTotals> {
  const { data, error } = await supabase.rpc("plant_totals", { p_plant_id: plantId });
  if (error) throw error;
  return data as PlantTotals;
}

// Energy one reading stands for. Rows from before energy_kwh existed were
// 15-minute readings.
export function readingEnergyKwh(r: { energy_kwh: number | null; ac_power_kw: number | null }): number {
  return r.energy_kwh ?? (r.ac_power_kw ?? 0) * 0.25;
}
