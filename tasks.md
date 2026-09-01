# Solar Yield Prediction & Monitoring — Task Plan

Project: predict expected solar plant output and use it for two purposes —
(1) flag underperforming inverters (fault detection), and
(2) forecast next-day plant yield under realistic (forecast-only) inputs.

---

## Phase 0 — Setup

- [x] Create project repo structure (`data/`, `notebooks/`, `src/`, `reports/`)
- [x] Set up Python environment (venv/conda) with `pandas`, `numpy`, `scikit-learn`,
      `pvlib`, `matplotlib`, `seaborn`, `xgboost`, `requests`
- [x] Decide: Open-Meteo Historical Forecast API (real forecast/actual split) vs.
      synthetic-degradation shortcut for Thread 2 — **decision: synthetic degradation**
      (noise/smoothing on measured irradiance). Reason: dataset only covers
      May-Jun 2020 and Open-Meteo's forecast archive coverage that far back is
      unconfirmed; avoids a fragile external dependency for a time-boxed course
      project. State this simplification explicitly in the final report.
- [ ] Write a one-paragraph problem statement + the two decision-relevant questions
      the project answers (for the final report intro)

## Phase 1 — Data Acquisition

- [x] Download Kaggle "Solar Power Generation Data" (both plants: generation +
      weather sensor files) — extracted to `data/raw/`
- [x] Get plant lat/lon — **decision: 18°N, 80°E, tz=Asia/Kolkata (both plants)**.
      Attempted data-driven calibration (`src/calibrate_location.py`) by grid-
      searching lat/lon against observed sunrise/sunset/solar-noon (from when
      IRRADIATION crosses a per-day relative threshold) vs. pvlib predictions.
      **Result:** latitude is NOT identifiable from this ~34-day window — data
      spans mid-May to mid-June, near the summer solstice, where day length is a
      very weak function of latitude at low latitudes, so the fit degenerated
      toward the equator (not a bug, a real identifiability limit — kept as a
      documented finding). **Longitude converged consistently to ~79-82°E for
      both plants** (best noon-timing fit), plausible for central India near the
      IST reference meridian (82.5°E), though residual error (35-48 min) is
      larger than sensor noise alone — likely because May-Jun India often has
      clear mornings / cloud buildup by afternoon, which biases the "observed
      peak irradiance" proxy earlier than true solar noon on many days. Net:
      kept the original 18°N assumption (uncontradicted, just unverifiable here),
      adopted 80°E from the data.
- [ ] If using Open-Meteo: pull historical forecast data for the plant date range
- [x] Sanity-check timestamps align between generation and weather files; document
      time zone assumptions — **note:** date format differs by *plant*, not just by
      file type (Plant 1 generation = `DD-MM-YYYY HH:MM`, Plant 2 generation already
      ISO; both weather files ISO). Handled in `src/data_loader.py` with
      `format="mixed", dayfirst=True`. Merged dataset: 136,476 rows; ~17% missing
      weather fields (likely sensor downtime gaps) — to confirm in Phase 2 EDA.
- [x] Save raw files under `data/raw/`, never edit in place

## Phase 2 — Exploratory Data Analysis

- [x] Daily/seasonal generation patterns per plant (`reports/figures/daily_trend.png`,
      `hourly_curve.png`)
- [x] Distribution of AC/DC power, irradiation, ambient vs. module temperature
- [x] Correlation analysis: irradiance, temp → power output — **finding:** Plant 1
      AC_POWER correlates 0.99 with irradiation (near-textbook physics); Plant 2
      only 0.78 — meaningfully more unexplained variance, consistent with real
      inverter issues (see anomaly candidate below)
- [x] Per-inverter comparison plots — **finding:** Plant 2 inverter
      `Quc1TzYxW2pYoWX` averages ~30% below plant mean AC_POWER (170 vs 243) —
      strong first candidate for Thread 1
- [x] Missing data / outlier check, document cleaning decisions — **bug found &
      fixed:** initial loader used `format="mixed", dayfirst=True` for both plants;
      pandas misparsed Plant 2's ambiguous ISO dates (day<=12, e.g. `2020-06-01`)
      as Jan-Dec instead of June 1-12. Fixed with explicit per-plant date formats
      in `src/data_loader.py`. This also explained an apparent "17% missing
      weather" issue — after the fix it's really ~0% (4 rows / 1 timestamp, a
      genuine sensor dropout)
