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

## Phase 4 — Frontend: Scaffold & data layer  ✅

- [x] Typed API client (`src/lib/api.ts`) — one function + TS interface per
      backend endpoint
- [x] `SimulationProvider` (`src/context/SimulationContext.tsx`) — global
      `as_of` state: fetches the plant's date range once, exposes
      `currentDate`/`currentIndex`, play/pause with 1s auto-advance. Hardcoded
      to Plant 2 (single-plant v1 scope decision)
- [x] `TimelineScrubber` component — range slider + play/pause, wired into
      root `layout.tsx` so it's global across all future pages
- [x] Loading/error states for the timeline fetch and the placeholder page's
      overview fetch
- [x] **Bug found via the end-to-end wiring check itself**: `enumerateDates`
      mixed local-time `Date` construction with `.toISOString()`, which
      shifts every date by the browser's UTC offset — the scrubber defaulted
      to 2020-06-16 instead of the real last day 2020-06-17. Fixed with pure
      `Date.UTC()` arithmetic throughout. Worth remembering: this exact
      footgun (local-time construct + UTC-string read) is an easy one to
      reintroduce later.
- [x] Verified in-browser end-to-end: scrubber drag updates `as_of` and
      triggers a real API call (confirmed day-1 shows 1-point trend, 2 active
      risks matching earlier backend testing); Play button auto-advances the
      index (~1/sec) and toggles to "Pause" correctly; zero console errors

## Phase 5 — Frontend: Command Center page  ✅

- [x] KPI cards (`KpiCard.tsx`): health score, today's generation vs expected
      (with delta), active risk count (+ watch/healthy breakdown), tomorrow's
      forecast, revenue at risk — 5 cards, color-toned (green/amber/red) by
      severity
- [x] Daily generation trend chart (`DailyTrendChart.tsx`, Recharts) — actual
      vs expected lines, updates live with the scrubber
- [x] **Bug found & fixed (dark-mode collision):** create-next-app's
      boilerplate `globals.css` auto-switches to a dark background on
      `prefers-color-scheme: dark`, which collided with the light-themed KPI
      cards — page headings were nearly invisible against a black background.
      Fixed by making the light theme deliberate (removed the automatic dark
      variant) rather than inheriting an accidental one; real dark-mode
      support can be designed properly later if wanted.
- [x] **Bug found & fixed (Recharts + live replay):** the chart's default
      line-draw entrance animation (~1.5s) collides with the scrubber's 1s
      auto-advance during Play — every tick re-triggered the animation, so
      the chart never looked "settled" and flickered a partial line during
      any rapid scrubbing/Play use. Fixed with `isAnimationActive={false}`.
      Root-caused by testing the actual Play interaction, not just a static
      screenshot — a static check would have missed this.
- [x] Verified in-browser: scrubbing to an early date correctly shows a
      shorter trend line, fewer flagged inverters, and a real (non-null)
      tomorrow's-forecast number; Play advances smoothly with the fix; no
      real console errors (only harmless HMR websocket noise from the
      sandboxed preview environment)

## Phase 6 — Frontend: Maintenance Queue page  ✅

- [x] Inverter list (`/maintenance`) — status badges (healthy/watch/at_risk),
      trend badges, sorted by risk (backend already returns z-score sorted)
- [x] Detail view (`/maintenance/[sourceKey]`) — residual-vs-irradiance
      scatter chart, daily severity trend chart, stat cards (mean deviation,
      z-score, est. kWh/revenue lost), plain-language diagnosis
- [x] Diagnosis text (`lib/diagnosis.ts`) is rule-based off status + trend +
      projected_days_to_critical — explicitly not a stronger claim than the
      numbers already shown elsewhere (consistent with the Phase 3 honesty
      framing), 6 message variants covering the status x trend combinations
- [x] **Backend refactor along the way**: `inverter_detail` didn't originally
      return status/z_score (only `inverter_summary` did) — needed for the
      diagnosis text, so extracted a shared `_inverter_row()` helper so both
      endpoints compute status/trend identically rather than duplicating logic
- [x] Added `NavBar` (Overview / Maintenance) to the root layout, verified
      routing works both directions
- [x] Verified in-browser end-to-end: queue list shows correct counts/sort;
      clicked into the "worsening but currently healthy" inverter found in
      Phase 3 (`V94E5Ben1TlhnDV`) — diagnosis text, stats, and both charts all
      render correctly and the plain-language warning reads exactly as
      intended (see PRODUCT_PLAN.md Phase 3 for why this finding matters);
      no real console errors

