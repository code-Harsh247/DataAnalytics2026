"use client";

import { useEffect } from "react";
import { usePlant } from "@/context/PlantContext";
import { fetchCurrentWeather, storeWeatherReading } from "@/lib/weather";

const POLL_INTERVAL_MS = 15 * 60 * 1000; // 15 minutes

// No UI -- runs in the background wherever it's mounted, ingesting real
// weather for the current plant while the app is open. Real
// scheduled/background ingestion (independent of a browser tab being open)
// is deliberately out of scope for this step -- see PRODUCT_PLAN.md.
export function WeatherIngestion() {
  const { plant } = usePlant();

  useEffect(() => {
    if (!plant) return;

    let cancelled = false;

    const ingest = async () => {
      try {
        const weather = await fetchCurrentWeather(plant.latitude, plant.longitude);
        if (cancelled) return;
        await storeWeatherReading(plant.id, weather);
      } catch (err) {
        console.warn("Weather ingestion failed:", err);
      }
    };

    ingest();
    const interval = setInterval(ingest, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [plant]);

  return null;
}
