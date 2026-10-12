"use client";

import { useState } from "react";
import { usePlant } from "@/context/PlantContext";
import { LiveProvider, useLive } from "@/context/LiveContext";
import { NavBar } from "@/components/NavBar";
import { DeviceBadge } from "@/components/DeviceBadge";
import { ConnectDevice } from "@/components/ConnectDevice";
import { resolvePlantDefaults } from "@/lib/generation";
import type { Plant } from "@/lib/plants";

// Frame around every plant page: nav, plant header with the gateway's
// status, and the pairing card while no gateway is connected.
export function PlantShell({ children }: { children: React.ReactNode }) {
  const { plant } = usePlant();
  if (!plant) return null; // AuthGate guarantees one; this keeps TypeScript honest
  return (
    <LiveProvider plant={plant}>
      <NavBar />
      <PlantHeader plant={plant} />
      <main className="flex-1">{children}</main>
    </LiveProvider>
  );
}

function PlantHeader({ plant }: { plant: Plant }) {
  const { gateway, gatewayLoaded, connected, reloadGateway } = useLive();
  const [replacing, setReplacing] = useState(false);
  const { capacityKw, inverterCount } = resolvePlantDefaults(plant);
  const paired = Boolean(gateway?.paired_at);

  return (
    <div className="max-w-6xl w-full mx-auto px-6 pt-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">{plant.name}</h1>
          <p className="text-sm text-gray-500">
            {capacityKw.toFixed(1)} kWp · {inverterCount} inverters · {plant.latitude.toFixed(2)},{" "}
            {plant.longitude.toFixed(2)} · tariff {plant.tariff_per_kwh}/kWh
          </p>
        </div>
        {paired && gateway && (
          <div className="flex flex-col items-end gap-1">
            <DeviceBadge gateway={gateway} connected={connected} />
            <button
              type="button"
              onClick={() => setReplacing((v) => !v)}
              className="text-xs text-blue-600 hover:underline"
            >
              {replacing ? "Cancel" : "Replace gateway"}
            </button>
          </div>
        )}
      </div>
      {gatewayLoaded && (!paired || replacing) && (
        <ConnectDevice
          plantId={plant.id}
          onPaired={() => {
            setReplacing(false);
            reloadGateway();
          }}
        />
      )}
    </div>
  );
}
