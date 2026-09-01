# Solar Plant Manager

A solar plant monitoring product, built in two layers: a rigorous data
analytics/ML demo on real historical plant data, and a real (if early-stage)
product on top — accounts, plant onboarding, live weather ingestion, and
physically-grounded synthetic generation data, all verified against real
services rather than mocked.

## What it is

This started as a data analytics course project (predict and diagnose solar
plant performance from a real Kaggle dataset — two Indian solar plants, 34
days, 22 inverters each) and grew into a product: **Solar Plant Manager**, a
dashboard an owner could plausibly use to monitor their plant's health,
maintenance risk, and expected yield.

Two things run side by side in this repo:

- **The historical demo** (`webapp/backend` serving `Plant 1`/`Plant 2`) —
  showcases the original analysis: a cross-validated Random Forest "expected
  power" model, residual-based anomaly detection, trend-based risk scoring,
  and day-ahead forecasting benchmarked against persistence/climatology
  baselines. Reachable via the dashboard nav once logged in.
- **The real product flow** — sign up, configure your own plant (location,
  capacity, panel specs), and watch real data start accumulating: actual
  current weather for your plant's coordinates, and physically-grounded
  synthetic generation readings (there's no real inverter hardware, so this
  is the deliberate, honestly-labeled stand-in — see below).

## What it does

1. **Sign up / log in** — real accounts via Supabase Auth
2. **Configure a plant** — name, location, tariff, and optional specs
   (capacity, panel count/type, tilt/azimuth, commissioning date, area).
   Every field is actually used, not decorative — location and tilt/azimuth
   drive real solar-position physics, panel type sets a real temperature
   coefficient, commissioning date drives degradation, area is a capacity
   fallback, tariff computes real revenue
3. **Live ingestion** (every 15 min while the app is open): fetches real
   current weather for the plant's coordinates (Open-Meteo), then generates
   synthetic per-inverter power output from that weather via `pvlib`
   plane-of-array irradiance + a standard temperature-derating model —
   multiple virtual inverters with persistent efficiency variance and
   occasional realistic multi-hour fault episodes
4. **A live dashboard** for that real, accumulating data — energy/revenue to
   date, active faults, weather and generation history charts, per-inverter
   status
5. **The historical demo dashboard** — Command Center, Maintenance Queue
   (with plain-language fault diagnosis), and Forecast pages, all driven by
   the original ML analysis on the Kaggle dataset, with a timeline scrubber
   to replay the 34-day history

## Current state

Phases 0–15 are built and verified end-to-end (see `PRODUCT_PLAN.md` for the
full phase-by-phase log, including every bug found and how it was verified —
this README is the summary, that file is the detailed record).

**Solid:**
- Backend API serving the historical demo's ML pipeline (FastAPI)
- Real Supabase auth, gating the dashboard behind a configured plant
- Plant setup with a full, genuinely-used field set
- Real weather ingestion + physically-grounded synthetic generation,
  including stateful fault injection
- A live dashboard for a user's real accumulating data

**Explicitly not done — parked, not forgotten:**
- **The ML/data-analytics layer doesn't run on a user's real plant data
  yet.** The historical demo's Random Forest methodology exists, but hasn't
  been pointed at real per-user data — partly a data volume problem (a new
  plant has only a few 15-minute ticks so far), partly a genuine design
  question: training ML to rediscover a relationship *we* coded (the
  synthetic generation formula) is somewhat circular unless it's framed
  right. The strongest path identified: backfill ~30 days of synthetic
  history using Open-Meteo's *historical* weather API (not just current),
  then both train the expected-power model **and** validate its anomaly
  detection against the known injected fault labels — real precision/recall
  metrics the original coursework couldn't produce, since it never had
  ground truth.
- Real scheduled ingestion (currently: client-side polling while a browser
  tab is open, not a background job)
- Deployment (currently local-only)

## Architecture

```
webapp/
  backend/           FastAPI (Python) — historical ML demo + weather/synthetic-generation compute
    app/
      data.py, solar_features.py       historical Plant 1/2 pipeline
      fault_model.py, forecast_model.py  the ML: expected-power model, anomaly detection, forecasting
      weather.py                       real current weather (Open-Meteo) + clear-sky physics
      synthetic_generation.py          weather + plant specs -> synthetic panel output (pvlib)
  frontend/          Next.js (App Router) + Tailwind + Recharts
    src/app/
      (dashboard)/    historical demo — Overview, Maintenance, Forecast (auth + plant required)
      login/          sign in / sign up
      setup-plant/    plant onboarding form -> live real-plant dashboard once configured
    src/context/      Auth, Plant, and Simulation (demo timeline) state
    src/lib/          Supabase client + typed API/data-access functions
  supabase/           SQL migrations (run manually in the Supabase SQL Editor —
                      the app only holds the client-safe anon key, not admin access)
```

## Running it

```bash
# Backend
cd webapp/backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/uvicorn app.main:app --reload --port 8000

# Frontend (needs .env.local with NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY)
cd webapp/frontend
npm install && npm run dev
```

Run the SQL files in `webapp/supabase/` (in order) against your own Supabase
project before using the real-product flow. The historical demo dashboard
needs the Kaggle ["Solar Power Generation Data"](https://www.kaggle.com/datasets/anikannal/solar-power-generation-data)
CSVs in `webapp/backend/data/raw/` (not included in the repo).

## Next phase

The clear next step is closing the ML/data-analytics gap described above:
backfill real historical weather for a configured plant, generate a
month-scale synthetic dataset from it, then run the same rigor as the
original analysis — cross-validated expected-power model, residual-based
anomaly detection — but this time validated against real ground-truth fault
labels. After that: real scheduled ingestion and deployment.
