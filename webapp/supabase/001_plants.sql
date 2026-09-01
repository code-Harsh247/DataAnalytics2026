-- Run this in the Supabase Dashboard: SQL Editor -> New query -> paste -> Run.
-- Not run automatically -- the app only has the client-safe anon key, not
-- admin access to your project.

create table if not exists plants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,

  -- Tier 1: actually used by the app's computations
  name text not null,
  latitude double precision not null,
  longitude double precision not null,
  tariff_per_kwh double precision not null,

  -- Tier 2: realistic plant metadata, stored for future use (not yet wired
  -- into any computation -- see PRODUCT_PLAN.md)
  capacity_kw double precision,
  panel_count integer,
  inverter_count integer,
  module_type text,
  module_wattage_w double precision,
  tilt_degrees double precision,
  azimuth_degrees double precision,
  commissioning_date date,
  area_sqm double precision,

  created_at timestamptz not null default now()
);

alter table plants enable row level security;

create policy "Users can view their own plants"
  on plants for select
  using (auth.uid() = user_id);

create policy "Users can insert their own plants"
  on plants for insert
  with check (auth.uid() = user_id);

create policy "Users can update their own plants"
  on plants for update
  using (auth.uid() = user_id);

create policy "Users can delete their own plants"
  on plants for delete
  using (auth.uid() = user_id);
