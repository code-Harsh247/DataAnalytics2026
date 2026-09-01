"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { usePlant } from "@/context/PlantContext";

// Guards the (dashboard) route group: requires a session AND a configured
// plant. A logged-in user with no plant yet is sent to /setup-plant first --
// the dashboard shouldn't be the first thing they see with nothing set up.
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { session, loading: authLoading } = useAuth();
  const { plant, loading: plantLoading } = usePlant();
  const router = useRouter();

  useEffect(() => {
    if (authLoading) return;
    if (!session) {
      router.replace("/login");
      return;
    }
    if (!plantLoading && !plant) {
      router.replace("/setup-plant");
    }
  }, [authLoading, session, plantLoading, plant, router]);

  if (authLoading || !session || plantLoading || !plant) {
    return <div className="p-6 text-gray-500">Loading…</div>;
  }

  return <>{children}</>;
}
