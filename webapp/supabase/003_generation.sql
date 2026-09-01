-- Run this in the Supabase Dashboard: SQL Editor -> New query -> paste -> Run.
-- Same handoff as 001_plants.sql / 002_weather_readings.sql.

create table if not exists inverters (
  id uuid primary key default gen_random_uuid(),
  plant_id uuid references plants(id) on delete cascade not null,
  label text not null,
  -- Persistent per-inverter variance (manufacturing/wiring/soiling), applied
  -- every tick so "healthy" output has realistic inverter-to-inverter spread
  -- instead of every inverter producing identically.
  base_efficiency_factor double precision not null default 1.0,
  created_at timestamptz not null default now(),
  unique (plant_id, label)
);

alter table inverters enable row level security;

create policy "Users can view inverters for their own plants"
  on inverters for select
  using (
    exists (
      select 1 from plants
      where plants.id = inverters.plant_id
      and plants.user_id = auth.uid()
    )
  );

create policy "Users can insert inverters for their own plants"
  on inverters for insert
  with check (
    exists (
      select 1 from plants
      where plants.id = inverters.plant_id
      and plants.user_id = auth.uid()
    )
  );

-- A fault episode: severity is the fraction of expected output lost
-- (0.3 = 30% derate) for the window [started_at, ends_at). No "closing" is
-- needed -- a fault simply stops applying once ends_at passes.
create table if not exists inverter_faults (
  id uuid primary key default gen_random_uuid(),
  inverter_id uuid references inverters(id) on delete cascade not null,
  started_at timestamptz not null default now(),
  ends_at timestamptz not null,
  severity double precision not null,
  created_at timestamptz not null default now()
);

alter table inverter_faults enable row level security;

-- inverter_faults is two joins away from the owning user (fault -> inverter
-- -> plant -> user_id), same ownership-check pattern, just one hop further.
create policy "Users can view faults for their own inverters"
  on inverter_faults for select
  using (
    exists (
      select 1 from inverters
      join plants on plants.id = inverters.plant_id
      where inverters.id = inverter_faults.inverter_id
      and plants.user_id = auth.uid()
    )
  );

create policy "Users can insert faults for their own inverters"
  on inverter_faults for insert
  with check (
    exists (
      select 1 from inverters
      join plants on plants.id = inverters.plant_id
      where inverters.id = inverter_faults.inverter_id
      and plants.user_id = auth.uid()
    )
  );

create table if not exists generation_readings (
  id uuid primary key default gen_random_uuid(),
  inverter_id uuid references inverters(id) on delete cascade not null,
  recorded_at timestamptz not null,
  dc_power_kw double precision,
  ac_power_kw double precision,
  cell_temp_c double precision,
  poa_irradiance_wm2 double precision,
  fault_active boolean not null default false,
  created_at timestamptz not null default now(),
  unique (inverter_id, recorded_at)
);

alter table generation_readings enable row level security;

create policy "Users can view generation for their own inverters"
  on generation_readings for select
  using (
    exists (
      select 1 from inverters
      join plants on plants.id = inverters.plant_id
      where inverters.id = generation_readings.inverter_id
      and plants.user_id = auth.uid()
    )
  );

create policy "Users can insert generation for their own inverters"
  on generation_readings for insert
  with check (
    exists (
      select 1 from inverters
      join plants on plants.id = inverters.plant_id
      where inverters.id = generation_readings.inverter_id
      and plants.user_id = auth.uid()
    )
  );
