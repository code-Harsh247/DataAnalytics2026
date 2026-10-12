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
3. **Connect the plant's gateway** with a 15-minute pairing code. The
   gateway is a **separate, simulated device** (`python -m gateway`): it
   behaves like a real inverter data logger, holds its own device token, and
   pushes per-inverter telemetry (power, DC voltage/current, temperatures,
   energy counters) generated from **real weather** at the plant (Open-Meteo)
   with `pvlib` physics, measurement noise, shading and fault episodes. It
   catches up on readings it missed while off, and a console lets you
   `inject` a fault or take its link `offline` during a demo
4. **A live dashboard**: Connected/Offline badge, readings arriving without
   a refresh (Supabase Realtime), energy/revenue to date, weather and output
   history, and a **live verdict** per inverter ("INV-3 is under-producing by
   ~27% since 08:50, ≈1.87 lost in the last 24 h"). The verdict comes from a
   model trained on the plant's own history, never from the simulator's
   fault labels
5. **30-day fault analysis** (needs ≥ 2 inverters): runs every detection
   model over the readings stored for the plant and returns:
   - expected vs. actual output, with flagged hours (and the injected faults
     as an optional overlay)
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

Phases 0–15, the hackathon MVP's ML pipeline, and the **Working MVP**
(simulated gateway, live verdict, analysis on stored data) are built and
verified end to end. See [`PRODUCT_PLAN.md`](PRODUCT_PLAN.md) for the
phase-by-phase log; this README is the summary.

**Solid:**
- Real Supabase auth, gating the dashboard behind a configured plant
- Plant setup with a full, genuinely-used field set
- Gateway pairing with per-device tokens (stored hashed); telemetry through
  database functions, so the whole system runs on the public anon key — no
  admin key anywhere
- A simulated gateway with catch-up, store-and-forward and a fault console
- A live dashboard (Realtime) with a per-inverter verdict from the detector
- Historical backfill, an evaluation harness, four anomaly-detection models,
  and the 30-day analysis on the plant's stored readings
- The backend reads Supabase as the signed-in user (their JWT), so row-level
  security applies to it too

**Not done yet:**
- Real hardware: the only gateway is the simulated one (a CSV import of a
  real inverter's export would be the first step)
- Email/push alerts (the verdict is in-app only)
- Deployment (currently local only)

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
      plant_data.py                    a user's stored readings (read as that user) -> model dataset
      plant_analysis.py                POST /api/plants/{id}/analyze: the 30-day analysis on stored data
      plant_status.py                  GET  /api/plants/{id}/status: the live per-inverter verdict
      seed_supabase.py                 fill your own plant with 30 days of history
    gateway/                           the simulated gateway: python -m gateway pair|run
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
```

The historical demo dashboard needs the Kaggle ["Solar Power Generation Data"](https://www.kaggle.com/datasets/anikannal/solar-power-generation-data)
CSVs in `webapp/backend/data/raw/` (not included in the repo). The real
product flow doesn't need them.

## Next phase

- **Real data in**: import a CSV export from a real inverter portal, then a
  real gateway
- **Peer-comparison model**: promote the exploratory peer hybrid from
  `FINDINGS.md` §5 to a fifth model and the default (it beats Random Forest,
  0.78 vs 0.71)
- **Alerts**: email/push when the verdict changes
- **Deploy**: backend on Render, frontend on Vercel
