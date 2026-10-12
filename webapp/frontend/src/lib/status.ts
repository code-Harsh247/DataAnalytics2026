import { backendFetch } from "./backend";

// Client for GET /api/plants/{id}/status -- the live verdict (Contract 6b).
// Comes from the detector, never from the simulator's fault labels.

export type InverterState = "ok" | "underperforming" | "offline" | "learning" | "no_data";

export interface InverterVerdict {
  label: string;
  state: InverterState;
  shortfall_pct?: number | null; // median shortfall vs expected over the latest readings
  since?: string | null; // start of the current underperforming run
  est_kwh_lost_24h?: number;
  est_revenue_lost_24h?: number;
  latest_at?: string | null;
}

export interface PlantStatus {
  as_of: string;
  timezone?: string;
  model: string;
  gateway: { connected: boolean; serial: string | null; last_seen_at: string | null } | null;
  inverters: InverterVerdict[];
}

export function getPlantStatus(plantId: string): Promise<PlantStatus> {
  return backendFetch<PlantStatus>(`/api/plants/${plantId}/status`);
}
