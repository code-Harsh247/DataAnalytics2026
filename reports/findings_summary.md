# Findings Summary — Phase 6 Integration

## How the two threads relate

Both threads share one physics foundation (`src/solar_features.py`): solar
elevation, clear-sky irradiance, and clear-sky index computed purely from
timestamp + location via `pvlib`. What differs is deliberate:

| | Thread 1 — Fault Detection | Thread 2 — Forecasting |
|---|---|---|
| Question | Is this inverter behaving normally *right now*? | What will the plant produce *tomorrow*? |
| Decision it serves | Maintenance dispatch | Operations/grid planning |
| Inputs allowed | Actual measured weather (irradiance, temp) | Only what's knowable in advance: forecast irradiation, lagged past output, calendar |
| Why the difference matters | Diagnosing a fault requires knowing what actually happened | Planning requires never peeking at data that doesn't exist yet — using measured weather here would be leakage that inflates apparent accuracy |

That contrast — same physics layer, deliberately different input
constraints — is the throughline that turns "we trained two models" into a
coherent system: one answers a diagnostic question, one answers a planning
question, and the boundary between them is principled, not incidental.

## Headline findings

**Data quality (methodological rigor, not just modeling):**
- Caught and fixed a date-parsing bug where Plant 2's ISO-format dates were
  silently misparsed as month/day-swapped values — this had inflated an
  apparent "17% missing weather" figure to what is really ~0% (one genuine
  sensor dropout). Worth stating plainly: without this fix, several downstream
  numbers would have been wrong.
- Caught a ~10x unit mismatch in Plant 1's `DC_POWER` relative to Plant 2 —
  switched to `AC_POWER` as the cross-plant metric throughout.

**Location calibration (an honest negative result):**
- Attempted to back out plant coordinates from the data itself (sunrise/sunset/
  solar-noon timing vs. `pvlib` predictions). Latitude turned out to be
  unidentifiable in this ~34-day, near-solstice window — day length barely
  varies with latitude there. Longitude converged consistently (~80°E) across
  both plants. Reporting the limitation is more credible than a falsely
  precise number.

**Thread 1 — Fault detection:**
- Plant 1's expected-power model reaches R²=0.967 (weather explains almost
  everything — a healthy plant). Plant 2 only reaches R²=0.450, mirroring an
  earlier EDA correlation gap (0.99 vs 0.78) — real unexplained variance, i.e.
  genuine equipment issues.
- Two independent methods (raw per-inverter mean comparison in EDA, and
  weather-adjusted residuals here) flag the same inverters — real
  corroboration, not circular reasoning.
- Plant 2's flagged inverters show a bimodal residual pattern: normal most of
  the time, then a sharp ~650-750 unit drop specifically at high irradiance.
  Reads as intermittent tripping/clipping under load, not steady degradation —
  a specific, actionable diagnosis rather than "underperforms by X%."
- Quantified into estimated revenue lost (stated assumed tariff, not a real
  published rate): Plant 1 ≈ 576, Plant 2 ≈ 2,851 over the ~34-day window.

**Thread 2 — Forecasting:**
- ML (Random Forest) beats both persistence and climatology baselines for
  both plants: Plant 1 RMSE 11.1 vs. persistence 26.2 (58% reduction); Plant 2
  RMSE 10.8 vs. persistence 17.5 (38% reduction).
- Feature importance confirms the synthetic forecast-irradiation feature
  (60-78% importance) is genuinely driving the improvement, not noise the
  model happens to ignore.
- Caveat stated plainly: only 31 usable days — directionally sound and
  consistent across both plants, but not statistically bulletproof at this
  sample size.

## Deliverable format decision

**Primary deliverable: Jupyter notebook** (standard, expected format for a
data analytics course; narrative + code + figures in one reviewable
artifact). A Streamlit dashboard is a nice-to-have stretch goal if time
remains after the notebook and report are solid — not required for the core
grade.
