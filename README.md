# Solar Yield Prediction & Monitoring

Data analytics course project: predicting and understanding solar plant
output, framed around two decision-relevant questions rather than a single
generic "predict power" exercise.

1. **Diagnosis** — is a given inverter behaving normally right now, given the
   weather it actually saw? (fault/anomaly detection → maintenance dispatch)
2. **Planning** — what will the plant produce tomorrow, using only
   information genuinely available in advance? (day-ahead forecasting →
   operations/grid planning)

**Primary deliverable:** [notebooks/01_full_analysis.ipynb](notebooks/01_full_analysis.ipynb)
— fully executed end-to-end, narrative + code + inline figures, zero errors.

## Data

[Solar Power Generation Data (Kaggle)](https://www.kaggle.com/datasets/anikannal/solar-power-generation-data) —
two Indian solar plants, 15-minute readings, ~34 days (2020-05-15 to
2020-06-17), 22 inverters per plant. Not included in this repo (see
`data/raw/` — download the Kaggle zip and extract there to reproduce).

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
```

Place the Kaggle dataset's 4 CSVs in `data/raw/`, then either open the
notebook directly or regenerate it:

```bash
python build_notebook.py
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_full_analysis.ipynb
```

## Project structure

```
src/
  data_loader.py        merge generation + weather data (handles per-plant date-format quirks)
  solar_features.py      pvlib-based solar position / clear-sky / calendar features
  calibrate_location.py  data-driven lat/lon estimation from sunrise/sunset/noon timing
  eda.py                 exploratory analysis, saves figures to reports/figures/
  fault_detection.py     Thread 1: expected-power model + residual-based anomaly flagging
  forecasting.py         Thread 2: day-ahead yield forecast vs persistence/climatology
notebooks/
  01_full_analysis.ipynb final deliverable
reports/
  figures/                generated plots
  findings_summary.md     headline findings, integration narrative
tasks.md                  full phase-by-phase task log with findings and decisions
```

## Key findings

- **Two data-quality bugs caught and fixed before any modeling**: a date-
  parsing bug that silently misdated Plant 2's readings across 8 months
  instead of a real 34-day window, and a ~10x unit mismatch in Plant 1's
  `DC_POWER` relative to Plant 2's — both would have corrupted results
  downstream if left unnoticed.
- **Location calibration produced an honest negative result**: latitude is
  unidentifiable from this near-solstice window (day length barely varies
  with latitude there), while longitude converged consistently (~80°E) across
  both plants.
- **Thread 1**: Plant 1's expected-power model reaches R²=0.967 (healthy
  plant); Plant 2 only R²=0.450 — real unexplained variance. Two independent
  detection methods flag the same inverters, and the failure pattern is
  bimodal (intermittent high-load tripping, not steady degradation) — a
  specific, actionable diagnosis.
- **Thread 2**: Random Forest forecasting beats persistence for both plants
  (58% and 38% RMSE reduction respectively), and feature importance confirms
  the improvement is real signal, not artifact — caveated honestly given the
  small (31-day) sample.

Full detail, including everything that didn't work on the first try, is in
[tasks.md](tasks.md) and [reports/findings_summary.md](reports/findings_summary.md).

## Limitations

~34-day window limits seasonal generalization and forecasting sample size;
revenue-loss figures use an assumed, not real, tariff; Thread 2's "forecast"
weather is synthetic (measured irradiance + calibrated noise), not a real
archived forecast; a subset of Plant 2 inverters have fewer daytime readings
than typical, possibly indicating partial-period downtime not distinguished
from steady underperformance here.
