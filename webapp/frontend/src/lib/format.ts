// Number and time formatting shared by the plant pages. Times are shown in
// the plant's own time zone (from the backend), not the viewer's.

export function kwh(x: number | null | undefined, digits = 1): string {
  if (x == null) return "—";
  if (Math.abs(x) >= 1000) return `${(x / 1000).toFixed(2)} MWh`;
  return `${x.toFixed(digits)} kWh`;
}

export function money(x: number | null | undefined, digits = 0): string {
  if (x == null) return "—";
  return x.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function pct(x: number | null | undefined, digits = 0): string {
  return x == null ? "—" : `${(x * 100).toFixed(digits)}%`;
}

export function co2(kg: number | null | undefined): string {
  if (kg == null) return "—";
  return kg >= 1000 ? `${(kg / 1000).toFixed(2)} t` : `${kg.toFixed(0)} kg`;
}

export function localTime(iso: string, tz: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit" });
}

export function localDateTime(iso: string, tz: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    timeZone: tz, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

// "2026-10-12" -> "Mon 12 Oct"
export function dayLabel(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("en-GB", {
    timeZone: "UTC", weekday: "short", day: "numeric", month: "short",
  });
}

// "2026-10" -> "Oct 2026"
export function monthLabel(month: string): string {
  return new Date(`${month}-15T12:00:00Z`).toLocaleDateString("en-GB", { timeZone: "UTC", month: "short", year: "numeric" });
}
