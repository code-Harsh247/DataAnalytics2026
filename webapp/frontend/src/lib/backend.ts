import { supabase } from "./supabase";

// Shared plumbing for the FastAPI backend's plant-scoped endpoints
// (Contract 6 in PRODUCT_PLAN.md): they read Supabase as the signed-in user,
// so every request carries the user's access token.

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// FastAPI returns `detail` as a string for our own errors and as a list of
// validation errors for 422.
function describeError(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(-1)[0] ?? "field"}: ${d.msg ?? "invalid"}`)
      .join("; ");
  }
  return `Request failed (HTTP ${status})`;
}

export async function backendFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Not signed in.");

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(describeError(res.status, body));
  }
  return res.json() as Promise<T>;
}
