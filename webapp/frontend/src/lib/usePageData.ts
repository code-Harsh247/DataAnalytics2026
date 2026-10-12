"use client";

import { useCallback, useEffect, useState } from "react";
import { usePlant } from "@/context/PlantContext";
import { useLive } from "@/context/LiveContext";

// Loads a page's payload for the current plant, and reloads it (keeping the
// old numbers on screen meanwhile) whenever new readings arrive.
export function usePageData<T>(fetcher: (plantId: string) => Promise<T>) {
  const { plant } = usePlant();
  const { version } = useLive();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const plantId = plant?.id;

  useEffect(() => {
    if (!plantId) return;
    let cancelled = false;
    const start = setTimeout(() => setRefreshing(true), 0);
    fetcher(plantId)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setRefreshing(false);
      });
    return () => {
      cancelled = true;
      clearTimeout(start);
    };
  }, [plantId, version, fetcher, reloadKey]);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);
  return { data, error, refreshing, reload };
}
