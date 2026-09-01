"use client";

import { useEffect } from "react";
import { usePlant } from "@/context/PlantContext";
import { fetchCurrentWeather, storeWeatherReading } from "@/lib/weather";
import { generateReadings } from "@/lib/generation";

const POLL_INTERVAL_MS = 15 * 60 * 1000; // 15 minutes

// No UI -- runs in the background wherever it's mounted. Each tick: fetch
// real weather for the plant's location, store it, then use that SAME
// weather reading to compute and store synthetic per-inverter generation --
// one tick produces one physically consistent weather+generation snapshot,
// rather than two independently-timed fetches that could drift apart.
export function SimulationIngestion() {
  const { plant } = usePlant();

  useEffect(() => {
    if (!plant) return;

    let cancelled = false;

    const tick = async () => {
      try {
        const weather = await fetchCurrentWeather(plant.latitude, plant.longitude);
        if (cancelled) return;
        await storeWeatherReading(plant.id, weather);
        if (cancelled) return;
        await generateReadings(plant, weather);
      } catch (err) {
        console.warn("Simulation ingestion tick failed:", err);
      }
    };

    tick();
    const interval = setInterval(tick, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [plant]);

  return null;
}
