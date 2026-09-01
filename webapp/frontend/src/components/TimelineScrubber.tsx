"use client";

import { useSimulation } from "@/context/SimulationContext";

export function TimelineScrubber() {
  const { dates, currentIndex, currentDate, isPlaying, isLoading, error, setIndex, play, pause } =
    useSimulation();

  if (isLoading) {
    return <div className="px-4 py-3 text-sm text-gray-500 border-b bg-white">Loading timeline…</div>;
  }
  if (error) {
    return (
      <div className="px-4 py-3 text-sm text-red-600 border-b bg-white">
        Failed to load timeline: {error}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-4 px-4 py-3 border-b bg-white">
      <button
        type="button"
        onClick={isPlaying ? pause : play}
        disabled={currentIndex >= dates.length - 1 && !isPlaying}
        className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {isPlaying ? "Pause" : "Play"}
      </button>
      <input
        type="range"
        min={0}
        max={Math.max(dates.length - 1, 0)}
        value={currentIndex}
        onChange={(e) => setIndex(Number(e.target.value))}
        className="flex-1 accent-blue-600"
      />
      <span className="text-sm font-mono w-28 text-right text-gray-700">{currentDate ?? "—"}</span>
    </div>
  );
}
