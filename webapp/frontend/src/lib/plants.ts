import { supabase } from "./supabase";

export interface Plant {
  id: string;
  user_id: string;
  name: string;
  latitude: number;
  longitude: number;
  tariff_per_kwh: number;
  capacity_kw: number | null;
  panel_count: number | null;
  inverter_count: number | null;
  module_type: string | null;
  module_wattage_w: number | null;
  tilt_degrees: number | null;
  azimuth_degrees: number | null;
  commissioning_date: string | null;
  area_sqm: number | null;
  created_at: string;
}

export type NewPlant = Omit<Plant, "id" | "user_id" | "created_at">;

export async function getMyPlant(): Promise<Plant | null> {
  const { data, error } = await supabase.from("plants").select("*").limit(1).maybeSingle();
  if (error) throw error;
  return data;
}

export async function createPlant(config: NewPlant): Promise<Plant> {
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("Not authenticated");

  const { data, error } = await supabase
    .from("plants")
    .insert({ ...config, user_id: user.id })
    .select()
    .single();
  if (error) throw error;
  return data;
}
