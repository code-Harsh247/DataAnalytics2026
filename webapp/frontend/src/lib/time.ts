// "12 s ago", "4 min ago", "3 h ago" -- for last-seen badges and verdicts.
export function formatAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "never";
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds} s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

// Plant-local clock time isn't known (only coordinates), so show UTC, like the charts.
export function formatUtcTime(iso: string): string {
  return new Date(iso).toISOString().slice(11, 16) + " UTC";
}
