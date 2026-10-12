-- Run this in the Supabase Dashboard: SQL Editor -> New query -> paste -> Run.
-- Same handoff as 001-004. Contract 4 in PRODUCT_PLAN.md ("Working MVP").
--
-- Connects a plant to a gateway: a separate process (today a simulated one,
-- `python -m gateway`) that pushes inverter telemetry the way a real data
-- logger would. The gateway authenticates with its own device token, never
-- the owner's password, and can only write to its own plant's inverters.
-- Everything it does goes through the security-definer functions below, so
-- the app still runs on the anon key alone -- no service_role key.

create extension if not exists pgcrypto with schema extensions;

-- ---------------------------------------------------------------- gateways

create table if not exists gateways (
  id uuid primary key default gen_random_uuid(),
  plant_id uuid references plants(id) on delete cascade not null unique,
  serial text,
  -- sha256 of the device token; the token itself is only ever shown to the
  -- gateway once, at pairing.
  token_hash text unique,
  pairing_code text unique,
  pairing_expires_at timestamptz,
  paired_at timestamptz,
  last_seen_at timestamptz,
  created_at timestamptz not null default now()
);

alter table gateways enable row level security;

-- Owners can see their gateway (for the "Connected / last seen" badge).
-- No insert/update policies: only the functions below write here.
create policy "Users can view the gateway for their own plants"
  on gateways for select
  using (
    exists (
      select 1 from plants
      where plants.id = gateways.plant_id
      and plants.user_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------- telemetry columns
-- All nullable / defaulted: existing rows and the old browser pipeline keep working.

alter table generation_readings
  add column if not exists energy_kwh double precision,
  add column if not exists dc_voltage_v double precision,
  add column if not exists dc_current_a double precision,
  add column if not exists inverter_temp_c double precision,
  add column if not exists energy_today_kwh double precision,
  add column if not exists status_code text,
  -- Ground-truth label, like fault_active: for scoring detection only.
  -- No UI or detector may read either column.
  add column if not exists fault_severity double precision,
  add column if not exists source text not null default 'browser';

alter table weather_readings
  add column if not exists wind_speed_kmh double precision,
  add column if not exists source text not null default 'browser';

-- ---------------------------------------------------------------- helpers

-- Plant + inverters as the gateway needs them. Internal: not callable by clients.
create or replace function gateway_config(p_plant_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'plant', (select to_jsonb(p) - 'user_id' from plants p where p.id = p_plant_id),
    'inverters', coalesce((
      select jsonb_agg(jsonb_build_object(
               'id', i.id, 'label', i.label,
               'base_efficiency_factor', i.base_efficiency_factor)
             order by i.label)
      from inverters i where i.plant_id = p_plant_id
    ), '[]'::jsonb)
  );
$$;

revoke execute on function gateway_config(uuid) from public, anon, authenticated;

-- ---------------------------------------------------------------- pairing

-- Called by the logged-in owner. Creates (or rotates) the plant's pairing
-- code, valid for 15 minutes. An already-paired gateway keeps working until
-- a new one pairs with the new code.
create or replace function create_pairing_code(p_plant_id uuid)
returns text
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_code text;
begin
  if not exists (select 1 from plants where id = p_plant_id and user_id = auth.uid()) then
    raise exception 'plant not found' using errcode = '42501';
  end if;

  -- 6 characters from an alphabet without look-alikes (no 0/O, 1/I).
  select string_agg(
           substr('ABCDEFGHJKLMNPQRSTUVWXYZ23456789',
                  1 + get_byte(gen_random_bytes(1), 0) % 32, 1), '')
    into v_code
    from generate_series(1, 6);

  insert into gateways (plant_id, pairing_code, pairing_expires_at)
  values (p_plant_id, v_code, now() + interval '15 minutes')
  on conflict (plant_id) do update
    set pairing_code = excluded.pairing_code,
        pairing_expires_at = excluded.pairing_expires_at;

  return v_code;
end;
$$;

-- Called by the gateway with the anon key. Exchanges a valid code for a
-- device token, creating the plant's inverters if the app hasn't yet.
create or replace function pair_gateway(p_code text, p_serial text)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_gateway gateways;
  v_token text;
begin
  select * into v_gateway
    from gateways
   where pairing_code = upper(trim(p_code))
     and pairing_expires_at > now()
   for update;
  if not found then
    raise exception 'invalid or expired pairing code' using errcode = '28000';
  end if;

  if not exists (select 1 from inverters where plant_id = v_gateway.plant_id) then
    insert into inverters (plant_id, label, base_efficiency_factor)
    select v_gateway.plant_id, 'INV-' || n, 0.96 + random() * 0.06  -- same spread as the app
      from generate_series(1, coalesce(
        (select inverter_count from plants where id = v_gateway.plant_id), 4)) as n;
  end if;

  v_token := encode(gen_random_bytes(32), 'hex');
  update gateways
     set token_hash = encode(digest(v_token, 'sha256'), 'hex'),
         serial = left(p_serial, 64),
         pairing_code = null,
         pairing_expires_at = null,
         paired_at = now(),
         last_seen_at = now()
   where id = v_gateway.id;

  return jsonb_build_object('token', v_token) || gateway_config(v_gateway.plant_id);
end;
$$;

-- ---------------------------------------------------------------- gateway calls

-- Resolves a device token to its gateway row, or raises. Internal.
create or replace function gateway_for_token(p_token text)
returns gateways
language plpgsql
stable
security definer
set search_path = public, extensions
as $$
declare
  v_gateway gateways;
begin
  select * into v_gateway
    from gateways
   where token_hash = encode(digest(coalesce(p_token, ''), 'sha256'), 'hex');
  if not found then
    raise exception 'invalid device token' using errcode = '28000';
  end if;
  return v_gateway;
end;
$$;

revoke execute on function gateway_for_token(text) from public, anon, authenticated;

-- Current config and where to resume: the latest reading from any source,
-- so a plant already seeded up to now needs no catch-up.
create or replace function gateway_state(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_gateway gateways := gateway_for_token(p_token);
begin
  return gateway_config(v_gateway.plant_id) || jsonb_build_object(
    'serial', v_gateway.serial,
    'last_recorded_at', (
      select max(r.recorded_at)
        from generation_readings r
        join inverters i on i.id = r.inverter_id
       where i.plant_id = v_gateway.plant_id
    )
  );
end;
$$;

-- Telemetry upload (Contract 5). Rows for inverters outside the gateway's
-- plant are silently dropped by the join; existing timestamps are skipped,
-- so re-sending a batch is safe. Empty arrays work as a heartbeat.
create or replace function ingest_telemetry(p_token text, p_weather jsonb, p_readings jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_gateway gateways := gateway_for_token(p_token);
  v_weather_count int := 0;
  v_reading_count int := 0;
begin
  if jsonb_array_length(coalesce(p_readings, '[]'::jsonb)) > 2000
     or jsonb_array_length(coalesce(p_weather, '[]'::jsonb)) > 2000 then
    raise exception 'too many rows in one call (max 2000)' using errcode = '54000';
  end if;

  insert into weather_readings (
    plant_id, recorded_at, temperature_c, cloud_cover_pct, ghi_wm2, dni_wm2, dhi_wm2,
    clearsky_ghi_wm2, clearsky_index, wind_speed_kmh, source)
  select v_gateway.plant_id, w.recorded_at, w.temperature_c, w.cloud_cover_pct,
         w.ghi_wm2, w.dni_wm2, w.dhi_wm2, w.clearsky_ghi_wm2, w.clearsky_index,
         w.wind_speed_kmh, 'gateway'
    from jsonb_to_recordset(coalesce(p_weather, '[]'::jsonb)) as w(
         recorded_at timestamptz, temperature_c double precision,
         cloud_cover_pct double precision, ghi_wm2 double precision,
         dni_wm2 double precision, dhi_wm2 double precision,
         clearsky_ghi_wm2 double precision, clearsky_index double precision,
         wind_speed_kmh double precision)
   where w.recorded_at is not null
  on conflict (plant_id, recorded_at) do nothing;
  get diagnostics v_weather_count = row_count;

  insert into generation_readings (
    inverter_id, recorded_at, dc_power_kw, ac_power_kw, cell_temp_c, poa_irradiance_wm2,
    fault_active, fault_severity, revenue_per_interval, energy_kwh, dc_voltage_v,
    dc_current_a, inverter_temp_c, energy_today_kwh, status_code, source)
  select r.inverter_id, r.recorded_at, r.dc_power_kw, r.ac_power_kw, r.cell_temp_c,
         r.poa_irradiance_wm2, coalesce(r.fault_active, false), r.fault_severity,
         r.revenue_per_interval, r.energy_kwh, r.dc_voltage_v, r.dc_current_a,
         r.inverter_temp_c, r.energy_today_kwh, r.status_code, 'gateway'
    from jsonb_to_recordset(coalesce(p_readings, '[]'::jsonb)) as r(
         inverter_id uuid, recorded_at timestamptz, dc_power_kw double precision,
         ac_power_kw double precision, cell_temp_c double precision,
         poa_irradiance_wm2 double precision, fault_active boolean,
         fault_severity double precision, revenue_per_interval double precision,
         energy_kwh double precision, dc_voltage_v double precision,
         dc_current_a double precision, inverter_temp_c double precision,
         energy_today_kwh double precision, status_code text)
    join inverters i on i.id = r.inverter_id and i.plant_id = v_gateway.plant_id
   where r.recorded_at is not null
  on conflict (inverter_id, recorded_at) do nothing;
  get diagnostics v_reading_count = row_count;

  update gateways set last_seen_at = now() where id = v_gateway.id;

  return jsonb_build_object(
    'inserted_weather', v_weather_count,
    'inserted_readings', v_reading_count);
end;
$$;

-- ---------------------------------------------------------------- dashboard totals

-- Energy, revenue and reading count in SQL, instead of paging every row into
-- the browser. Runs as the caller, so RLS applies. Rows from before
-- energy_kwh existed were all 15-minute readings.
create or replace function plant_totals(p_plant_id uuid)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select jsonb_build_object(
    'total_energy_kwh', coalesce(sum(coalesce(r.energy_kwh, r.ac_power_kw * 0.25)), 0),
    'total_revenue', coalesce(sum(r.revenue_per_interval), 0),
    'reading_count', count(*))
  from generation_readings r
  join inverters i on i.id = r.inverter_id
  where i.plant_id = p_plant_id;
$$;

-- ---------------------------------------------------------------- realtime

-- Lets the dashboard subscribe to new readings and gateway heartbeats.
-- Realtime applies the same RLS policies as normal reads.
do $$
begin
  if not exists (select 1 from pg_publication_tables
                 where pubname = 'supabase_realtime' and tablename = 'generation_readings') then
    alter publication supabase_realtime add table generation_readings;
  end if;
  if not exists (select 1 from pg_publication_tables
                 where pubname = 'supabase_realtime' and tablename = 'gateways') then
    alter publication supabase_realtime add table gateways;
  end if;
end;
$$;
