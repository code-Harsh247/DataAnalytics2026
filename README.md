# Solar Plant Manager

A solar plant monitoring product, built in two layers: a rigorous data
analytics/ML demo on real historical plant data, and a real (if early-stage)
product on top — accounts, plant onboarding, live weather ingestion,
physically-grounded synthetic generation data, and ML fault detection
validated against ground-truth fault labels.

*Data Analytics 2026 — Harsh Chattar (22CS30028), Abhinav Kumar Singh (22CS30005)*

## What it is

This started as a data analytics course project (predict and diagnose solar
plant performance from a real Kaggle dataset — two Indian solar plants, 34
days, 22 inverters each) and grew into a product: **Solar Plant Manager**, a
dashboard an owner could plausibly use to monitor their plant's health,
spot failing inverters, and see what each fault is costing them.

Two things run side by side in this repo:

- **The historical demo** (`webapp/backend` serving `Plant 1`/`Plant 2`) —
  showcases the original analysis: a cross-validated Random Forest "expected
  power" model, residual-based anomaly detection, trend-based risk scoring,
  and day-ahead forecasting benchmarked against persistence/climatology
  baselines. Reachable via the dashboard nav once logged in.
- **The real product flow** — sign up, configure your own plant (location,
  capacity, panel specs), watch real data start accumulating, and run a
  30-day fault analysis that compares four detection models on your plant.
  There's no real inverter hardware, so generation is a deliberate,
  honestly-labeled synthetic stand-in driven by real weather — see below.

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
5. **30-day fault analysis** (needs ≥ 2 inverters): the backend pulls 30 days
   of real historical weather for the plant, generates a month of synthetic
   output with injected, labeled faults, trains every detection model, and
   returns:
   - expected vs. actual output, with flagged hours (and the true faults as
     an optional overlay)
   - per-inverter status with kWh and revenue lost
   - a model comparison — precision, recall, F1 against the true labels, and
     R² of the expected-power fit — where you can switch which model's
     results you're looking at
6. **The historical demo dashboard** — Command Center, Maintenance Queue
   (with plain-language fault diagnosis), and Forecast pages, all driven by
   the original ML analysis on the Kaggle dataset, with a timeline scrubber
   to replay the 34-day history

## Model results

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

## Current state

Phases 0–15 plus the hackathon MVP's ML pipeline and analysis panel are
built and verified end to end. See [`PRODUCT_PLAN.md`](PRODUCT_PLAN.md) for
the phase-by-phase log; this README is the summary.

**Solid:**
- Backend API serving the historical demo's ML pipeline (FastAPI)
- Real Supabase auth, gating the dashboard behind a configured plant
- Plant setup with a full, genuinely-used field set
- Real weather ingestion + physically-grounded synthetic generation,
  including stateful fault injection
- A live dashboard for a user's real accumulating data
- Historical backfill, an evaluation harness, four anomaly-detection models,
  and `POST /api/plants/analyze`, wired into the dashboard's analysis panel

**Not done yet:**
- Deployment (currently local only)
- Real scheduled ingestion: data is currently collected by client-side
  polling while a browser tab is open, not by a background job
- The backend has no auth of its own. `/analyze` is stateless and takes the
  plant's specs in the request; it never reads or writes user data

## Architecture

```
webapp/
  backend/           FastAPI (Python)
    app/
      data.py, solar_features.py       historical Plant 1/2 pipeline
      fault_model.py, forecast_model.py  historical demo ML: expected power, anomalies, forecasting
      weather.py                       real current weather (Open-Meteo) + clear-sky physics
      synthetic_generation.py          weather + plant specs -> synthetic panel output (pvlib)
      backfill.py                      30 days of archive weather -> labeled synthetic dataset
      models/                          anomaly models (auto-discovered) + evaluate.py harness
      analysis.py                      POST /api/plants/analyze: backfill, train all models, compare
      seed_supabase.py                 fill your own plant with 30 days of history
    data/backfill/sample_plant.csv     canonical evaluation dataset
  frontend/          Next.js (App Router) + Tailwind + Recharts
    src/app/
      (dashboard)/    historical demo — Overview, Maintenance, Forecast (auth + plant required)
      login/          sign in / sign up
      setup-plant/    plant onboarding form -> live real-plant dashboard once configured
    src/components/   incl. PlantDashboardView + AnalysisPanel (the 30-day analysis)
    src/context/      Auth, Plant, and Simulation (demo timeline) state
    src/lib/          Supabase client + typed API/data-access functions
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

Open <http://localhost:3000>. For a guided walkthrough, see [`DEMO.md`](DEMO.md).

**Useful extras** (from `webapp/backend`; on Windows swap `.venv/bin` for
`.venv/Scripts`):

```bash
# Reproduce the model results table
.venv/bin/python -m app.models.evaluate --data data/backfill/sample_plant.csv

# Give your own plant 30 days of history, so the live charts aren't empty
SEED_EMAIL=<your login email> .venv/bin/python -m app.seed_supabase
```

The historical demo dashboard needs the Kaggle ["Solar Power Generation Data"](https://www.kaggle.com/datasets/anikannal/solar-power-generation-data)
CSVs in `webapp/backend/data/raw/` (not included in the repo). The real
product flow doesn't need them.

## Next phase

- **Deploy**: backend on Render, frontend on Vercel
- **Peer-comparison model**: promote the exploratory peer hybrid from
  `FINDINGS.md` §5 to a fifth model (it beats Random Forest, 0.78 vs 0.71)
- **Scheduled ingestion**: a background job instead of browser polling
- **Live alerting**: a trailing rather than centered smoothing window, so
  faults can be flagged as they happen instead of only in retrospect