- [x] **Bug found:** Plant 1's `DC_POWER` is on a ~10x different unit scale than
      Plant 2's (AC/DC ratio 0.098 vs 0.977) — not comparable across plants.
      Decision: use `AC_POWER` as the primary cross-plant metric going forward
      (consistently scaled, and physically sensible: AC <= DC always)
- [x] Write up 5-10 EDA findings with supporting charts — see `src/eda.py` output
      and findings above; formal write-up deferred to Phase 6/7 report

## Phase 3 — Shared Feature Engineering (solar physics layer)

- [x] Compute solar zenith/elevation angle via `pvlib` from lat/lon + timestamp
      (`src/solar_features.py`, location 18N/80E per Phase 1 calibration)
- [x] Compute clear-sky irradiance (GHI) via `pvlib` for the same location/time
- [x] Derive clear-sky index = measured (or forecast) irradiance / clear-sky
      irradiance — **note:** dataset's `IRRADIATION` is a normalized fraction
      (~0-1.2), not raw W/m^2 like pvlib's clearsky GHI, so clearsky GHI is
      rescaled onto the same basis (divided by its own daytime max) before
      taking the ratio — otherwise the index would be comparing mismatched units
- [x] Build calendar features: hour, day-of-year (season deferred — not yet
      needed, dataset only spans ~34 days / one season anyway)
- [x] Confirm these features are reproducible for any future timestamp (no
      leakage risk) — verified: inputs are timestamp + fixed location only

## Phase 4 — Thread 1: Fault / Anomaly Detection  ✅ (`src/fault_detection.py`)

- [x] Train "expected power" model per plant (pooled across inverters) using
      measured irradiance, ambient/module temp, solar elevation as inputs
      (5-fold out-of-fold predictions via `cross_val_predict`, not in-sample —
      avoids trivially-good residuals from overfitting)
- [x] Baseline: linear regression; stronger: Random Forest — **finding:** Plant 1
      RF R2=0.967 (weather explains nearly all variance — healthy plant); Plant 2
      RF R2=0.450 only. This mirrors the Phase 2 correlation gap (0.99 vs 0.78) —
      Plant 2 has real unexplained variance, i.e. genuine equipment issues, not
      just noisier weather
- [x] Compute residuals (actual − expected) per inverter per timestamp
- [x] Implemented z-score threshold on per-inverter mean residual (flag z < -1.5).
      Plant 1: 2/22 flagged (matches the two lowest inverters from Phase 2's raw
      comparison — consistent). Plant 2: 3/22 flagged (Quc1TzYxW2pYoWX,
      Et9kgGMDl729KT4, LYwnQax7tkwH5Cb); a 4th from the Phase 2 raw check
      (rrq4fwE8jgrTyWY) came in just under threshold at z=-1.17 — model-based
      method is more conservative than the naive mean comparison
- [x] Characterized deviation pattern — **finding:** Plant 2's flagged inverters'
      residual-vs-irradiance plot is NOT a simple proportional loss. It's
      bimodal: near-normal residuals most of the time, plus a distinct second
      cluster dropping ~650-750 units specifically at high irradiance
      (0.7-1.0). Reads as intermittent tripping/clipping under high load, not
      steady degradation — more specific and actionable than "underperforms by
      X%" (`reports/figures/plant2_flagged_residual_pattern.png`)
- [x] Converted to estimated kWh/revenue lost (assumed tariff = 4.0 INR/kWh,
      stated explicitly, not a real published tariff). Totals over the ~34-day
      window: Plant 1 ≈ 576, Plant 2 ≈ 2,851 (same assumed currency units)
- [x] Cross-validated flags against Phase 2's independent raw-mean-comparison —
      same inverters surface both ways, which is a real corroboration, not
      circular (two different methods agreeing)
