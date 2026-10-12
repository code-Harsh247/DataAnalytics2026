"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useLive } from "@/context/LiveContext";

const links = [
  { href: "/", label: "Overview" },
  { href: "/production", label: "Production" },
  { href: "/forecast", label: "Forecast" },
  { href: "/health", label: "Health" },
  { href: "/finance", label: "Finance" },
];

export function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const { status } = useLive();
  const problems = (status?.inverters ?? []).filter((i) => i.state === "underperforming").length;

  const handleSignOut = async () => {
    await signOut();
    router.replace("/login");
  };

  return (
    <nav className="flex items-center gap-1 px-4 py-2 border-b bg-white overflow-x-auto whitespace-nowrap">
      <span className="hidden sm:inline text-sm font-semibold text-gray-900 mr-4 shrink-0">
        Solar Plant Manager
      </span>
      {links.map((link) => {
        const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`relative text-sm px-3 py-1.5 rounded shrink-0 ${
              active ? "bg-blue-100 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            {link.label}
            {link.href === "/health" && problems > 0 && (
              <span
                className="absolute top-1 right-0.5 w-2 h-2 rounded-full bg-red-500"
                title={`${problems} inverter${problems === 1 ? "" : "s"} under-producing`}
              />
            )}
          </Link>
        );
      })}
      <div className="flex-1" />
      {user && <span className="hidden md:inline text-xs text-gray-400 mr-3 shrink-0">{user.email}</span>}
      <button
        type="button"
        onClick={handleSignOut}
        className="text-sm px-3 py-1.5 rounded text-gray-600 hover:bg-gray-100 shrink-0"
      >
        Sign out
      </button>
    </nav>
  );
}
