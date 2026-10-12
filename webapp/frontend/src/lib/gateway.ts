import { supabase } from "./supabase";

// The plant's gateway: the device that pushes inverter telemetry. Today it's
// the simulated one (`python -m gateway` in webapp/backend), paired with a
// short-lived code -- see Contract 4 in PRODUCT_PLAN.md.

export const PAIRING_CODE_MINUTES = 15;

export interface Gateway {
  serial: string | null;
  paired_at: string | null;
  last_seen_at: string | null;
}

export async function getGateway(plantId: string): Promise<Gateway | null> {
  const { data, error } = await supabase
    .from("gateways")
    .select("serial, paired_at, last_seen_at")
    .eq("plant_id", plantId)
    .maybeSingle();
  if (error) throw error;
  return data;
}

export async function createPairingCode(plantId: string): Promise<{ code: string; expiresAt: number }> {
  const { data, error } = await supabase.rpc("create_pairing_code", { p_plant_id: plantId });
  if (error) throw error;
  return { code: data as string, expiresAt: Date.now() + PAIRING_CODE_MINUTES * 60 * 1000 };
}
