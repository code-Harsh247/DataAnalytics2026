"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
import { getMyPlant, type Plant } from "@/lib/plants";

interface PlantContextValue {
  plant: Plant | null;
  loading: boolean;
  refetch: () => Promise<void>;
}

const PlantContext = createContext<PlantContextValue | null>(null);

export function PlantProvider({ children }: { children: React.ReactNode }) {
  const { session, loading: authLoading } = useAuth();
  const [plant, setPlant] = useState<Plant | null>(null);
  const [loading, setLoading] = useState(true);

  // Keyed on the user id, not the session object: Supabase hands out a new
  // session object on every token refresh (~hourly), and refetching on that
  // flips `loading`, which unmounts the whole dashboard and wipes its state.
  const userId = session?.user.id ?? null;

  const fetchPlant = useCallback(async () => {
    if (!userId) {
      setPlant(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const p = await getMyPlant();
      setPlant(p);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    if (authLoading) return;
    fetchPlant();
  }, [authLoading, fetchPlant]);

  return (
    <PlantContext.Provider value={{ plant, loading, refetch: fetchPlant }}>
      {children}
    </PlantContext.Provider>
  );
}

export function usePlant(): PlantContextValue {
  const ctx = useContext(PlantContext);
  if (!ctx) throw new Error("usePlant must be used within PlantProvider");
  return ctx;
}
