# Solar Plant Manager Dashboard — Product Build Plan

A separate initiative from the course analysis project (`src/`, `notebooks/`,
`tasks.md` — that deliverable is done and untouched by this). This plan
covers turning the validated analysis into an owner-facing product demo:
FastAPI backend + Next.js frontend, living under `webapp/`.

**Scope for v1** (per brainstorm): single plant (Plant 2 — the one with real
findings to show), trend-based risk scoring (not true predictive
maintenance — see rationale below), timeline-scrubber "live replay" instead
of a real-time clock.

**Why trend-based risk scoring, not "AI predicts failure":** true predictive
maintenance needs historical examples of past failures to learn from, which
this dataset doesn't have. Trend-based scoring (is this inverter's anomaly
severity worsening over time?) is honest about what the data supports and
still genuinely useful. State this plainly in the UI copy, not just here.

---

## Phase 0 — Setup & Architecture

- [x] Repo layout: `webapp/backend` (FastAPI), `webapp/frontend` (Next.js)
- [x] Backend skeleton: FastAPI + uvicorn, CORS for local dev
      (`webapp/backend/app/main.py`), Python deps in `webapp/backend/requirements.txt`
- [x] Restored the Kaggle plant data into `webapp/backend/data/raw/` (from the
      same archive.zip used for the course project — not tracked by git,
      see `.gitignore`)
- [x] Frontend skeleton: Next.js (TypeScript, App Router, Tailwind, src dir)
      via `create-next-app` — verified rendering in-browser
- [x] Charting library: Recharts installed — lightweight, good React fit;
      revisit only if the residual scatter plots need more control than it offers
- [x] `.claude/launch.json` added so both dev servers (backend :8000, frontend
      :3000) can be started via the preview tooling
- [x] Verified end-to-end: backend `/api/health` returns `{"status":"ok"}`,
      frontend renders the default Next.js page with no console/server errors
- [x] ~~Decide backend data-access strategy (import vs duplicate from
      `src/`)~~ — moot now: `src/` was deleted per the earlier scope
      decision. Backend analytics code is being written fresh under
      `webapp/backend/app/`, informed by (not copied from) the validated
      analysis approach

## Phase 1 — Backend: Refactor analysis code into a service layer  ✅

- [x] Rewrote the analysis logic fresh under `webapp/backend/app/` (`data.py`,
      `solar_features.py`, `fault_model.py`, `forecast_model.py`,
      `overview.py`) — pure functions returning JSON-serializable dicts, no
      prints/saved PNGs; charts render client-side now
- [x] `as_of` parameter threaded through every computation — the fault model
      is fit once on the full known history (cached; a realistic
      "commissioning baseline," not something a real product would retrain
      per-request either), while `as_of` controls how much of that history
      is *revealed* to summary/detail views. The forecast model retrains per
      request on data <= as_of (cheap at 34 rows) — this is where the actual
      leakage discipline lives, reused directly from the original design
- [x] Caching: `data.py`/`fault_model.py`/`forecast_model.py` each cache their
      expensive computation (data load, cross-validated RF fit, daily
      aggregation) in a module-level dict keyed by plant, computed lazily on
      first request
- [x] **Verified against the original analysis's numbers as a correctness
      check**: Plant 2 total estimated revenue lost = 2850.64 here vs ≈2,851
      in the original `fault_detection.py` output — same 3 inverters flagged
      at_risk. Confirms the refactor is faithful, not just "runs without
      errors"

## Phase 2 — Backend: API endpoints  ✅

