"use client";

import { useEffect, useState } from "react";
import { createPairingCode, getGateway } from "@/lib/gateway";

const POLL_MS = 1000; // also drives the countdown; the pairing check is one tiny query

// "Connect your inverter": shows a short-lived pairing code and waits for a
// gateway to claim it. Today the gateway is the simulated one in
// webapp/backend (`python -m gateway`); a real data logger would pair the same way.
export function ConnectDevice({ plantId, onPaired }: { plantId: string; onPaired: () => void }) {
  const [pairing, setPairing] = useState<{ code: string; expiresAt: number; requestedAt: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const requestCode = async () => {
    setBusy(true);
    setError(null);
    try {
      const { code, expiresAt } = await createPairingCode(plantId);
      setNow(Date.now());
      setPairing({ code, expiresAt, requestedAt: Date.now() });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't create a pairing code.");
    } finally {
      setBusy(false);
    }
  };

  // While a code is showing: tick the countdown and watch for the gateway to pair.
  useEffect(() => {
    if (!pairing) return;
    const timer = setInterval(async () => {
      setNow(Date.now());
      try {
        const gateway = await getGateway(plantId);
        if (gateway?.paired_at && new Date(gateway.paired_at).getTime() >= pairing.requestedAt - 5000) {
          onPaired();
        }
      } catch {
        // transient; the next poll retries
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [pairing, plantId, onPaired]);

  const secondsLeft = pairing ? Math.max(0, Math.round((pairing.expiresAt - now) / 1000)) : 0;
  const expired = pairing !== null && secondsLeft === 0;

  return (
    <div className="bg-white rounded-lg border shadow-sm p-5 space-y-3">
      <div>
        <div className="text-sm font-medium text-gray-800">Connect your inverter</div>
        <p className="text-xs text-gray-500 mt-1 max-w-2xl">
          Readings come from a gateway: the box next to your inverters that sends their output to
          the cloud. This demo uses a <span className="font-medium">simulated gateway</span> that
          generates telemetry from real weather at your plant&apos;s location.
        </p>
      </div>

      {!pairing || expired ? (
        <div className="space-y-2">
          {expired && <p className="text-xs text-amber-700">That code expired. Get a new one.</p>}
          <button
            type="button"
            onClick={requestCode}
            disabled={busy}
            className="bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? "Creating code…" : "Get pairing code"}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="font-mono text-3xl font-semibold tracking-[0.3em] text-gray-900">{pairing.code}</span>
            <span className="text-xs text-gray-500">
              expires in {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}
            </span>
          </div>
          <div className="text-xs text-gray-600 space-y-1">
            <div>On the gateway (from <code>webapp/backend</code>):</div>
            <pre className="bg-gray-900 text-gray-100 rounded px-3 py-2 overflow-x-auto">
{`python -m gateway pair ${pairing.code}
python -m gateway run`}
            </pre>
          </div>
          <p className="text-xs text-gray-500 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            Waiting for the gateway to connect…
          </p>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