## Phase 7 — Frontend: Forecast page  ✅

- [x] Backend enhancement: added `forecast_range` (10th-90th percentile
      spread across the Random Forest's individual trees — a lightweight,
      honest uncertainty band, explicitly not a calibrated confidence
      interval) and `monthly_revenue_projection` (last 7 days' actual average
      x 30 x the same illustrative tariff used elsewhere, imported from
      `fault_model` rather than duplicated)
- [x] Forecast vs actual chart with baselines (`ForecastChart.tsx`) — actual,
      persistence, and climatology as continuous lines, tomorrow's forecast
      rendered as an isolated highlighted dot via a separate `dataKey` with
      `connectNulls={false}` (renders as a standalone point, not connected to
      the history lines — visually distinct on purpose)
- [x] KPI cards: tomorrow's forecast (with range), 30-day revenue projection
- [x] Added `/forecast` to nav
- [x] Verified in-browser: at the dataset's last day, correctly shows "No
      data yet" for tomorrow (honest, since there's no next-day data to
      forecast against); scrubbing back one day shows a real forecast number,
      range, and the isolated green dot rendering correctly on the chart; no
      console errors at all this time

## Phase 8 — Polish  ✅

- [x] Copywriting pass on the inverter detail page: removed raw `z_score` and
      `p_value`/`slope` from the primary stat cards (meaningless to a plant
      owner), renamed "Mean deviation" → "Avg. output vs expected" with units
      and red/green coloring, demoted the statistical detail to a small muted
      footnote line for anyone who wants it. Same rename + units + color
      applied to the Maintenance Queue list's column.
