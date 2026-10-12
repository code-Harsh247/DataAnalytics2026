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

## Phase 13 — Synthetic Panel-Output Generation  ✅

The deferred "hardware part": since there's no real inverter hardware,
there are no real power readings, but the numbers can still be grounded in
real physics (the real weather from Phase 12 + a standard PV performance
model) rather than made up outright. Full design in the approved plan at
the time (`~/.claude/plans/okay-i-want-to-resilient-church.md`); summary
here.

**Decisions from brainstorm**: fault injection is stateful (persists a
realistic multi-hour window, tracked in the DB) rather than re-rolled every
tick; virtual inverters are proper DB entities (an `inverters` table), not
just derived labels.

**Physical model** (`app/synthetic_generation.py`, sibling to `weather.py`):
1. Plane-of-array irradiance via `pvlib.irradiance.get_total_irradiance`,
   using the plant's actual `tilt_degrees`/`azimuth_degrees` — the first
   real use for those two Tier 2 onboarding fields (previously stored,
   unused)
2. Cell temperature via a standard NOCT model
3. DC power: `capacity_kw × (POA/1000) × (1 + temp_coeff×(cell_temp−25))`,
   temp_coeff ≈ −0.4%/°C — the same physical relationship the *original
   Kaggle-data analysis* found empirically (module temp was a strong
   predictor of underperformance there too)
4. AC power: DC × 97% inverter efficiency

**Fallback chain for optional setup fields** (`resolvePlantDefaults` in
`lib/generation.ts`): `capacity_kw` derived from `panel_count ×
module_wattage_w` if both given, else a 5kW small-system default;
`tilt_degrees` defaults to site latitude (standard fixed-tilt convention);
`azimuth_degrees` defaults to 180° (south-facing) in the northern
hemisphere or 0° (north-facing) in the southern — real design convention,
not an arbitrary guess; `inverter_count` defaults to 4.

**Multi-inverter + fault modeling**:
- `webapp/supabase/003_generation.sql` — `inverters` (persistent
  `base_efficiency_factor` per inverter, ~0.96-1.02 spread, assigned once
  at creation so healthy variance is stable over time, not re-randomized
  every tick), `inverter_faults` (stateful episodes: `severity` +
  `[started_at, ends_at)` window, no explicit "closing" needed — a fault
  just stops applying once `ends_at` passes), `generation_readings`. RLS on
  the two-levels-removed tables (`inverter_faults`, `generation_readings`)
  checks ownership via a join through `inverters` → `plants.user_id`.
- `lib/generation.ts`: `getOrCreateInverters` lazily provisions an
  plant's inverters on first tick (using the resolved `inverterCount`
  default/input); each tick, currently-fault-free inverters get a ~4%
  chance of starting a new 2-8 hour fault episode (severity 15-50%)

**Orchestration**: renamed `WeatherIngestion.tsx` → `SimulationIngestion.tsx`
— now chains weather-fetch → weather-store → generation-compute →
generation-store in one tick, so a single tick produces one physically
consistent weather+generation snapshot instead of two independently-timed
fetches that could drift apart. (Renaming an already-verified, committed
component was a deliberate choice over adding a second independently-polling
component, specifically to preserve that consistency guarantee.)

**Verified thoroughly, including hand-checking the physics**:
- Backend endpoint tested directly: manually verified the POA transposition,
  NOCT cell-temp formula, and per-inverter efficiency/fault multipliers all
  compute to the exact expected values by hand, for both a daytime case
  (real Auckland weather) and a nighttime case (zero irradiance in Pune —
  confirmed zero power, cell temp correctly equals ambient with no solar
  heating, no divide-by-zero or negative-power bugs)
- Frontend compiles cleanly; confirmed the component rename didn't break
  anything after a transient Turbopack cache issue (cleared `.next`,
  confirmed clean via direct DOM/state inspection rather than trusting a
  console-log buffer that turned out to hold stale entries from before the
  rename)
- End-to-end against the real Supabase project: first tick correctly
  lazy-created 4 inverters (`inverter_count` was left blank at setup, so
  the default applied) with real distinct efficiency values; a matching
  generation reading landed for each, correctly showing zero output since
  it's genuinely nighttime in Pune right now — not a bug, the honest
  correct answer for that time of day
- RLS confirmed on all three new tables (anon-only queries return nothing)
- Dedup confirmed: a second tick left inverter count and reading count
  unchanged rather than duplicating
- **Fault-injection wiring specifically verified** (hadn't organically
  triggered yet in just two ticks — ~4% per inverter per tick): manually
  inserted a fault row, then independently replicated the app's exact
  active-fault detection query and confirmed it correctly found the fault —
  combined with the earlier hand-verified severity math, this confirms the
  full fault path end-to-end without needing to wait for the random trigger

**Explicitly not done yet**: actually running this synthetic data through
the fault-detection/forecasting models built for the Plant 1/2 demo — that
needs enough accumulated history first, a real next step once ingestion has
been running a while. Also not done: real scheduled ingestion (same known
limitation as Phase 12).

## Phase 14 — Wire Up the Remaining Unused Setup Fields  ✅

Prompted by directly auditing which of the plant-setup fields actually drove
computation vs. were just stored. Answer at the time: `module_type`,
`commissioning_date`, `area_sqm`, and `tariff_per_kwh` were all collected
but never read anywhere. This phase makes each one genuinely load-bearing.

**`module_type` → real temperature coefficient**: replaced the single fixed
`TEMP_COEFFICIENT` constant in `synthetic_generation.py` with a per-plant
value resolved from a lookup table in `lib/generation.ts`
(Monocrystalline −0.35%/°C, Polycrystalline −0.41%/°C, Thin-film −0.25%/°C —
thin-film genuinely tolerates heat better in reality, this isn't an
invented spread). Backend stays a pure calculator; the lookup lives in the
frontend alongside the other config-resolution logic.