- [x] `GET /api/plants`
- [x] `GET /api/plants/{id}/timeline`
- [x] `GET /api/plants/{id}/overview?as_of=`
- [x] `GET /api/plants/{id}/inverters?as_of=`
- [x] `GET /api/plants/{id}/inverters/{source_key}?as_of=`
- [x] `GET /api/plants/{id}/forecast?as_of=`
- [x] Verified via curl: happy path for all 6 endpoints, plus edge cases —
      unknown plant (404), invalid date (400), earliest possible `as_of`
      (day 1, minimal data, doesn't crash)
- [x] **Bug found & fixed:** Starlette's JSON response rejects NaN
      (`allow_nan=False`) — the forecast history's first day has no prior day
      for `PERSISTENCE`/`CLIMATOLOGY`, producing NaN that crashed
      serialization. Fixed by converting NaN to `None` before returning.
- [x] **Tooling gotcha found:** uvicorn's `--reload` silently got stuck mid-
      reload (logged "Reloading..." but never logged a new "Started server
      process" — kept serving the old worker). Cost real debugging time
      chasing a "fix that isn't taking effect." Resolution: stop/restart the
      server fully rather than trust `--reload` after a burst of rapid edits.

## Phase 3 — Backend: Trend-based risk scoring  ✅

- [x] Aggregate per-timestamp residuals to a daily severity score per inverter
      (`_daily_severity()` in `fault_model.py`)
- [x] **Empirical check, done before committing to UI framing:** fit a linear
      trend to each Plant 2 inverter's daily severity. Result — the three
      flagged (`at_risk`) inverters all show weak correlation (0.03-0.21) and
      classify as **stable**, not worsening: chronic, consistent
      underperformance, not degradation-over-time. Confirms the UI should say
      "consistently underperforming," not force a countdown for those three.
- [x] Implemented trend classification (worsening / stable / improving) via
      `scipy.stats.linregress` per inverter, p<0.10 threshold (deliberately
      lenient given only ~34 points) plus a minimum slope magnitude so tiny
      but "significant" slopes don't get over-called
- [x] **Validated the classifier isn't a constant-output bug**: across all 22
      Plant 2 inverters, got a real mix — 18 stable, 2 improving, 2 worsening
      — so it's demonstrably capable of detecting a real trend, not just
      defaulting to "stable"
- [x] **Genuinely interesting finding, not planned for:** the 2 "worsening"
      inverters (`V94E5Ben1TlhnDV`, `oZ35aAeoifZaQzV`) are currently classified
      `healthy` by the static z-score check — trend scoring catches an early
      warning (p=0.014, projected ~49-63 days to a critical residual
      threshold) that the static status alone would completely miss. This is
      the actual product value of Phase 3, more than the flagged-inverter
      countdown I originally expected.
- [x] Wired into both `inverter_summary` (queue list) and `inverter_detail`
      (per-inverter page) — verified via curl against the running API

## Phase 4 — Frontend: Scaffold & data layer

- [ ] Next.js app setup, typed API client, global layout
- [ ] Timeline scrubber component + play/pause control — global state (e.g.
      React context) for the current `as_of` date, shared across all pages
- [ ] Loading/error states for API calls (a real product handles these, not
      just the happy path)

## Phase 5 — Frontend: Command Center page

- [ ] KPI cards: health score, today's generation vs expected, active risk
      count, tomorrow's forecast teaser
- [ ] Daily generation trend chart (actual vs expected)

## Phase 6 — Frontend: Maintenance Queue page

- [ ] Inverter list, status badges (healthy/watch/at-risk), sortable by risk
- [ ] Detail view: residual-vs-irradiance chart, plain-language diagnosis
      (reusing the bimodal-pattern insight — "pattern suggests intermittent
      tripping under high load" vs "steady degradation"), trend chart,
      estimated $ impact

## Phase 7 — Frontend: Forecast page

- [ ] Forecast vs actual chart with baselines for comparison
- [ ] Running monthly revenue projection (owners think in revenue, not kWh)

## Phase 8 — Polish

- [ ] Styling/branding pass, responsive layout
- [ ] Plain-language copywriting pass — translate stats into owner-facing
      language throughout, not just in one panel
- [ ] Empty/edge-case states (e.g. scrubber at day 1, no history yet for
      trend scoring)

## Phase 9 — Deployment (optional, only if time remains)

- [ ] Backend: Railway/Render/Fly.io
- [ ] Frontend: Vercel
- [ ] Wire production API URL, verify CORS in production
