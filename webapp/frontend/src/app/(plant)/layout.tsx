import { AuthGate } from "@/components/AuthGate";
import { PlantShell } from "@/components/PlantShell";

// Every plant page: requires a session and a configured plant (AuthGate),
// then the shared nav, header and live data (PlantShell).
export default function PlantLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <PlantShell>{children}</PlantShell>
    </AuthGate>
  );
}