**`commissioning_date` → panel degradation**: ~0.5%/year (standard for
crystalline silicon), floored at 70% so an old/bad date can't zero out
output. No date → no degradation applied (honest "unknown" rather than
guessing an age).

**`area_sqm` → third tier in the capacity fallback chain**: `capacity_kw`
→ `panel_count × module_wattage_w` → `area_sqm × 150 W/m²` (installed-area
density) → 5kW default. Also added a non-blocking plausibility check: if
both capacity and area are given and imply wildly different values (>3x),
logs a warning rather than silently accepting an inconsistent configuration.

**`tariff_per_kwh` → real revenue per reading**: new `revenue_per_interval`
column on `generation_readings` (`webapp/supabase/004_generation_revenue.sql`),
computed as `ac_power_kw × 0.25h × tariff_per_kwh` at storage time.

**Verified in three independent layers**:
1. Backend physics, hand-checked via direct API calls: monocrystalline vs.
   thin-film coefficients produce different power under identical hot-day
   conditions (thin-film correctly higher, matching real-world behavior),
   and a 0.9 degradation factor correctly scales output down by exactly 10%
2. Frontend resolution logic verified by replicating `resolvePlantDefaults`
   exactly in the browser console against the real (deliberately
   reconfigured) test plant — capacity from area (50 sqm → 7.5kW), thin-film
   coefficient, and a 3-year degradation factor (≈0.985) all matched
   hand-calculated expected values exactly
3. End-to-end against the real Supabase project: PATCHed the test plant to
   exercise all three new paths at once (nulled `capacity_kw`/`panel_count`/
   `module_wattage_w`, set `area_sqm`, `module_type`, `commissioning_date`),
   triggered a real tick, confirmed a genuinely new row landed (not blocked
   by dedup) with `revenue_per_interval: 0` correctly computed, while the
   pre-migration rows correctly show `null` for that column (they predate
   it, not a bug) — and confirmed the manually-inserted fault from Phase 13
   is still being correctly detected and applied on this later tick too

**Known limitation, stated plainly**: none of this was observed producing
*non-zero* revenue/temp-coefficient/degradation effects through the live
pipeline, since it's nighttime at the test plant's location — only the
direct backend physics tests (layer 1) exercised real daylight conditions.
The orchestration and math are independently proven correct; seeing them
combine into a non-zero number live would need either a daytime plant or
waiting for one.

## Phase 15 — Real-Plant Dashboard  ✅

Closes the biggest visible gap from Phases 10-14: a user could sign up,
configure a plant, and watch data silently accumulate in Supabase forever
with nothing to look at — `/setup-plant` just showed a static "coming
soon" message once a plant existed. This phase makes that data visible.

**Deliberately deferred, per explicit decision**: the ML/data-analytics
layer (expected-power model, anomaly detection, forecasting) discussed
separately — this phase is pure data visualization pulled directly from
Supabase, no backend compute involved. That decision (deterministic
baseline vs. trained ML, plus a historical-backfill idea to get enough
data for real training/validation against known synthetic fault labels)
is parked for later, not abandoned.

**Where it lives**: extended `/setup-plant`'s "already configured" branch
— previously static text, now renders `PlantDashboardView` when a plant
exists. Kept as the same route rather than adding a new one to avoid
churn; still a reasonable place for "your plant's page" conceptually.
Deliberately separate from the (dashboard) route group, which still shows
the unrelated Plant 1/2 historical demo (per the earlier explicit decision
not to connect a new plant to that dataset).

**Built** (`lib/plantDashboard.ts`, `components/PlantDashboardView.tsx` +
two new chart components):
- KPI cards: energy-to-date and revenue-to-date (summed client-side over
  all readings — fine at current data volume, would need a real aggregate
  query or materialized view at scale, not attempted here), active fault
  count, latest weather conditions
- Two history charts (real GHI over time, total plant AC power over time —
  summed across inverters per timestamp)
- Per-inverter status table (latest reading, fault status, timestamp)
- A low-data notice when fewer than 5 readings exist yet, rather than
  silently showing sparse/empty-looking charts with no explanation

**Verified against the real Supabase project, live, not mocked**: loaded
the actual dashboard for the real test plant and confirmed every number
matches what direct REST queries showed in earlier phases (1/4 active
faults — the manually-inserted test fault from Phase 13, still correctly
showing as active; 0 kWh/revenue — correct for all-nighttime data so far).
Reloaded and confirmed a **genuinely new tick** (22:00 UTC) appeared
automatically, proving this reads live data, not a cached snapshot.

---

## Hackathon MVP — Remaining Work (Abhinav + Harsh)

Scope cut to what a hackathon MVP needs. The ML pipeline is the most
important and most time-heavy part, so it is split across **both**
teammates as a multi-model comparison. Abhinav owns the data foundation,
evaluation harness, API, and two models; Harsh owns one model plus the
frontend, demo flow, and deployment.

**This section is written so the two of us can work with as little contact
as possible.** Everything needed to start — contracts, file ownership,
commands, and what "done" means — is here. If something isn't covered,
follow the rules in "Working agreement" rather than waiting on a reply.

---

### Working agreement (read first)

1. **The contracts below are frozen.** Build against them exactly. If a
   change is truly needed, make it **additive only** (new optional field /
   new column — never rename or remove), and log it in the
   "Contract change log" at the bottom of this section in the same commit.
