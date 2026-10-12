"use client";

import { useEffect, useState } from "react";
import type { Gateway } from "@/lib/gateway";
import { formatAgo } from "@/lib/time";

// Connected / Offline pill for the plant's gateway. `connected` comes from
// the status endpoint, which knows the reading interval; last-seen ticks live.
export function DeviceBadge({ gateway, connected }: { gateway: Gateway; connected: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full font-medium ${
          connected ? "bg-green-100 text-green-700" : "bg-gray-200 text-gray-600"
        }`}
      >
        <span className={`w-2 h-2 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-gray-400"}`} />
        {connected ? "Connected" : "Offline"}
      </span>
      <span className="text-gray-500">last seen {formatAgo(gateway.last_seen_at, now)}</span>
      <span className="text-gray-400">·</span>
      <span className="font-mono text-gray-500">{gateway.serial ?? "gateway"}</span>
      <span className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
        Simulated device
      </span>
    </div>
  );
}