- [x] **Real bug found via day-1 edge-case testing, not hypothetically**: the
      diagnosis text for `insufficient_data` trend fell through to the
      "stable" branch's language ("Consistently... underperforming"), which
      overclaims — a single day of data isn't "consistent" anything. Fixed
      with an explicit `insufficient_data` branch that's honest about not
      having enough history yet ("not enough history yet to tell whether
      this is a persistent issue or normal early variation")
- [x] **Real bug found via mobile testing, not hypothetically**: the
      Maintenance Queue table's `overflow-hidden` wrapper was silently
      clipping the last two columns off-screen on mobile with no way to
      access them — not just visually cramped, actually inaccessible data.
      Fixed with `overflow-x-auto` + `min-w` so it scrolls instead of
      clipping; verified scrollable via `scrollWidth > clientWidth` check,
      not just a screenshot
- [x] **Real bug found via mobile testing**: the nav bar's "Solar Plant
      Manager" brand text wrapped across 3 lines next to the nav links on
      a 375px viewport. Fixed by hiding the brand text below `sm:` — the nav
      links are what matters for actual use
- [x] Verified in-browser at mobile width (375x812) across all 4 pages
      (Overview, Maintenance list, Maintenance detail, Forecast) — KPI card
      grids, charts (ResponsiveContainer), and stat card grids all reflow
      correctly; only the two bugs above needed fixing
- [x] Verified day-1 (minimal-data) edge case across all pages: Command
      Center chart renders a single point without crashing, Forecast
      correctly shows "No data yet" (genuinely not enough training data yet,
      not a bug), Maintenance Queue trend badges show "—" for
      insufficient_data rather than a misleading trend claim
- [x] Confirmed zero real console errors throughout (only harmless HMR
      websocket noise from the sandboxed preview environment, not present in
      a normal dev setup)
- [ ] Not done (documented, not silently skipped): custom favicon/logo —
      still the default Next.js icon. Minor, cosmetic, low priority relative
      to the functional/UX fixes above.

## Phase 9 — Deployment (optional, only if time remains)

- [ ] Backend: Railway/Render/Fly.io
- [ ] Frontend: Vercel
- [ ] Wire production API URL, verify CORS in production

## Phase 10 — Authentication (Supabase)  ✅

Added after the original 9 phases, as part of designing the onboarding flow.
Real accounts (not cosmetic personalization) — user set up a Supabase
project and provided the URL + anon key (anon key is designed to be public/
client-safe per Supabase's own docs; protection is via Row Level Security,
not key secrecy — safe to use directly, unlike a `service_role` key).

**Scope decision**: frontend-only auth for now. The FastAPI backend stays
as-is (no JWT verification) since real per-user plant data ("data
connection") is explicitly deferred — backend auth should be designed
together with that, not bolted on separately now.

- [x] `npm install @supabase/supabase-js`; credentials in `.env.local`
      (gitignored by create-next-app's default `.env*` rule)
- [x] `lib/supabase.ts` — client singleton
- [x] `context/AuthContext.tsx` — session state via `onAuthStateChange`,
      `signUp`/`signIn`/`signOut` methods
- [x] `components/AuthGate.tsx` — redirects to `/login` when unauthenticated
- [x] **Restructured routing** into a `(dashboard)` route group so protected
      pages (Overview/Maintenance/Forecast) share `AuthGate` + `SimulationProvider`
      + `NavBar` + `TimelineScrubber`, while `/login` shares only the root
      layout (fonts + `AuthProvider`) — no scrubber/nav on the login screen
- [x] `/login` page combines welcome/value-prop copy with a sign in/up toggle
      form (per the "no separate tour" decision — one screen, not three)
- [x] Sign-out added to `NavBar`
- [x] **Verified against the real Supabase project, not mocked:**
  - Unauthenticated access to `/` and directly to `/maintenance` both
    correctly redirect to `/login`
  - Sign-up with `@example.com` correctly rejected by Supabase (blocks
    known-fake/reserved domains) — real validation, real error surfaced
  - Sign-up with a real-format address succeeds, correctly shows "check your
    email" (Supabase requires email confirmation by default — no session
    issued yet)
  - Sign-in attempt on that unconfirmed account correctly blocked with
    "Email not confirmed"
  - Two legitimate 400s in the network log (the two rejected requests
    above) — not bugs, expected responses for intentionally-invalid test
    inputs
- [ ] **Not fully verified**: the confirmed-session → dashboard path, since
      completing it requires clicking a real confirmation-email link, which
      needs the account owner. Everything up to that point (signup, error
      handling, redirect gating) is confirmed working; the remaining link is
      the email-confirm step itself plus the post-confirm sign-in redirect —
      should be tested once you've clicked the confirmation link.
- [ ] Worth deciding: Supabase's "Confirm email" requirement adds friction
      for demo/portfolio use — could disable it in Supabase's dashboard
      (Authentication → Providers → Email) if faster iteration matters more
      than the (minimal, for a demo) security value here.

## Phase 11 — Plant Setup (Onboarding Step 2)  ✅

After signup, a logged-in user with no configured plant is sent to
`/setup-plant` before the dashboard is reachable at all.

**Field design — split into two tiers, decided in brainstorm**:
- **Tier 1 (actually wired to computation)**: plant name, latitude/longitude,
  electricity tariff. Location was previously hardcoded in
  `solar_features.py` (18N/80E) and tariff in `fault_model.py`
  (`TARIFF_PER_KWH = 4.0`) — this is the first step toward making those
  real per-plant inputs instead of constants (not yet wired into the
  backend itself — see open item below).
- **Tier 2 (realistic, decorative until data connection exists)**: capacity
  (kW), panel count, inverter count, module type, module wattage, tilt,
  azimuth, commissioning date, area — collected in full per user's choice,
  stored for future use, explicitly not read by any computation yet.

**Scope decisions from brainstorm**:
- Location entered as plain lat/lon number fields (no geocoding/map picker)
- Full Tier 2 field set collected now, not deferred
- The newly configured plant is explicitly NOT connected to the Plant 2 demo
  dataset — user wants to test that wiring later, separately
- Post-setup lands on a plain confirmation screen ("configured, live
  monitoring coming soon"), not the dashboard

**Built**:
- [x] `webapp/supabase/001_plants.sql` — `plants` table + RLS policies
      (each user sees only their own row via `auth.uid() = user_id`) — user
      needs to run this in the Supabase SQL Editor (no admin access from
      the app, only the client-safe anon key)
- [x] `lib/plants.ts` — `getMyPlant()` / `createPlant()` against Supabase
- [x] `context/PlantContext.tsx` — loads the current user's plant once
      authenticated, exposes `plant`/`loading`/`refetch`
- [x] `AuthGate` extended: authenticated + no plant → redirect to
      `/setup-plant` (previously: authenticated was the only check)
- [x] `/setup-plant` form — required Tier 1 fields with validation
      (lat -90..90, lon -180..180), optional Tier 2 fields in a separate
      "(optional)" section, shows a confirmation state instead of the form
      if a plant already exists (prevents accidental duplicate rows — no
      DB uniqueness constraint added, relies on this client-side check)
- [x] Verified: unauthenticated access to `/setup-plant` redirects to
      `/login`; page compiles with no console errors beyond the known
      harmless HMR noise

**Fully verified end-to-end against the real Supabase project, not mocked**,
once the SQL migration was run and the test account's email confirmed:
- Sign in → `AuthGate` correctly detected authenticated-but-no-plant and
  redirected straight to `/setup-plant` (not the dashboard)
- Submitted the form (name, lat/lon, tariff; optional fields left blank) →
  confirmation screen shown immediately
- **Reloaded the page** — confirmation screen reappeared (fetched fresh from
  the DB via `PlantContext`, not just leftover in-memory state), proving
  persistence actually works, not just the optimistic UI
- **Queried the row directly via the Supabase REST API with the user's own
  access token** — all Tier 1 fields correct, all untouched Tier 2 fields
  correctly `null`, scoped to the right `user_id`
- **Confirmed RLS is doing real work, not just present**: the same query
  with only the anon key (no user token) returned an empty array — the row
  exists but is invisible without the owning user's session

**Explicitly not done yet**: wiring the backend to actually use a plant's
stored lat/lon/tariff instead of the hardcoded constants — that's a
FastAPI change (accept plant params, or look them up) that makes sense to
do once there's a real per-user data flow to attach it to, not before.

## Phase 12 — Real Weather Ingestion  ✅

First half of "data connection" (the second half — synthetic panel-output
generation from this weather — is separate, deliberately deferred). Full
design/reasoning in the approved plan at the time
(`~/.claude/plans/okay-i-want-to-resilient-church.md`); summary here.

**Decisions from brainstorm**: weather-fetching logic lives in the FastAPI
backend (reuses `pvlib`, sets up the foundation for later combining weather
+ physics into synthetic output); ingestion is triggered by client-side
polling while the app is open (real scheduled/background ingestion is
explicit future work — a known limitation, not an oversight); pipeline
only, no UI yet.

**Built**:
- [x] `app/weather.py` — `fetch_current_weather()` (Open-Meteo, free, no API
      key: temperature, cloud cover, GHI/DNI/DHI) + `get_clearsky_ghi()`
      (same `pvlib.location.Location(...).get_clearsky()` approach as
      `solar_features.py`, but parameterized per-request instead of that
      file's hardcoded Plant 1/2 constants — kept as a separate function
      rather than modifying the verified existing one). Combined into
      `clearsky_index`, null-gated below 5° solar elevation (same day/night
      guard pattern as `solar_features.py`)
- [x] `GET /api/weather/current?lat=&lon=` — stateless, no DB writes on the
      backend side; storage happens in Supabase from the frontend, keeping
      the backend Supabase-unaware (no new secrets needed there)
- [x] `webapp/supabase/002_weather_readings.sql` — `weather_readings` table,
      `unique(plant_id, recorded_at)` so repeated polling near the same
      Open-Meteo update cycle doesn't spam duplicates, RLS via a join
      through `plants.user_id` (this table has no direct `user_id` column)
- [x] `lib/weather.ts` — fetch from backend, upsert to Supabase with
      `ignoreDuplicates`
- [x] `components/WeatherIngestion.tsx` — renders nothing, mounted in root
      layout inside `PlantProvider` so it runs on every page once a plant
      exists; fetches immediately on mount then every 15 minutes; catches
      and logs errors without crashing the app

**Verified against real services throughout, not mocked**:
- Backend endpoint tested at both a nighttime location (Pune, ~2:30am
  local — correctly returned GHI=0, `clearsky_index: null`) and a
  simultaneous daytime location (Auckland — GHI=315 W/m², clear-sky max
  383.8 W/m², `clearsky_index: 0.821`, all physically consistent with the
  56% cloud cover reported)
- Before the SQL migration was run: confirmed the component fails
  gracefully (a caught, logged warning — `PGRST205 table not found` — not a
  crash)
- After the migration: confirmed a real row lands in `weather_readings`
  matching the backend's output, queried directly via the Supabase REST API
  using the authenticated user's own access token
- Confirmed RLS: the identical query with only the anon key returns nothing
- Confirmed the dedup constraint: reloaded the page (triggering a second
  ingestion cycle within the same clock-hour), row count stayed at 1 rather
  than duplicating

**Explicitly not done yet**: the synthetic panel-output module (weather →
physical model → fake-but-grounded power readings) — that's the deferred
"hardware part" from the brainstorm, a separate next step. Also not done:
real scheduled ingestion independent of a browser tab being open.