2. **File ownership — only edit files you own.** Shared files are listed
   explicitly; touch them only as described.

   | Owner | Files |
   |---|---|
   | Abhinav | `webapp/backend/app/backfill.py`, `app/models/base.py`, `app/models/__init__.py`, `app/models/evaluate.py`, `app/models/random_forest.py`, `app/models/isolation_forest.py`, `app/analysis.py` (new), the `/api/plants/analyze` route in `main.py`, `requirements.txt`, `data/backfill/` |
   | Harsh | `app/models/gradient_boosting.py`, everything under `webapp/frontend/`, deployment config files, the CORS block in `main.py`, `README.md` |
   | Shared (append-only) | `PRODUCT_PLAN.md` — tick your own checkboxes, append to the change log / status log; `FINDINGS.md` — model results, decisions and why, bugs found |

   Models are auto-discovered from `app/models/`, so adding a model never
   requires editing anyone else's file.
3. **Git**: work on your own branch (`abhinav/ml`, `harsh/frontend` —
   `harsh/gb-model` optional), rebase on `main` often, merge to `main` when
   a checkbox's "done when" is met. Push at least once a day even if
   unfinished, so the other person can see progress.
4. **Status without messaging**: tick checkboxes here and add a one-line
   dated entry to the "Status log" when you merge something the other person
   depends on.
5. **Blocked?** Never wait. Every dependency below has a fallback (mock
   data, sample dataset, or regenerate it yourself with the script).
6. **Sync points** (the only times a real conversation is needed): the
   integration step and the final demo rehearsal. Everything else is async.

---

### Contract 1 — Dataset (backfill output)

**How the data is obtained** — no one needs to send data to anyone; anyone
can regenerate it:

1. Real **historical weather** for the plant's lat/lon from Open-Meteo's
   archive API (free, no key, fixed start/end dates → reproducible;
   ERA5 data trails real time by ~5 days, so the end date must be ≥6 days ago)
2. **Physics** (same as `synthetic_generation.py`, vectorized): pvlib
   plane-of-array irradiance → NOCT cell temperature → temperature derating
   → degradation → inverter efficiency
