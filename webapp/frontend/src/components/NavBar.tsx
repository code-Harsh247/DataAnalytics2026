"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

// The product is the user's own plant. The Plant 1/2 historical demo (the
// original Kaggle coursework) is kept, but out of the way: one quiet link
// from the plant page, with its own section nav once you're in it.
const demoLinks = [
  { href: "/", label: "Overview" },
  { href: "/maintenance", label: "Maintenance" },
  { href: "/forecast", label: "Forecast" },
];

function linkClass(active: boolean): string {
  return `text-sm px-3 py-1.5 rounded shrink-0 ${
    active ? "bg-blue-100 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-100"
  }`;
}

export function NavBar({ section = "plant" }: { section?: "plant" | "demo" }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();

  const handleSignOut = async () => {
    await signOut();
    router.replace("/login");
  };

  return (
    <nav className="flex items-center gap-1 px-4 py-2 border-b bg-white overflow-x-auto whitespace-nowrap">
      <span className="hidden sm:inline text-sm font-semibold text-gray-900 mr-4 shrink-0">
        Solar Plant Manager
      </span>
      <Link href="/setup-plant" className={linkClass(section === "plant")}>
        My plant
      </Link>
      {section === "demo" && (
        <>
          <span className="text-xs text-gray-400 ml-3 mr-1 pl-3 border-l shrink-0">Historical demo (Kaggle data):</span>
          {demoLinks.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link key={link.href} href={link.href} className={linkClass(active)}>
                {link.label}
              </Link>
            );
          })}
        </>
      )}
      <div className="flex-1" />
      {section === "plant" && (
        <Link href="/" className="text-xs text-gray-400 hover:text-gray-600 mr-3 shrink-0">
          Historical demo
        </Link>
      )}
      {user && (
        <span className="hidden md:inline text-xs text-gray-400 mr-3 shrink-0">{user.email}</span>
      )}
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
