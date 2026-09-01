"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

interface SimulationContextValue {
  plantId: number;
  dates: string[];
  currentIndex: number;
  currentDate: string | null;
  isPlaying: boolean;
  isLoading: boolean;
  error: string | null;
  setIndex: (i: number) => void;
  play: () => void;
  pause: () => void;
}

const SimulationContext = createContext<SimulationContextValue | null>(null);

// Single-plant scope for v1 (see PRODUCT_PLAN.md) — Plant 2 has the real
// findings (flagged inverters, worsening-trend early warning) worth showing.
const PLANT_ID = 2;
const PLAY_INTERVAL_MS = 1000;

function parseISODate(s: string): { y: number; m: number; d: number } {
  const [y, m, d] = s.split("-").map(Number);
  return { y, m, d };
}

// Pure UTC arithmetic throughout — mixing local-time `Date` construction
// (e.g. `new Date(start + "T00:00:00")`) with `.toISOString()` shifts dates
// by the browser's UTC offset (e.g. IST) and silently drops/duplicates a day.
function enumerateDates(start: string, end: string): string[] {
  const s = parseISODate(start);
  const e = parseISODate(end);
  const dates: string[] = [];
  let cur = Date.UTC(s.y, s.m - 1, s.d);
  const endMs = Date.UTC(e.y, e.m - 1, e.d);
  while (cur <= endMs) {
    dates.push(new Date(cur).toISOString().slice(0, 10));
    cur += 24 * 60 * 60 * 1000;
  }
  return dates;
}

export function SimulationProvider({ children }: { children: React.ReactNode }) {
  const [dates, setDates] = useState<string[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api
      .getTimeline(PLANT_ID)
      .then((tl) => {
        const d = enumerateDates(tl.start, tl.end);
        setDates(d);
        setCurrentIndex(d.length - 1);
        setIsLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setIsLoading(false);
      });
  }, []);

  useEffect(() => {
    if (isPlaying && dates.length > 0) {
      intervalRef.current = setInterval(() => {
        setCurrentIndex((i) => {
          if (i >= dates.length - 1) {
            setIsPlaying(false);
            return i;
          }
          return i + 1;
        });
      }, PLAY_INTERVAL_MS);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, dates.length]);

  const value: SimulationContextValue = {
    plantId: PLANT_ID,
    dates,
    currentIndex,
    currentDate: dates[currentIndex] ?? null,
    isPlaying,
    isLoading,
    error,
    setIndex: setCurrentIndex,
    play: () => setIsPlaying(true),
    pause: () => setIsPlaying(false),
  };

  return <SimulationContext.Provider value={value}>{children}</SimulationContext.Provider>;
}

export function useSimulation(): SimulationContextValue {
  const ctx = useContext(SimulationContext);
  if (!ctx) throw new Error("useSimulation must be used within SimulationProvider");
  return ctx;
}
