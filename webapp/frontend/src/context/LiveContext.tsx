"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { getGateway, type Gateway } from "@/lib/gateway";
import { getPlantStatus, type PlantStatus } from "@/lib/status";
import type { Plant } from "@/lib/plants";

// Live state shared by every plant page: the gateway (Connected/Offline),
// the detector's verdict, and a `version` that ticks when new readings
// arrive over Supabase Realtime, so pages know to refresh their numbers.

const STATUS_REFRESH_MS = 60_000; // also catches a gateway going quiet
const STATUS_MIN_GAP_MS = 10_000;
const VERSION_MIN_GAP_MS = 30_000; // pages refetch at most this often on new readings
const RECENTLY_SEEN_MS = 120_000;

interface LiveValue {
  gateway: Gateway | null;
  gatewayLoaded: boolean;
  connected: boolean;
  status: PlantStatus | null;
  statusError: string | null;
  version: number; // bumps on new readings (throttled) and after re-pairing
  lastReadingAt: string | null;
  reloadGateway: () => void;
}

const LiveContext = createContext<LiveValue | null>(null);

export function LiveProvider({ plant, children }: { plant: Plant; children: React.ReactNode }) {
  const [gateway, setGateway] = useState<Gateway | null>(null);
  const [gatewayLoaded, setGatewayLoaded] = useState(false);
  const [status, setStatus] = useState<PlantStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [lastReadingAt, setLastReadingAt] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [gatewayKey, setGatewayKey] = useState(0);

  const lastStatusAt = useRef(0);
  const lastVersionAt = useRef(0);
  const pendingReading = useRef<string | null>(null);

  const refreshStatus = useCallback(async () => {
    lastStatusAt.current = Date.now();
    try {
      setStatus(await getPlantStatus(plant.id));
      setStatusError(null);
    } catch (e) {
      setStatusError(e instanceof Error ? e.message : "status unavailable");
    }
  }, [plant.id]);

  // Gateway row (re-read after pairing).
  useEffect(() => {
    let cancelled = false;
    getGateway(plant.id)
      .then((g) => {
        if (!cancelled) {
          setGateway(g);
          setGatewayLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) setGatewayLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [plant.id, gatewayKey]);

  // Verdict: now, then every minute.
  useEffect(() => {
    const first = setTimeout(refreshStatus, 0);
    const timer = setInterval(() => {
      setNow(Date.now());
      refreshStatus();
    }, STATUS_REFRESH_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [refreshStatus, gatewayKey]);

  // Realtime: new readings for this plant's inverters, and gateway heartbeats.
  useEffect(() => {
    let channel: ReturnType<typeof supabase.channel> | null = null;
    let cancelled = false;
    supabase
      .from("inverters")
      .select("id")
      .eq("plant_id", plant.id)
      .then(({ data }) => {
        if (cancelled) return;
        const ids = (data ?? []).map((r) => r.id as string);
        channel = supabase.channel(`live-${plant.id}`);
        if (ids.length > 0) {
          channel.on(
            "postgres_changes",
            { event: "INSERT", schema: "public", table: "generation_readings", filter: `inverter_id=in.(${ids.join(",")})` },
            (payload) => {
              pendingReading.current = (payload.new as { recorded_at: string }).recorded_at;
            },
          );
        }
        channel
          .on(
            "postgres_changes",
            { event: "*", schema: "public", table: "gateways", filter: `plant_id=eq.${plant.id}` },
            (payload) => {
              const g = payload.new as Gateway;
              setNow(Date.now());
              setGateway({ serial: g.serial, paired_at: g.paired_at, last_seen_at: g.last_seen_at });
            },
          )
          .subscribe();
      });

    // Batch: a catch-up can send thousands of inserts in a few seconds.
    const flush = setInterval(() => {
      const reading = pendingReading.current;
      if (!reading) return;
      pendingReading.current = null;
      setLastReadingAt(reading);
      setNow(Date.now());
      if (Date.now() - lastStatusAt.current > STATUS_MIN_GAP_MS) refreshStatus();
      if (Date.now() - lastVersionAt.current > VERSION_MIN_GAP_MS) {
        lastVersionAt.current = Date.now();
        setVersion((v) => v + 1);
      }
    }, 1000);

    return () => {
      cancelled = true;
      clearInterval(flush);
      if (channel) supabase.removeChannel(channel);
    };
  }, [plant.id, gatewayKey, refreshStatus]);

  const reloadGateway = useCallback(() => {
    setGatewayKey((k) => k + 1);
    setVersion((v) => v + 1);
  }, []);

  const seenRecently = gateway?.last_seen_at != null && now - new Date(gateway.last_seen_at).getTime() < RECENTLY_SEEN_MS;
  const connected = Boolean(status?.gateway?.connected) || seenRecently;

  return (
    <LiveContext.Provider
      value={{ gateway, gatewayLoaded, connected, status, statusError, version, lastReadingAt, reloadGateway }}
    >
      {children}
    </LiveContext.Provider>
  );
}

export function useLive(): LiveValue {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error("useLive must be used within LiveProvider");
  return ctx;
}
