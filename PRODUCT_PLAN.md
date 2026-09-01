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

## Phase 1 — Backend: Refactor analysis code into a service layer

- [ ] Extract reusable logic from `src/fault_detection.py`, `forecasting.py`,
      `solar_features.py`, `data_loader.py` into functions that return
      JSON-serializable dicts, not prints/saved PNGs — charts render
      client-side now
- [ ] Add an `as_of` parameter throughout so every computation can be scoped
      to "using only data up to this point" — this is what makes the
      timeline scrubber (Phase 4) actually work, and it reuses the same
      leakage discipline already built for forecasting
- [ ] Cache/precompute the expensive parts (the cross-validated expected-power
      model) — recomputing per API request would be slow; compute once at
      startup or on first request, keyed by plant

## Phase 2 — Backend: API endpoints

- [ ] `GET /api/plants` — available plants
- [ ] `GET /api/plants/{id}/timeline` — valid date range for the scrubber
- [ ] `GET /api/plants/{id}/overview?as_of=` — command-center KPIs
- [ ] `GET /api/plants/{id}/inverters?as_of=` — maintenance queue + risk scores
- [ ] `GET /api/plants/{id}/inverters/{source_key}?as_of=` — detail view data
      (residual-vs-irradiance points, diagnosis, trend)
- [ ] `GET /api/plants/{id}/forecast?as_of=` — forecast vs actual vs baselines
- [ ] Verify each endpoint via Swagger UI / curl before wiring the frontend

## Phase 3 — Backend: Trend-based risk scoring (new logic, not yet built)

- [ ] Aggregate per-timestamp residuals to a daily severity score per inverter
- [ ] **Empirical check before committing to UI framing:** does Plant 2's
      anomaly severity actually trend (worsening/improving) over the 34 days,
      or stay roughly flat? If flat, the UI should say "consistently
      underperforming," not force a countdown that isn't supported by the
      data. Check this before Phase 6.
- [ ] Implement trend classification (worsening / stable / improving) and,
      where a worsening trend is real, a rough projected inspection window
- [ ] Document the finding either way — this is exactly the kind of honest
      negative/positive result that made `tasks.md` credible

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
