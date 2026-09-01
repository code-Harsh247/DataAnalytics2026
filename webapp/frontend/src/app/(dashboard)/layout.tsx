import { SimulationProvider } from "@/context/SimulationContext";
import { TimelineScrubber } from "@/components/TimelineScrubber";
import { NavBar } from "@/components/NavBar";
import { AuthGate } from "@/components/AuthGate";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <SimulationProvider>
        <NavBar />
        <TimelineScrubber />
        <main className="flex-1">{children}</main>
      </SimulationProvider>
    </AuthGate>
  );
}
