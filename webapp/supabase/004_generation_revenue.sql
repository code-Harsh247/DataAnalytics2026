-- Run this in the Supabase Dashboard: SQL Editor -> New query -> paste -> Run.
-- Adds a revenue column to generation_readings, computed from the plant's
-- own tariff_per_kwh (previously collected at setup but never used).

alter table generation_readings
  add column if not exists revenue_per_interval double precision;
