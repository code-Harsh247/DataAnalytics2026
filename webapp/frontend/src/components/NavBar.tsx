"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Overview" },
  { href: "/maintenance", label: "Maintenance" },
  { href: "/forecast", label: "Forecast" },
];

export function NavBar() {
  const pathname = usePathname();

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
            className={`text-sm px-3 py-1.5 rounded shrink-0 ${
              active ? "bg-blue-100 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
