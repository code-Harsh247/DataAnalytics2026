"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { usePlant } from "@/context/PlantContext";
import { createPlant, type NewPlant } from "@/lib/plants";

const MODULE_TYPES = ["Monocrystalline", "Polycrystalline", "Thin-film", "Other"];

const emptyForm = {
  name: "",
  latitude: "",
  longitude: "",
  tariff_per_kwh: "",
  capacity_kw: "",
  panel_count: "",
  inverter_count: "",
  module_type: "",
  module_wattage_w: "",
  tilt_degrees: "",
  azimuth_degrees: "",
  commissioning_date: "",
  area_sqm: "",
};

function toNumberOrNull(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

export default function SetupPlantPage() {
  const { session, loading: authLoading } = useAuth();
  const { plant, loading: plantLoading, refetch } = usePlant();
  const router = useRouter();

  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [justCreated, setJustCreated] = useState(false);

  useEffect(() => {
    if (!authLoading && !session) router.replace("/login");
  }, [authLoading, session, router]);

  // Setup is only for a first plant; once there is one, its pages are the home.
  useEffect(() => {
    if (!plantLoading && plant) router.replace("/");
  }, [plantLoading, plant, router]);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.name.trim()) return setError("Plant name is required.");
    const lat = toNumberOrNull(form.latitude);
    const lon = toNumberOrNull(form.longitude);
    const tariff = toNumberOrNull(form.tariff_per_kwh);
    if (lat === null || lat < -90 || lat > 90) return setError("Latitude must be between -90 and 90.");
    if (lon === null || lon < -180 || lon > 180) return setError("Longitude must be between -180 and 180.");
    if (tariff === null || tariff < 0) return setError("Enter a valid tariff.");

    const payload: NewPlant = {
      name: form.name.trim(),
      latitude: lat,
      longitude: lon,
      tariff_per_kwh: tariff,
      capacity_kw: toNumberOrNull(form.capacity_kw),
      panel_count: toNumberOrNull(form.panel_count),
      inverter_count: toNumberOrNull(form.inverter_count),
      module_type: form.module_type || null,
      module_wattage_w: toNumberOrNull(form.module_wattage_w),
      tilt_degrees: toNumberOrNull(form.tilt_degrees),
      azimuth_degrees: toNumberOrNull(form.azimuth_degrees),
      commissioning_date: form.commissioning_date || null,
      area_sqm: toNumberOrNull(form.area_sqm),
    };

    setSubmitting(true);
    try {
      await createPlant(payload);
      await refetch();
      setJustCreated(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save plant.");
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || plantLoading) {
    return <div className="p-6 text-gray-500">Loading…</div>;
  }

  if (plant || justCreated) {
    // Brief transitional state -- refetch() is awaited before justCreated is
    // set, so `plant` should already be populated by the time we get here;
    // this only covers the instant before that render lands.
    return <div className="p-6 text-gray-500">Loading your plant…</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-10">
      <form onSubmit={handleSubmit} className="max-w-xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Set up your plant</h1>
          <p className="text-sm text-gray-500">
            A few details about your installation. Location and tariff are used right away for
            solar-position calculations and revenue estimates — the rest is stored for when data
            connection is set up.
          </p>
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </p>
        )}

        <Section title="Basic info">
          <Field label="Plant name" required>
            <input
              type="text"
              required
              value={form.name}
              onChange={set("name")}
              placeholder="e.g. Green Valley Solar"
              className="input"
            />
          </Field>
        </Section>

        <Section title="Location">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Latitude" required>
              <input
                type="number"
                step="any"
                required
                value={form.latitude}
                onChange={set("latitude")}
                placeholder="18.52"
                className="input"
              />
            </Field>
            <Field label="Longitude" required>
              <input
                type="number"
                step="any"
                required
                value={form.longitude}
                onChange={set("longitude")}
                placeholder="73.86"
                className="input"
              />
            </Field>
          </div>
        </Section>

        <Section title="Financials">
          <Field label="Electricity tariff (per kWh)" required>
            <input
              type="number"
              step="any"
              required
              value={form.tariff_per_kwh}
              onChange={set("tariff_per_kwh")}
              placeholder="4.0"
              className="input"
            />
          </Field>
        </Section>

        <Section title="Capacity & equipment" optional>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Capacity (kW)">
              <input type="number" step="any" value={form.capacity_kw} onChange={set("capacity_kw")} className="input" />
            </Field>
            <Field label="Area (m²)">
              <input type="number" step="any" value={form.area_sqm} onChange={set("area_sqm")} className="input" />
            </Field>
            <Field label="Number of panels">
              <input type="number" value={form.panel_count} onChange={set("panel_count")} className="input" />
            </Field>
            <Field label="Number of inverters">
              <input type="number" value={form.inverter_count} onChange={set("inverter_count")} className="input" />
            </Field>
            <Field label="Module type">
              <select value={form.module_type} onChange={set("module_type")} className="input">
                <option value="">—</option>
                {MODULE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Module wattage (W)">
              <input
                type="number"
                step="any"
                value={form.module_wattage_w}
                onChange={set("module_wattage_w")}
                className="input"
              />
            </Field>
            <Field label="Tilt (degrees)">
              <input type="number" step="any" value={form.tilt_degrees} onChange={set("tilt_degrees")} className="input" />
            </Field>
            <Field label="Azimuth (degrees)">
              <input
                type="number"
                step="any"
                value={form.azimuth_degrees}
                onChange={set("azimuth_degrees")}
                className="input"
              />
            </Field>
            <Field label="Commissioning date">
              <input
                type="date"
                value={form.commissioning_date}
                onChange={set("commissioning_date")}
                className="input"
              />
            </Field>
          </div>
        </Section>

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-blue-600 text-white text-sm font-medium py-2.5 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Save plant"}
        </button>
      </form>
    </div>
  );
}

function Section({
  title,
  optional,
  children,
}: {
  title: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-lg border shadow-sm p-4 space-y-3">
      <div className="text-sm font-medium text-gray-700">
        {title}
        {optional && <span className="text-gray-400 font-normal"> (optional)</span>}
      </div>
      {children}
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-gray-500 mb-1">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </span>
      {children}
    </label>
  );
}
