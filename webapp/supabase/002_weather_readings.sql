-- Run this in the Supabase Dashboard: SQL Editor -> New query -> paste -> Run.
-- Same handoff as 001_plants.sql -- the app only has the client-safe anon
-- key, not admin access to your project.

create table if not exists weather_readings (
  id uuid primary key default gen_random_uuid(),
  plant_id uuid references plants(id) on delete cascade not null,

  recorded_at timestamptz not null,
  temperature_c double precision,
  cloud_cover_pct double precision,
  ghi_wm2 double precision,
  dni_wm2 double precision,
  dhi_wm2 double precision,
  clearsky_ghi_wm2 double precision,
  clearsky_index double precision,

  created_at timestamptz not null default now(),

  unique (plant_id, recorded_at)
);

alter table weather_readings enable row level security;

-- weather_readings has no user_id column of its own (it belongs to a plant,
-- not directly to a user), so ownership is checked via a join through
-- plants.user_id, same intent as 001_plants.sql's policies.

create policy "Users can view weather for their own plants"
  on weather_readings for select
  using (
    exists (
      select 1 from plants
      where plants.id = weather_readings.plant_id
      and plants.user_id = auth.uid()
    )
  );

create policy "Users can insert weather for their own plants"
  on weather_readings for insert
  with check (
    exists (
      select 1 from plants
      where plants.id = weather_readings.plant_id
      and plants.user_id = auth.uid()
    )
  );
