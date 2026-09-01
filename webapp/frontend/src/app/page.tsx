"use client";

import { useEffect, useState } from "react";
import { useSimulation } from "@/context/SimulationContext";
import { api, type Overview } from "@/lib/api";

// Temporary placeholder proving the data layer (context -> scrubber -> API)
// works end-to-end. Replaced by the real Command Center page in Phase 5.
export default function Home() {
  const { plantId, currentDate } = useSimulation();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentDate) return;
    setError(null);
    api
      .getOverview(plantId, currentDate)
      .then(setOverview)
      .catch((e: Error) => setError(e.message));
  }, [plantId, currentDate]);

  if (error) {
    return <p className="p-4 text-red-600">Error loading overview: {error}</p>;
  }
  if (!overview) {
    return <p className="p-4 text-gray-500">Loading overview…</p>;
  }

  return (
    <div className="p-4">
      <p className="text-sm text-gray-500 mb-2">
        Phase 4 wiring check — real Command Center UI comes in Phase 5.
      </p>
      <pre className="text-xs bg-white border rounded p-3 overflow-auto">
        {JSON.stringify(overview, null, 2)}
      </pre>
    </div>
  );
}