- [ ] Open item: a subset of Plant 2 inverters have noticeably fewer daytime
      readings (~1205 vs ~1663 typical) and different residual variance — could
      indicate partial-period downtime rather than steady underperformance;
      flagged for the report's limitations section, not resolved here

## Phase 5 — Thread 2: Day-Ahead Forecasting  ✅ (`src/forecasting.py`)

- [x] Scope decision: whole-plant **daily** total yield, not per-inverter/hourly
      (per earlier scope discussion — keeps this tractable given only ~34 days
      of data, 31 usable after lag/rolling warmup)
- [x] Build forecast-only feature set: synthetic day-ahead irradiation forecast
      (actual daily irradiation + ~15% relative Gaussian noise — stated
      simplification per the Phase 0 decision, not real forecast data), lagged
      actual yield (1-day, 2-day, 3-day rolling mean), day index. No measured
      same-day weather used — leakage-safe by construction
- [x] Baseline models: persistence (tomorrow = today) and expanding-window
      climatology (mean of all prior days) — both computed leakage-safe
      (shift/expanding on *prior* days only)
- [x] ML models: linear regression, Random Forest (test = last 7 days, train =
      remainder)
- [x] Evaluated all four vs RMSE/MAE/MAPE — **finding: ML beats persistence for
      both plants.** Plant 1: RF RMSE=11.1 vs persistence 26.2 (58% reduction);
      Plant 2: RF RMSE=10.8 vs persistence 17.5 (38% reduction). Climatology was
      the weakest baseline both times (flat-lines, ignores real day-to-day
      variation — see `reports/figures/plant1_forecast.png`, RF visibly tracks
      the June 13 volatility spike while persistence just lags a day behind)
- [x] Feature importance check: `FORECAST_IRRADIATION` dominates (60-78%) for
      both plants — confirms the synthetic forecast signal is genuinely
      informative to the model, not noise it learned to ignore; lag/rolling
      features contribute secondary but real value
- [ ] **Caveat for report:** only 31 usable days (24 train / 7 test) — results
      are illustrative and directionally sound (consistent across both plants,
      corroborated by feature importances) but not statistically robust at this
      sample size. State this explicitly rather than overclaiming.

## Phase 6 — Integration & Narrative  ✅ (`reports/findings_summary.md`)

- [x] Write up how Thread 1 and Thread 2 relate: same physics features, deliberately
      different input constraints (diagnosis vs. planning), and why that distinction
      matters
- [x] Pull together headline findings — see `reports/findings_summary.md` for the
      full list (data-quality bugs, location calibration result, Thread 1 & 2
      findings)
- [x] Decide on final deliverable format — **decision: Jupyter notebook is the
      primary deliverable**; Streamlit dashboard is an optional stretch goal only
      if time remains, not required

## Phase 7 — Deliverable & Polish

- [x] Clean up notebook(s) with narrative markdown between code cells —
      `notebooks/01_full_analysis.ipynb`, built programmatically via
      `build_notebook.py` (nbformat) then executed end-to-end via
      `jupyter nbconvert --execute` — **verified: all 14 code cells ran with
      zero errors**, printed numbers cross-checked against the standalone
      script runs (exact match), all 5 figures render inline correctly
- [x] Finalize charts (consistent style, labeled axes, captions) — done inline
      in the notebook version; standalone PNGs also in `reports/figures/`
- [ ] (Optional) Streamlit dashboard — deferred; not required per Phase 6 format
      decision, only a stretch goal if time remains
- [x] Write final report / README — `README.md` (problem framing, setup, project
      structure, key findings, limitations)
- [x] Proofread, check reproducibility — fixed a real bug found in this step: the
      notebook's `sys.path` insert used a path relative to cwd, which broke
      because Jupyter's kernel cwd is `notebooks/` not the project root, not
      wherever it's launched from; fixed to resolve robustly either way. Also
      had to make `matplotlib.use("Agg")` conditional (`if "ipykernel" not in
      sys.modules`) in `eda.py`/`fault_detection.py`/`forecasting.py` so
      importing them from the notebook doesn't clobber Jupyter's own inline
      backend — those scripts still run standalone via Bash exactly as before
- [ ] Presentation/demo — not attempted here, prepare if the course requires it
