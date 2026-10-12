-- Run this in the Supabase Dashboard: SQL Editor -> New query -> paste -> Run.
-- Product MVP (PRODUCT_PLAN.md, "Product MVP -- complete plant manager").

-- What the owner paid for the system, for the payback estimate on Finance.
-- Optional; owners can already update their own plant under RLS.
alter table plants add column if not exists system_cost double precision;

-- Energy and earnings per calendar month in the plant's own time zone, over
-- the plant's whole history (the pages only read the last ~35 days of raw
-- readings). Runs as the caller, so RLS applies. Rows from before
-- energy_kwh existed were 15-minute readings.
create or replace function plant_monthly(p_plant_id uuid, p_tz text)
returns table (month text, energy_kwh double precision, revenue double precision, reading_count bigint)
language sql
stable
security invoker
set search_path = public
as $$
  select to_char(date_trunc('month', r.recorded_at at time zone p_tz), 'YYYY-MM') as month,
         coalesce(sum(coalesce(r.energy_kwh, r.ac_power_kw * 0.25)), 0) as energy_kwh,
         coalesce(sum(r.revenue_per_interval), 0) as revenue,
         count(*) as reading_count
    from generation_readings r
    join inverters i on i.id = r.inverter_id
   where i.plant_id = p_plant_id
   group by 1
   order by 1;
$$;
