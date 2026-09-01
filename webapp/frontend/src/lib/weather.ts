import { supabase } from "./supabase";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface CurrentWeather {
  timestamp: string;
  temperature_c: number;
  cloud_cover_pct: number;
  ghi_wm2: number;
  dni_wm2: number;
  dhi_wm2: number;
  clearsky_ghi_wm2: number;
  clearsky_index: number | null;
}

export async function fetchCurrentWeather(lat: number, lon: number): Promise<CurrentWeather> {
  const res = await fetch(`${API_BASE}/api/weather/current?lat=${lat}&lon=${lon}`);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Weather fetch failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<CurrentWeather>;
}

export async function storeWeatherReading(plantId: string, weather: CurrentWeather): Promise<void> {
  const { error } = await supabase
    .from("weather_readings")
    .upsert(
      {
        plant_id: plantId,
        recorded_at: weather.timestamp,
        temperature_c: weather.temperature_c,
        cloud_cover_pct: weather.cloud_cover_pct,
        ghi_wm2: weather.ghi_wm2,
        dni_wm2: weather.dni_wm2,
        dhi_wm2: weather.dhi_wm2,
        clearsky_ghi_wm2: weather.clearsky_ghi_wm2,
        clearsky_index: weather.clearsky_index,
      },
      { onConflict: "plant_id,recorded_at", ignoreDuplicates: true },
    );
  if (error) throw error;
}