3. **Per-inverter realism**: persistent efficiency spread, slow soiling
   drift, measurement noise (so models can't just rediscover the formula)
4. **Fault injection with labels**: random multi-hour derate episodes;
   every row carries `is_fault` / `fault_severity` as ground truth
5. Saved as CSV + a `.meta.json` with the exact arguments used

```bash
cd webapp/backend
.venv/bin/python -m app.backfill --lat 18.0 --lon 80.0 \
    --start 2026-09-01 --end 2026-09-30 --seed 42 \
    --out data/backfill/sample_plant.csv
```

Same arguments + same seed → identical file on both machines.
**Canonical dataset** for all model comparison: `data/backfill/sample_plant.csv`
(committed). Use it for every reported number so results are comparable.

**Schema** — one row per inverter per **hour** (UTC), 4 inverters × 720
hours = 2,880 rows:

| column | type | meaning |
|---|---|---|
| `timestamp` | datetime UTC | end of the hourly interval |
| `inverter` | str | `INV-1` … `INV-4` |
| `ghi`, `dni`, `dhi` | float W/m² | real irradiance (Open-Meteo) |
| `poa_irradiance` | float W/m² | irradiance on the tilted panels (pvlib) |
| `air_temp`, `cell_temp` | float °C | ambient, estimated panel temperature |
| `wind_speed` | float km/h | real |
| `cloud_cover` | int % | real |
| `solar_elevation` | float ° | sun height, mid-interval |
| `is_daylight` | bool | `solar_elevation > 5°` |
| `dc_power_kw`, `ac_power_kw` | float | synthetic **observed** output (faults + noise applied) |
| `is_fault` | bool | **label** — never a model input |
| `fault_severity` | float | **label** — fraction of output lost, 0 when healthy |

### Contract 2 — Model interface

Defined in `webapp/backend/app/models/base.py` (full docstring + a worked
example there). One file per model, one `AnomalyModel` subclass each:

```python
class MyModel(AnomalyModel):
    name = "gradient_boosting"            # unique, snake_case
    def fit(self, train: pd.DataFrame) -> None: ...
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        # return df + expected_kw (NaN if N/A), anomaly_score (higher = worse), flagged (bool)
```

Rules: label columns are stripped by the harness before `fit`/`predict`;
power-predicting models must not use `ac_power_kw`/`dc_power_kw` as
features (use `WEATHER_FEATURES` from `base.py` + `inverter`); night rows
are passed in but only daylight rows are scored.

**Evaluation** — same split and metrics for everyone:

```bash
.venv/bin/python -m app.models.evaluate --data data/backfill/sample_plant.csv
.venv/bin/python -m app.models.evaluate --data data/backfill/sample_plant.csv --model gradient_boosting
```

- Split: first 70% of timestamps train, last 30% test (time order, no shuffle)
- Detection: precision / recall / F1 of `flagged` vs `is_fault`, daylight rows only
- Power fit: R² / MAE of `expected_kw` vs `ac_power_kw` on healthy daylight rows
- **Baseline to beat**: `baseline_ratio` (one plant-wide power/irradiance
  ratio, flag at >12% below). On the first draft of the dataset it scored
  F1 ≈ 0.99, so the dataset was made harder: fault severity 5–40%, 3%
  measurement noise, a shared ±6% site-irradiance error (reanalysis weather ≠
  on-site sun), and unlabeled 1–2h partial-shading dips as false-alarm bait.
- **Shared helpers in `base.py`** (use them, don't copy them):
  `add_peer_features(df)` → `peer_median_kw` (median output of the *other*
  inverters at the same hour — the strongest single feature, because it
  absorbs the site-irradiance error) and `smooth_daylight_scores(df)`
  (centered 3-hour rolling median of `anomaly_score` per inverter).
- **Undefined metrics are `None`**, not 0 (no faults in the test window →
  no recall/F1; a model that flags nothing → no precision).
- **Checking across seeds**: one test window has only ~35 faulted hours, so
  a single run is noisy. Before claiming one model beats another, compare
  mean F1 over seeds 1–8 (see "Current results").

**Current results** (canonical dataset, seed 42 / mean over seeds 1–8):

| model | owner | F1 (seed 42) | mean F1 (8 seeds) | precision | recall | R² |
|---|---|---|---|---|---|---|
| `baseline_ratio` | shared | 0.610 | 0.638 | 0.58 | 0.73 | 0.974 |
| `random_forest` | Abhinav | 0.675 | **0.705** | 0.70 | 0.72 | 0.988 |
| `isolation_forest` | Abhinav | 0.667 | 0.628 | 0.73 | 0.57 | — |
| `gradient_boosting` | Harsh | 0.675 | 0.677 | 0.73 | 0.64 | 0.987 |

Takeaways so far: the expected-power model (RF) clearly beats physics-only
and label-free detection; Isolation Forest is the most precise but misses
the milder faults. Faults below ~10% severity sit inside the noise floor and
are effectively undetectable by any model — expected, not a bug.

### Contract 3 — API

`POST /api/plants/analyze` — stateless; the backend fetches weather,
generates the dataset in memory, trains every model, returns results. No
Supabase writes from the backend.

```jsonc
// request — fields map 1:1 from resolvePlantDefaults() in lib/generation.ts
{ "lat": 18.0, "lon": 80.0, "capacity_kw": 7.5,
  "tilt_degrees": 18, "azimuth_degrees": 180,
  "temp_coefficient": -0.0035, "degradation_factor": 0.985,
  "inverter_count": 4, "tariff_per_kwh": 4.0,
  "days": 30,                     // optional, default 30, min 21, max 90
  "model": "random_forest" }      // optional, default = best F1

// response 200
{
  "model": "random_forest",
  "period": { "start": "2026-09-01T00:00:00Z", "end": "2026-09-30T23:00:00Z",
              "test_start": "2026-09-21T23:00:00Z",
              "test_fault_hours": 35 },  // 0 → metrics are null, say so in the UI
  "series": [   // plant total per hour (summed over inverters), test window only
    { "timestamp": "2026-09-25T06:00:00Z", "actual_kw": 3.1,
      "expected_kw": 3.4, "flagged": false, "true_fault": false } ],
  "inverters": [
    { "label": "INV-1", "flagged_hours": 12, "true_fault_hours": 10,
      "est_kwh_lost": 4.2, "est_revenue_lost": 16.8,
      "status": "healthy" | "warning" | "critical" } ],
  "comparison": [   // every registered model, same test window
    // sorted by f1 desc; precision/recall/f1 may be null (see test_fault_hours)
    { "model": "random_forest",    "precision": 0.88, "recall": 0.81, "f1": 0.84, "r2": 0.97, "mae_kw": 0.05 },
    { "model": "isolation_forest", "precision": 0.70, "recall": 0.75, "f1": 0.72, "r2": null, "mae_kw": null } ],
  "totals": { "energy_kwh": 812.0, "revenue": 3248.0 }
}
// series: `expected_kw` is null for models without a power model (isolation_forest)
// errors: 400 unknown model, 422 invalid/missing fields (FastAPI validation,
//         `detail` is a list), 502 weather provider failure — body { "detail": ... }
```

Status rule: `critical` if flagged_hours ≥ 10% of daylight test hours,
`warning` if ≥ 3%, else `healthy`. `est_kwh_lost` = Σ max(expected − actual, 0)
over flagged hours (peer median stands in for expected when a model has no
power model); revenue = kWh × tariff. Measured runtime: ~2 s. Default
model = best F1, or `random_forest` when F1 is unavailable. Results are
deterministic per plant (fixed seed), so re-running gives the same answer.

**Run it locally**: `cd webapp/backend && .venv/bin/uvicorn app.main:app --reload --port 8000`

---

### Abhinav — data foundation + 2 models + API

Order matters: items 1–2 unblock Harsh's model work, so they ship first.

- [x] Local backend setup (venv on Linux, `requirements.txt` installs clean)
- [x] **1. Backfill script + canonical dataset** (`app/backfill.py`,
      `data/backfill/sample_plant.csv`) — baseline F1 0.61
- [x] **2. Model interface + evaluation harness** (`app/models/base.py`,
      `__init__.py`, `evaluate.py`, `baseline_ratio.py`)
- [x] **3. Model 1 — Random Forest** (`random_forest.py`): predict healthy
      `ac_power_kw` from weather features + inverter, flag when residual
      ratio exceeds a threshold tuned on the train window.
      *Done when*: beats baseline F1 in `evaluate`
- [x] **4. Model 2 — Isolation Forest** (`isolation_forest.py`):
      unsupervised on weather + power + power/poa ratio, daylight rows;
      `expected_kw` = NaN. *Done when*: appears in `evaluate` output
- [x] **5. `/api/plants/analyze`** (`app/analysis.py` + route) matching
      Contract 3, wired to every registered model.
      *Done when*: `curl -X POST localhost:8000/api/plants/analyze -H 'Content-Type: application/json' -d '{"lat":18,"lon":80,"capacity_kw":7.5,"tilt_degrees":18,"azimuth_degrees":180,"temp_coefficient":-0.0035,"degradation_factor":1,"inverter_count":4,"tariff_per_kwh":4}'`
      returns valid JSON in < 15 s
- [x] Pin versions in `requirements.txt` (built on Python 3.14; needs ≥ 3.11)
- [x] Fix `weather.py` live pipeline: request `direct_normal_irradiance`
      instead of `direct_radiation` (currently passes horizontal direct
      irradiance where pvlib expects DNI)

### Harsh — 1 model + frontend + demo flow + deployment

Start with frontend/infra (no dependencies); switch to the model once item
1 above is on `main`. If it isn't yet, generate the dataset yourself with
the backfill command (same seed → same data) once `backfill.py` is pushed.

- [x] **Local setup**: backend venv (`python3 -m venv .venv &&
      .venv/bin/pip install -r requirements.txt`), `npm install` in
      `webapp/frontend`, `.env.local` with `NEXT_PUBLIC_SUPABASE_URL` /
      `NEXT_PUBLIC_SUPABASE_ANON_KEY` (get from the Supabase dashboard →
      Project Settings → API) and `NEXT_PUBLIC_API_URL=http://localhost:8000`
- [x] **Supabase**: disable "Confirm email" (Authentication → Providers →
      Email). *Done when*: fresh sign-up → setup plant → dashboard works
      with no email step
- [x] **Model 3 — Gradient Boosting** (`app/models/gradient_boosting.py`,
      `HistGradientBoostingRegressor`): predict healthy `ac_power_kw` from
      weather features + inverter, flag on residual threshold.
      *Done when*: appears in `evaluate` output on the canonical dataset
- [x] **Mock + client**: `src/lib/mocks/analysis.json` (hand-written,
      matching Contract 3 exactly, ~48 series points, 4 inverters, 3
      models) and `src/lib/analysis.ts` (typed `runAnalysis(plant)`; uses
      the mock when `NEXT_PUBLIC_USE_MOCK_ANALYSIS=true`)
      — **client done, mock skipped**: the real endpoint was already on
      `main`, so `runAnalysis` calls it directly and the panel was built and
      verified against real responses instead
- [x] **Analysis panel** in `PlantDashboardView`: "Run 30-day analysis"
      button + loading state (up to ~15 s), expected-vs-actual chart
      (Recharts, flagged hours highlighted, true faults optional overlay),
      per-inverter table (status badge, kWh/revenue lost), model
      comparison table (precision/recall/F1/R²) with a model selector that
      re-requests with `model`. *Done when*: works fully on the mock
- [ ] **Deploy**: backend on Render (or Railway), frontend on Vercel; CORS
      origins from an env var (`CORS_ORIGINS`, comma-separated, default
      `http://localhost:3000`); set `NEXT_PUBLIC_API_URL` on Vercel; add the
      Vercel URL to Supabase Auth → URL Configuration.
      *Done when*: sign-up works on the live URL (analysis can still be mock)
- [x] **Demo flow script** (`DEMO.md`): sign up → configure plant → live
      dashboard → run analysis → compare models → point at a faulty
      inverter and its revenue loss. ~3 minutes
- [x] README: Linux/macOS run commands (`.venv/bin/...`)

### Together — integration (sync point 1)

- [ ] Harsh sets `NEXT_PUBLIC_USE_MOCK_ANALYSIS=false`, points at the real
      endpoint (local, then deployed); fix any contract mismatch
      (log it in the change log)
- [ ] Pick the default model (best F1 on the canonical dataset)
- [ ] Redeploy backend + frontend; verify end-to-end on the live URL

### Together — demo rehearsal (sync point 2)

- [ ] Run `DEMO.md` end-to-end on the live URL on a fresh account
- [x] README "Hackathon MVP" summary with the model comparison table
      (Harsh drafted it as "Model results"; Abhinav, edit freely)

### Optional — out of MVP scope (only if time remains)

- More models (e.g. LSTM autoencoder)
- Scheduled background ingestion (browser polling is fine for a demo)
- Backend JWT auth / per-user data in FastAPI (replace hardcoded
  `LATITUDE`/`LONGITUDE`/`TARIFF_PER_KWH`)
- [x] Persisting backfilled history to Supabase so the live charts show 30
      days — `app/seed_supabase.py` (Abhinav)
- [x] Align live fault-injection constants with the backfill's (see
      FINDINGS.md §3) (Harsh)
- Server-side aggregation for energy/revenue totals
- Automated tests
- Custom favicon/logo

### Contract change log

_(append: date — who — what changed — why)_

- 2026-10-11 — Abhinav — dataset is **hourly CSV**, not 15-min parquet
  (Open-Meteo archive is hourly; no extra dependency); request fields renamed
  to `tilt_degrees`/`azimuth_degrees` to match the existing
  `/api/synthetic/generate` request

- 2026-10-11 — Abhinav — `base.py` gains `add_peer_features()` and
  `smooth_daylight_scores()`; peer inverters' output is an allowed feature
  (own output still isn't)
- 2026-10-11 — Abhinav — API: `days` min 21 (shorter windows often hold no
  test faults); `period.test_fault_hours` added; precision/recall/f1 can be
  `null`; validation errors are 422 (FastAPI default), unknown model is 400

- 2026-10-11 — Abhinav — **edited Harsh-owned frontend files** (needed to
  display a seeded month): `lib/plantDashboard.ts` now reads in pages
  (Supabase caps responses at 1000 rows), charts show the newest 7 days
  (previously the *oldest* rows, so "latest conditions" was wrong), totals
  cover all rows; `WeatherHistoryChart`/`GenerationHistoryChart` show
  `MM-DD HH:MM` labels and drop dots above 100 points. Function signatures
  unchanged apart from the removed optional `limit` params
- 2026-10-11 — Abhinav — `backfill.build_dataset()` gains optional
  `weather`, `step_minutes`, `efficiencies` (hourly default unchanged —
  canonical dataset byte-identical)
- 2026-10-12 — Harsh — **proposed, not built yet**: Contracts 4–6 in "Working
  MVP" at the end of this file. All additive: new tables/columns/RPCs, two
  new plant-scoped endpoints. Contract 3 (`POST /api/plants/analyze`) is
  unchanged and keeps working

### Status log

_(append: date — who — what landed on `main`)_

- 2026-10-11 — Abhinav — plan + contracts pushed
- 2026-10-11 — Abhinav — backfill, canonical dataset, harness, baseline,
  Random Forest, Isolation Forest, and `/api/plants/analyze` on `main`.
  Harsh: dataset + harness are ready for the gradient boosting model, and
  the real endpoint is ready, so the mock is optional
- 2026-10-11 — Abhinav — `FINDINGS.md` (results + decision log — add your
  gradient boosting row there) and `app/seed_supabase.py`: fills your own
  plant with 30 days of history. Run from `webapp/backend`:
  `SEED_EMAIL=<login email> .venv/bin/python -m app.seed_supabase`
- 2026-10-12 — Abhinav — **FYI, no action needed**: `FINDINGS.md` §5
  "Optional findings" — side experiments with extra models. Headline: a
  no-ML peer comparison (each inverter vs. its neighbours) beats our Random
  Forest (F1 0.781 vs 0.705) and nearly matches a model trained on the
  labels; it's blind to plant-wide faults unless paired with a weather-only
  check. **Nothing in the app or API contract changed.** Your gradient
  boosting model and the comparison panel proceed exactly as planned. Worth
  knowing for the demo Q&A
- 2026-10-12 — Harsh — `gradient_boosting` model (branch `harsh/gb-model`).
  Mean F1 0.677 over seeds 1–8: second to Random Forest (0.705, GB wins
  2/8), ahead of the baseline and Isolation Forest. Same recipe as RF, with
  shuffled 5-fold CV standing in for out-of-bag. Results and the
  contiguous-folds dead end are in `FINDINGS.md` §1–2. No contract changes
- 2026-10-12 — Harsh — merged #3 (analysis panel), #4 (gradient boosting),
  #5 (`DEMO.md`, README, live fault rates aligned with the backfill, "My
  plant" nav link). Then **planned the "Working MVP" below — Abhinav, please
  read its "Open questions" before building on `analysis.py`**

---

## Working MVP — connected (simulated) hardware

*Planned 2026-10-12 (Harsh). Nothing below is built yet.*

### Why

The hackathon MVP above works end to end, but it's a demo of a product, not
a product. An honest review found:

1. **The analysis doesn't analyse the user's plant.** `POST /api/plants/analyze`
   generates its own fresh synthetic month instead of reading the readings
   stored in Supabase. The dashboard and the analysis are two unrelated
   simulations: the analysis can call INV-3 "critical" while the dashboard's
   history shows it healthy.
2. **Data arrives only while a browser tab is open**, and two open tabs both
   inject faults. There's no notion of a device being connected.
3. **The dashboard shows the answer key.** The inverter "Fault active" badge
   reads the injected fault label. Real hardware never reports "I'm faulty";
   status must come from detection.
4. **No verdict.** "Know before it costs you money" needs the app to *say*
   which inverter is losing output now. Today you click a button to look at
   the past month.
5. **The default model is picked on the test week** (best F1 per run), so the
   "winner" changes from run to run. That's selection on test data.

### Goal

One loop, on the user's own data, every time they open the app:
**my plant's data → which inverter is losing output → what it's costing me.**

The inverters stay simulated, but they behave like real hardware: a separate
**virtual gateway** process pushes telemetry through the same kind of
interface a real data logger would. Swapping in real hardware later means
writing a new gateway, not changing the app.

**Done when** (the demo loop, on a fresh account, in daylight at the plant):

1. Sign up → set up plant → the app shows a **pairing code**
2. `python -m gateway pair <CODE>` then `python -m gateway run` → within
   ~10 s the dashboard says **Connected**, and ~30 days of history appear
   (the gateway catches up)
3. New readings appear **without refreshing**
4. `inject INV-3 30%` in the gateway console → within a few readings the
   dashboard says **"INV-3 is under-producing ~30%, ≈X/day"**
5. `offline` → the dashboard says **Offline · last seen N min ago**
6. The 30-day analysis runs on the **stored** readings, and its verdict for
   each inverter agrees with the dashboard

**Not in this MVP**: real hardware or CSV import (first thing after),
email/push alerts (need a scheduler), deployment, multiple plants per
account, a mobile layout pass.

### Architecture

```
 virtual gateway (python -m gateway)          Supabase                     app
 ┌──────────────────────────────┐   RPC    ┌──────────────────┐  Realtime  ┌───────────────┐
 │ 4 virtual inverters          │ ───────▶ │ gateways         │ ─────────▶ │ dashboard     │
 │ real weather (Open-Meteo)    │  token   │ weather_readings │            │ (Next.js)     │
 │ physics (app.synthetic_*)    │          │ generation_...   │ ◀──────┐   └───────┬───────┘
 │ fault state + console        │          └──────────────────┘   RLS  │           │ Bearer
 └──────────────────────────────┘                    ▲                 │           ▼
                                                     └──── user JWT ── FastAPI: /status, /analyze
```

- The gateway is a **separate process** with its own credentials (a device
  token). It never sees the user's password.
- The browser **stops generating data**; it only reads.
- The backend reads Supabase **as the user** (their JWT + the anon key), so
  row-level security applies. Still no service_role key anywhere.

### Contract 4 — Device link (`webapp/supabase/005_devices.sql`)

Run once in the Supabase SQL Editor, like 001–004. Uses `pgcrypto`
(enabled by default on Supabase, schema `extensions`).

**New table `gateways`** (one per plant)

| column | type | notes |
|---|---|---|
| `id` | uuid pk | |
| `plant_id` | uuid, unique, fk → plants (cascade) | |
| `serial` | text | reported by the gateway, e.g. `SIM-GW-4F2A` |
| `token_hash` | text | sha256 of the device token; the token itself is never stored |
| `pairing_code` | text, unique, nullable | 6 characters, cleared once used |
| `pairing_expires_at` | timestamptz | code valid for 15 min |
| `paired_at`, `last_seen_at`, `created_at` | timestamptz | |

RLS: owners can `select` their plant's row. No direct insert/update from
clients; everything goes through the functions below.

**New nullable columns** (existing rows unaffected)

- `generation_readings`: `energy_kwh` (energy in this interval; intervals
  are no longer always 15 min, so `ac_power_kw × 0.25` stops being right),
  `dc_voltage_v`, `dc_current_a`, `inverter_temp_c`,
  `energy_today_kwh`, `status_code` (`producing` | `standby` | `offline`),
  `fault_severity` (**label**), `source` (`browser` | `gateway`, default
  `browser`)
- `weather_readings`: `wind_speed_kmh`, `source`

**Functions** (`security definer`, `search_path = public`)

| function | caller | does |
|---|---|---|
| `create_pairing_code(plant_id)` → text | logged-in owner | creates or rotates the plant's gateway row with a fresh 15-min code |
| `pair_gateway(code, serial)` → jsonb | gateway (anon key) | checks the code, creates the plant's inverters if missing, issues a random 32-byte token (stores only its hash), clears the code. Returns `{token, plant: <the plants row>, inverters: [{id, label, base_efficiency_factor}]}`; the gateway derives the physics inputs with the existing `resolve_plant_defaults()` (`app/seed_supabase.py`) |
| `gateway_state(token)` → jsonb | gateway | `{plant, inverters, last_recorded_at}`: current config (the owner may have edited the plant) and where to resume catching up |
| `ingest_telemetry(token, weather jsonb, readings jsonb)` → jsonb | gateway | checks the token; inserts rows for **that plant's inverters only**, skipping existing timestamps (existing unique keys); updates `last_seen_at`; returns `{inserted_weather, inserted_readings}`. Max 2,000 readings per call |
| `plant_totals(plant_id)` → jsonb | logged-in owner | energy, revenue and reading count, computed in SQL (replaces paging every row into the browser) |

Plus: `alter publication supabase_realtime add table generation_readings, gateways;`
so the dashboard can subscribe. Realtime respects RLS.

### Contract 5 — Telemetry payload (gateway → `ingest_telemetry`)

```jsonc
// readings: one per inverter per interval
{ "inverter_id": "uuid", "recorded_at": "2026-10-12T09:05:00Z",  // UTC, end of interval
  "ac_power_kw": 1.42, "dc_power_kw": 1.49, "energy_kwh": 0.1183,
  "revenue_per_interval": 0.53,
  "dc_voltage_v": 361.2, "dc_current_a": 4.12,
  "inverter_temp_c": 41.5, "cell_temp_c": 47.9, "poa_irradiance_wm2": 812.0,
  "energy_today_kwh": 6.31, "status_code": "producing",
  "fault_active": false, "fault_severity": 0.0 }   // labels: evaluation only
// weather: one per interval
{ "recorded_at": "...", "temperature_c": 29.4, "cloud_cover_pct": 40,
  "ghi_wm2": 690, "dni_wm2": 540, "dhi_wm2": 160, "wind_speed_kmh": 9.5 }
```

**Rule:** `fault_active` / `fault_severity` are ground truth for scoring
only. **No UI element and no detector may read them.** The only place they
appear is the "how accurate is this?" evaluation (precision/recall).

Intervals: live readings every **300 s** by default (`--interval`; use ~30 s
for a demo); catch-up runs at 15-min resolution, at most 30 days back.

### Contract 6 — Plant-scoped API (FastAPI)

Both endpoints require `Authorization: Bearer <Supabase access token>`. The
backend uses it to read Supabase as that user.

**6a. `POST /api/plants/{plant_id}/analyze`**: the 30-day analysis, on
**stored** readings.

- Request: `{ "days": 30, "model": "random_forest" }` (both optional;
  `days` 7–90)
- Builds a Contract 1-shaped hourly frame from stored rows:
  - hourly means of power;
  - weather joined on time;
  - `solar_elevation` and `is_daylight` from pvlib;
  - `poa_irradiance` and `cell_temp` from the stored readings;
  - labels from `fault_active` / `fault_severity`.

  Then the same time split, training and scoring as Contract 3.
- Response: **same shape as Contract 3**, plus
  `"source": "stored"` and `"coverage": {"expected_rows", "present_rows"}`
- Default model: **fixed** (`random_forest`; see M7), not best-F1 per run
- Errors: 401 missing/invalid token, 404 plant not found or not yours,
  409 not enough data (`detail` says how many days are present)

**6b. `GET /api/plants/{plant_id}/status`**: the live verdict.

```jsonc
{ "as_of": "2026-10-12T09:10:00Z", "model": "random_forest",
  "gateway": { "connected": true, "last_seen_at": "...", "serial": "SIM-GW-4F2A" },
  "inverters": [
    { "label": "INV-3", "state": "underperforming",   // ok | underperforming | offline | learning | no_data
      "shortfall_pct": 28.5, "since": "2026-10-12T08:40:00Z",
      "est_kwh_lost_24h": 2.1, "est_revenue_lost_24h": 9.45 } ] }
```

- Trains the fixed model on stored history up to 24 h ago, caches it per
  plant in memory, and retrains when the cache is more than 6 h old
- Scores the most recent readings **at their native interval**, with a
  **trailing** median of the last 6 readings. It must be trailing, not
  centred: live status can't use future readings, see `FINDINGS.md` §5,
  finding 5.
  A fault injected in a demo is visible after ~6 readings.
- `underperforming`: the smoothed shortfall is above the model's threshold
  for the last 3 daylight readings. `offline`: no reading for more than
  3 × interval (at least 2 min). `learning`: under ~4 days of history
  before the last 24 h to train on. `since` = the start of the current run
  of flagged readings.
- Night: `state` stays at its last daylight value, with no new flags

### Work items

| # | Item | Owner | Done when |
|---|---|---|---|
| M1 | `005_devices.sql`: `gateways`, new columns, the 5 functions, Realtime publication | Harsh | Run in the SQL Editor; `pair_gateway` with a bad code fails; `ingest_telemetry` with another plant's inverter id inserts nothing |
| M2 | **Virtual gateway** `webapp/backend/gateway/` (`python -m gateway pair/run`). Reuses the physics in `app.synthetic_generation` / `app.backfill` (import, don't copy) and the backfill's fault constants. Token kept in `gateway/.gateway.json` (gitignored). Console commands: `status`, `inject INV-n <pct> [duration]`, `clear INV-n`, `offline [duration]`, `quit` | Harsh | Pairs with a code; catches up a 30-day gap; live readings land at `--interval`; `inject` shows up in the readings |
| M3 | **Pairing + live dashboard**: a "Connect your inverter" step after plant setup (code, the command to run, live wait); a connection badge (Connected / Offline · last seen); a Realtime subscription so charts and KPIs update without refreshing; totals from `plant_totals`; every device labelled **"Simulated device (virtual gateway)"** | Harsh | Done-when steps 1–3 and 5 work in the browser |
| M4 | **Remove the browser simulation**: `SimulationIngestion` and the tick/fault code in `lib/generation.ts` (keep `resolvePlantDefaults`). The inverter status badge comes from 6b, never from `fault_active` | Harsh | No writes from the browser; grep finds no UI read of `fault_active` outside the evaluation table |
| M5 | **6a: analysis on stored readings**: new `app/plant_data.py` (stored rows → Contract 1 frame) and `app/plant_analysis.py`, reusing `analysis.py`'s summaries without modifying it; new route | Harsh | Same response shape; on a gateway-fed plant, the verdicts match the dashboard |
| M6 | **6b: `/status`** (backend) + a **verdict banner** on the dashboard ("INV-3 is under-producing ~28% since 08:40, ≈9/day" or "All 4 inverters healthy"); new `app/plant_status.py` | Harsh | Done-when step 4 |
| M7 | **One fixed model**, chosen once on the canonical benchmark, not per run. `random_forest` today. If Abhinav's peer hybrid (`FINDINGS.md` §5) is added as `app/models/peer_hybrid.py` and wins on seeds 1–8, it becomes the default for both 6a and 6b | Harsh (peer hybrid: post-MVP) | The default in 6a/6b is a constant; results recorded in `FINDINGS.md` |
| M8 | **Docs and cleanup**: `DEMO.md` rewritten around pair → live → inject → detect; README (gateway, architecture); historical Kaggle demo moved out of the main nav; `FINDINGS.md` entry with stored-data results | Harsh | `DEMO.md` runs end to end on a fresh account |

**Progress** (2026-10-12, Harsh): all eight built. Verified live on the test
plant: pair (and re-pair via "Replace gateway") → catch-up → Realtime
readings → `inject INV-3 30` flagged ~1 min later as "under-producing ~27%"
→ `offline 3m` shows Offline / Not reporting, then recovers → 30-day
analysis on stored readings. Not verified: a brand-new account end to end
(the pairing UI was tested via "Replace gateway" on the existing account).

- [x] M1 `005_devices.sql` (run in Supabase)
- [x] M2 virtual gateway
- [x] M3 pairing + live dashboard
- [x] M4 browser simulation removed; health from the detector
- [x] M5 analysis on stored readings
- [x] M6 `/status` + verdict banner
- [x] M7 fixed default model (Random Forest; peer hybrid post-MVP)
- [x] M8 `DEMO.md`, README, historical demo out of the main nav, `FINDINGS.md`

**Order**: M1 → M2 → (M3 + M4) alongside M5 → M6 → M7 → M8. M2 and M5 are
independent once M1 is in: M5 can develop against a plant filled by
`seed_supabase.py`.

**Demo caveat**: detection needs sunlight. Present when it's daytime at the
demo plant's location (or set the plant somewhere it is daytime during the
presentation).

### Rules

- **Simulated, and labelled as such.** In the UI, `DEMO.md` and the
  presentation, the device is a *virtual gateway generating telemetry from
  real weather*. Never claim real hardware.
- Labels (`fault_active`, `fault_severity`) are for evaluation only (Contract 5).
- Live status uses trailing windows only; centred smoothing stays in the
  retrospective analysis.
- Still anon key + user JWT + device token. No service_role key.

### Ownership

Decided 2026-10-12: **Harsh builds all of M1–M8.** Abhinav's files
(`analysis.py`, `backfill.py`, `seed_supabase.py`, `models/`) are imported
and reused, not modified; the new endpoints get their own routes in
`main.py`. FYI for Abhinav, no action needed:

1. The status rule in 6b (trailing median of 6 readings, 3 consecutive
   flagged daylight readings) is a first guess. If your trailing-window
   experiment (`FINDINGS.md` §5, finding 5) suggests better numbers, say so.
2. The peer hybrid as the fixed default (M7) is post-MVP.

