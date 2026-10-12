# Solar Plant Manager

An MVP of a complete solar plant management tool: live monitoring,
production analytics, generation forecasts, plant health with ML fault
detection, and financials, for a small plant owner.

*Data Analytics 2026 — Harsh Chattar (22CS30028), Abhinav Kumar Singh (22CS30005)*

## What it is

This started as a data analytics course project on a Kaggle dataset (two
Indian solar plants, 34 days) and grew into a product. An owner signs up,
describes their plant, connects its gateway, and gets the answers they need
day to day: how much did I make, how well is the plant doing, what will it
make this week, is anything wrong, and when does it pay for itself.

**Be clear about one thing:** there's no real inverter hardware. The
gateway is a *simulated* device that behaves like a real data logger and
generates telemetry from **real weather** at the plant's location with
`pvlib` physics. That's labelled in the app, and it's also what lets us
measure how accurate the fault detection is, because the simulator records
the faults it injects.

## What it does

**Getting started**
- **Accounts** (Supabase Auth) and **plant setup**: location, tariff,
  capacity, panels, tilt/azimuth, install date. Every field feeds the physics.
- **Connect the gateway** with a 15-minute pairing code. The simulated
  gateway (`python -m gateway`) holds its own device token, catches up on
  readings it missed while off, and streams live ones. Its console can
  `inject` a fault or take its link `offline` for demos.

**Five pages**
1. **Overview**: power now vs what the plant should be producing; energy,
   earnings and CO₂ avoided today / this month / lifetime; performance
   ratio; specific yield; a health summary; today's output curve against
   the forecast. Updates live (Supabase Realtime).
2. **Production**: daily energy with performance ratio, monthly totals,
   inverter comparison (energy, share, PR), best/worst day, 7-day output
   and sunlight charts.
3. **Forecast**: the next 7 days (kWh, earnings, likely range, cloud cover),
   today hour by hour against actual output, the projected month total, and
   **how accurate the forecast has been**: each recent day's forecast *as
   issued the day before* against what the plant actually made.
4. **Health**: a live verdict per inverter from the ML detector ("INV-3 is
   under-producing by ~27% since 08:50, ≈1.87 lost in the last 24 h"),
   availability, alert history with what each episode cost, a loss
   breakdown from sunlight potential down to delivered energy, and the
   30-day detection report comparing four models.
5. **Finance**: earnings to date and per day, projected annual production
   and earnings (a typical year of real weather at the site), and payback
   once the owner enters the system cost.

## Fault detection: model results

One feature of the Health page, and the most measured part of the project.

Four detectors, compared on the same data with the same metrics. The
canonical dataset is 30 days of real weather at 18°N 80°E, a 7.5 kW plant
with 4 inverters, and seed 42. The first 70% of hours train, the last 30%
test, and only daylight hours are scored. Because one test week holds only
~35 faulted hours, models are also compared as a **mean over 8 datasets**
(seeds 1–8).

| Model | Owner | F1 (seed 42) | Mean F1 (seeds 1–8) | Precision | Recall | R² (healthy) |
|---|---|---|---|---|---|---|
| `random_forest` — expected power + residual | Abhinav | 0.675 | **0.705** | 0.70 | 0.72 | **0.988** |
| `gradient_boosting` — expected power + residual | Harsh | 0.675 | 0.677 | 0.73 | 0.64 | 0.987 |
| `baseline_ratio` — physics ratio, no ML | shared | 0.610 | 0.638 | 0.58 | 0.73 | 0.974 |
| `isolation_forest` — unsupervised | Abhinav | 0.667 | 0.628 | **0.73** | 0.57 | — |

- **Learning what healthy output should look like wins.** Both
  expected-power models beat the physics-only baseline. Random Forest is
  best overall; gradient boosting is more precise but misses more.
- **Unsupervised detection is precise but misses mild faults.** Without an
  expected-power model it can't see a small, steady shortfall.
- **Faults below ~10% severity are undetectable by any model.** They sit
  inside the noise floor (measurement noise plus the gap between reported
  and on-site irradiance). That's a limit of the physics, not a bug.

The reasoning behind every modelling decision, the dead ends, and some
exploratory models are in [`FINDINGS.md`](FINDINGS.md). One example: a
no-ML peer comparison reaches 0.78.

## Forecasting

Forecast = Open-Meteo's weather forecast for the site → the same physics
model → × the plant's **calibration** (actual ÷ physics over the last 14
days; it absorbs dirt, shading and wiring losses). Accuracy is measured
against the forecast *as issued the day before* (Open-Meteo's previous-runs
API), not against hindsight.

Over **12 months** at the test plant (Pune), the day-ahead forecast's error
was **1.54 kWh/day (4.6%)**: **42% lower than "tomorrow = today"**
(persistence) and 59% lower than a 30-day average. The monsoon roughly
triples the error, but the lead holds in every month.

## Analytics report

Uncertainty and significance of the model comparison, detection by fault
episode and time to detect, the detection limit as a curve, how results
depend on the simulator's noise, the data's exploratory analysis, and the
forecast's skill: **[`webapp/backend/analysis/REPORT.md`](webapp/backend/analysis/REPORT.md)**
(12 figures, regenerated by `python -m analysis.run_all`). The short version
is in `FINDINGS.md` §6. For example, RF and Gradient Boosting are
statistically tied, and a plant-wide sunlight error is what makes the ML
beat the physics baseline.

## Current state

Built and verified end to end on a test plant: accounts and setup, gateway
pairing, live monitoring, the five pages, fault detection and the forecast.
See [`PRODUCT_PLAN.md`](PRODUCT_PLAN.md) for the phase-by-phase log.

**Solid:**
- Real Supabase auth and row-level security everywhere; the backend reads
  Supabase as the signed-in user (their JWT), and the gateway uses its own
  hashed device token. No admin key anywhere.
- A simulated gateway with catch-up, store-and-forward and a fault console
- One cached data frame per plant behind every page, so numbers agree
  across pages (today's energy is the same on Overview, Production and Forecast)
- Real day-ahead forecast accuracy; a typical-year projection from real
  archive weather

**Not done yet:**
- Real hardware: the only gateway is the simulated one (a CSV import of a
  real inverter's export would be the first step)
- Email/push alerts (warnings are in-app only)
- Cleaning advice (needs dirt build-up and rain in the simulator)
- Multiple plants per account; deployment (currently local only)

## Architecture

```
webapp/
  backend/           FastAPI (Python)
    app/
      synthetic_generation.py          shared physics constants (pvlib model)
      backfill.py                      archive weather -> labelled synthetic dataset (the benchmark)
      models/                          anomaly models (auto-discovered) + evaluate.py harness
      analysis.py                      POST /api/plants/analyze: benchmark-style analysis on a fresh dataset
      plant_data.py                    a user's stored readings (read as that user) -> model dataset
      plant_metrics.py                 the cached per-plant frame: energy, expected, PR, calibration, time zone
      plant_forecast.py                7-day forecast, day-ahead accuracy, typical-year projection
      plant_pages.py                   GET /api/plants/{id}/overview|production|forecast|health|finance
      plant_analysis.py                POST /api/plants/{id}/analyze: the 30-day detection report
      plant_status.py                  GET  /api/plants/{id}/status: the live per-inverter verdict
      seed_supabase.py                 fill a plant with 30 days of history
    gateway/                           the simulated gateway: python -m gateway pair|run
    data/backfill/sample_plant.csv     canonical evaluation dataset
  frontend/          Next.js (App Router) + Tailwind + Recharts
    src/app/
      (plant)/        Overview (/), Production, Forecast, Health, Finance
      login/          sign in / sign up
      setup-plant/    first-time plant setup
    src/context/      Auth, Plant, and Live (gateway, verdict, Realtime) state
    src/components/   page shell, charts, pairing card, verdict banner, detection report
    src/lib/          Supabase client + typed clients for every endpoint
  supabase/           SQL migrations (run manually in the Supabase SQL Editor —
                      the app only holds the client-safe anon key, not admin access)
```

## Running it

Needs Python ≥ 3.11 and Node.js. Run the SQL files in `webapp/supabase/` (in
order) against your own Supabase project first, then create
`webapp/frontend/.env.local`:

```
NEXT_PUBLIC_SUPABASE_URL=...        # Supabase dashboard → Project Settings → API
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_API_URL=http://localhost:8000
```

In Supabase, turn off **Authentication → Providers → Email → Confirm email**
so sign-up goes straight to plant setup.

**Linux / macOS**

```bash
# Backend (terminal 1)
cd webapp/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (terminal 2)
cd webapp/frontend
npm install && npm run dev
```

**Windows** (Git Bash; in PowerShell use `.venv\Scripts\...`)

```bash
# Backend (terminal 1)
cd webapp/backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/uvicorn app.main:app --reload --port 8000

# Frontend (terminal 2)
cd webapp/frontend
npm install && npm run dev
```

Open <http://localhost:3000>, sign up, set up a plant, and click **Get
pairing code**. Then start the simulated gateway in a third terminal:

```bash
cd webapp/backend
.venv/bin/python -m gateway pair <CODE>     # Windows: .venv/Scripts/python
.venv/bin/python -m gateway run             # a reading every 5 min; --interval 30 for a demo
```

While it runs, type `inject INV-3 30` to break an inverter, `clear` to fix
it, `offline 3m` to drop its link, or `help`. For a guided walkthrough, see
[`DEMO.md`](DEMO.md).

**Useful extras** (from `webapp/backend`; on Windows swap `.venv/bin` for
`.venv/Scripts`):

```bash
# Reproduce the model results table
.venv/bin/python -m app.models.evaluate --data data/backfill/sample_plant.csv

# Give your own plant 30 days of history, so the live charts aren't empty
SEED_EMAIL=<your login email> .venv/bin/python -m app.seed_supabase

# Rerun the analytics report (~8 min; needs matplotlib)
.venv/bin/pip install -r analysis/requirements.txt
.venv/bin/python -m analysis.run_all
```

## Next phase

- **Real data in**: import a CSV export from a real inverter portal, then a
  real gateway
- **Peer-comparison model**: promote the exploratory peer hybrid from
  `FINDINGS.md` §5 to a fifth model and the default (it beats Random Forest,
  0.78 vs 0.71)
- **Alerts**: email/push when the verdict changes
- **Cleaning advice**: model dirt build-up and rain, then predict when
  cleaning pays for itself
- **Deploy**: backend on Render, frontend on Vercel
