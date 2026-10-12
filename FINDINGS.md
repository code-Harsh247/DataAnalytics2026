# Findings & Decisions — ML Pipeline

What we learned building the anomaly-detection pipeline, and why each
decision was made. `PRODUCT_PLAN.md` says *what* to build and who owns it;
this file says *what we found* and *why*. Append-only: add new entries at
the end of each section, dated, with your name.

**Reproduce every number here** (from `webapp/backend`):
```bash
.venv/bin/python -m app.models.evaluate --data data/backfill/sample_plant.csv
```

---

## 1. Model results

Canonical dataset `data/backfill/sample_plant.csv` (18°N 80°E, 2026-09-01 →
09-30, 7.5 kW, 4 inverters, seed 42). Split: first 70% of hours train, last
30% test. Detection is scored on daylight hours only.

| Model | Owner | F1 (seed 42) | Mean F1 (seeds 1–8) | Precision | Recall | R² (healthy) |
|---|---|---|---|---|---|---|
| `baseline_ratio` — physics ratio, no ML | shared | 0.610 | 0.638 | 0.58 | 0.73 | 0.974 |
| `random_forest` — expected power + residual | Abhinav | 0.675 | **0.705** | 0.70 | 0.72 | **0.988** |
| `isolation_forest` — unsupervised | Abhinav | 0.667 | 0.628 | **0.73** | 0.57 | — |
| `gradient_boosting` — expected power + residual | Harsh | 0.675 | 0.677 | 0.73 | 0.64 | 0.987 |

(Mean columns: averaged over 8 datasets generated with seeds 1–8 from the
same weather, because one test week holds only ~35 faulted hours, and a
single run moves by ±0.1 F1.)

**What the results say**
- **Learning "what healthy output should be" wins.** The Random Forest
  expected-power model beats the physics-only baseline by ~0.07 F1 on
  average and fits healthy output best (R² 0.988). The original Plant 1/2
  analysis reached the same conclusion; now it's confirmed against ground
  truth.
- **Unsupervised detection is precise but misses mild faults.** Isolation
  Forest has the best precision (0.73), so when it flags something it's usually
  right, but its recall is the lowest. Without an expected-power model it can't
  see a small, steady shortfall. Its average F1 is about the same as the
  baseline's.
- **Some faults are undetectable, and that's correct.** Faults below about 10%
  severity are inside the noise floor (3% measurement noise plus about 6%
  site-irradiance error). A Sydney test plant scored F1 ≈ 0.2 for every model
  because 8 of its 10 test fault hours were one 8% fault. This is a limit of
  the physics, not a model bug.
- **Boosting doesn't beat bagging here** (Harsh, 2026-10-12). Gradient
  boosting uses RF's exact recipe with only the learner swapped. It ties RF
  on seed 42 (0.675) but is second on average: 0.677 vs 0.705, winning 2 of 8
  paired seeds. It still beats the baseline (+0.04, 4/8) and Isolation Forest
  (+0.05, 6/8). It is more precise than RF (0.73 vs 0.70) and misses more
  (recall 0.64 vs 0.72), because its learned threshold is looser (0.15 vs
  0.12 relative shortfall). Its power fit is about equal to RF's (R² 0.987 vs
  0.988), but it ranks faults slightly worse: the average precision of its
  anomaly score is 0.76 vs RF's 0.79.
  - *Caveat*: `min_samples_leaf` and the CV fold scheme were picked from 5
    settings scored on these same 8 seeds, so 0.677 is slightly optimistic.
    The conclusion, second to RF, holds for every setting tried.

## 2. Decisions and why

**Data**
- **The data is synthetic, but generated from real weather.** There's no real
  inverter hardware. Weather is real (Open-Meteo); power comes from pvlib
  physics plus injected faults. That gives us something the original Kaggle
  coursework never had: **ground-truth fault labels**, which make real
  precision and recall possible.
- **The Open-Meteo archive API is used for the evaluation dataset.** Fixed
  dates plus a seed give a byte-identical file on every machine, so
  teammates never need to send each other data. Its downside: it trails real
  time by about 5 days.
- **The forecast API with `past_days` is used for seeding live plants.** It
  has no lag and native 15-minute data, which matches live ingestion.
- **The evaluation data is hourly, not 15-minute,** because the archive API is
  hourly. Interpolating to 15 minutes would invent smoothness that isn't there.
- **We made the dataset harder on purpose.** The first draft was so clean that a
  one-line ratio threshold scored **F1 0.99**, so no model comparison could mean
  anything. We added:
  - a shared ±6% site-irradiance error, because reanalysis weather isn't an
    on-site sensor;
  - 3% measurement noise;
  - fault severity of 5–40% (previously 15–50%);
  - unlabeled 1–2 hour partial-shading dips as false-alarm bait.

  After this, the baseline dropped to 0.61.
- **The fault rate is 0.02 per hour,** giving about 9% of daylight hours
  faulted. The live pipeline's rate (0.04 per 15 minutes) would leave
  inverters faulted about half the time, which is unrealistic.

**Evaluation**
- **Time-based split, never shuffled.** Shuffling would leak future weather
  patterns into training.
- **Only daylight hours are scored.** A fault at night produces 0 kW, the same
  as a healthy inverter, so including night rows would penalize every model
  for faults nobody could see.
- **Labels are removed before `fit` and `predict`,** as on a real plant. The
  harness enforces this, so no model can cheat.
- **Undefined metrics are reported as `null`, not 0.** A test window with no
  faults says nothing about recall. Short windows (14 days) often had none,
  which is why the API requires at least 21 days.
- **R² and MAE are measured on healthy rows only.** The models are meant to
  predict *healthy* output, so faulted rows aren't their target.

**Modelling**
- **Peer-inverter comparison is allowed as a feature; an inverter's own output
  isn't.** The site-irradiance error is shared by every inverter (it's the same
  sky), so the median output of the *other* inverters cancels it. It's the
  strongest single feature, and real fleet monitoring works the same way.
  Using an inverter's own output to predict its own output would be leakage.
- **No model tunes on labels.**
  - The Random Forest threshold is the median plus 2.5 robust standard
    deviations of its out-of-bag residuals.
  - The Isolation Forest's contamination rate (8%) is a prior about the
    plant.

  Both choices would work the same on a real plant with no labels.
- **The Random Forest is fitted twice.** Fault hours are in the training data
  unlabeled, so it fits once, drops the 10% worst-explained rows, and refits.
- **The threshold spread is measured before trimming.** Measuring after
  trimming cut one tail of the distribution, made the noise look smaller, and
  produced too many false alarms (precision 0.37 → 0.60 after the fix).
- **Scores are smoothed with a 3-hour rolling median.** Real faults last 2 or
  more hours, so this removes single-hour noise spikes. The window is
  centered, so it uses the next hour too. That's fine for this
  retrospective analysis; live alerting would need a trailing window.
- **Isolation Forest only flags hours below peer output.** It also isolates
  *over*-performing hours, which aren't faults.
- **Gradient boosting uses shuffled 5-fold CV in place of out-of-bag**
  (Harsh, 2026-10-12). `HistGradientBoostingRegressor` has no out-of-bag
  predictions, and a boosted model's in-sample residuals are far too
  small. Held-out residuals come from 5-fold CV on the train window instead.
  - *Contiguous time-block folds were tried first and failed* (mean F1 0.51,
    recall 0.46). Each block is a stretch of weather the model never saw, so
    the largest held-out residuals were healthy-but-unusual hours rather than
    faults. That inflated the threshold (0.22 vs RF's 0.12), and the
    "drop the 10% worst-explained rows" refit dropped healthy rows and kept
    the faulty ones: the average precision of the anomaly score fell to 0.56.
  - Shuffled folds hold out random rows, as out-of-bag does. That fixed both
    problems.
  - `min_samples_leaf` is 5, not sklearn's default of 20. The default smooths
    over the sharp peer-median relationship.

  The threshold itself still uses no labels. The two settings above were
  chosen by checking F1 on seeds 1–8, which is the caveat in section 1.

**Product**
- **The analysis API is stateless,** and the backend never writes to Supabase.
  It still has no service key or JWT check (see `PRODUCT_PLAN.md` Phase 10).
- **Analysis is deterministic per plant** (fixed seed), so re-running gives
  the same answer during a demo.
- **Seeding signs in as the plant owner** (`app/seed_supabase.py`). It uses
  email and password, so Row Level Security applies exactly as in the browser,
  with no admin key.

**Working MVP** (Harsh, 2026-10-12; `PRODUCT_PLAN.md` "Working MVP")
- **Data now comes from a gateway, not the browser.** A simulated gateway
  (`python -m gateway`) pairs with a 15-minute code, holds its own device
  token (stored only as a sha256 hash), and uploads through security-definer
  SQL functions. Everything still runs on the anon key.
- **The analysis and the verdict read the plant's stored readings** (as the
  signed-in user, via their JWT), so the dashboard and the analysis finally
  describe the same data. Before this, `/analyze` built its own synthetic
  month.
- **The dashboard used to show the answer key.** Its "Fault active" badge read
  the injected fault label. Status now comes only from the detector; labels
  are used only to score accuracy.
- **Live verdict = Random Forest trained on history older than 24 h, scored
  on raw readings with a *trailing* median of 6 and 3 flagged readings in a
  row.** Trailing, because a live verdict can't look ahead (the analysis
  keeps its centred window). Measured on the test plant at a 30 s interval: a
  30% fault injected at 03:19:00 was flagged from 03:20:00 and shown on the
  dashboard by 03:21:30. At the default 5-minute interval, expect ~15–20 min.
  The reported shortfall (27–28%) matched the injected 30%.
- **The default model is fixed** (Random Forest), no longer the best F1 of
  each run, which was selection on the test window.
- **Caveat on stored-data scores:** the test plant's 30-day analysis scores
  F1 0.85 (RF). This is **not comparable** to section 1: its history mixes
  seeded data with the older browser pipeline, whose faults were bigger
  (15–50%) and so easier to catch. Section 1 stays the benchmark.

**Product MVP: forecasting and metrics** (Harsh, 2026-10-12)
- **Forecast = weather forecast → physics → × calibration.** Calibration is
  the plant's actual ÷ physics-expected energy over the last 14 days of
  daylight readings (0.95 on the test plant). One number absorbs soiling,
  shading, wiring and the site's sky bias. No per-plant ML model is trained
  for the forecast: with weeks of data, a calibrated physics model is
  harder to overfit than a learned one, and it stays interpretable.
- **Accuracy is measured day-ahead, not in hindsight.** Open-Meteo's
  previous-runs API returns each hour's forecast as issued the day before;
  we run it through the same model and compare with what the plant made.
  Test plant (18.5°N 73.9°E, 5–11 Oct, clear post-monsoon weather): mean
  absolute error **5.7%**, per-day errors −5.9% to +14.9%. The forecast's
  p10–p90 band (91–104% of the forecast) comes from those errors.
  *Caveats:* 7 days of easy weather; and the calibration window overlaps
  the scored days (one scalar, so the leak is small but not zero).
- **Performance ratio** follows IEC 61724: AC energy ÷ (plane-of-array
  insolation × kWp). The test plant's 30-day PR is 0.86, at the top of the
  healthy 0.75–0.85 range. That's expected: the simulator has no long-term
  soiling and only light shading, so treat it as a sanity check of the
  formula, not a finding about real plants.
- **Typical year** = the last 365 days of archive weather at the site →
  physics × calibration: 13.8 MWh for 7.5 kWp (≈1,840 kWh/kWp). Real plants
  in central India report ~1,400–1,700, so ours is optimistic, again because
  the simulator has no soiling, curtailment or downtime.
- **Loss breakdown adds up by construction**: potential − heat − ageing −
  conversion − downtime − detected faults − other = delivered, where "other"
  is the remainder. On the test plant (30 days): 1,285 → 1,102 kWh, with
  heat the largest loss (81 kWh) and detected faults 28 kWh.

## 3. Bugs found along the way

- **`weather.py` requested the wrong sunlight value.** It asked Open-Meteo for
  `direct_radiation` (direct sunlight on a horizontal surface) and passed it to
  pvlib as DNI (direct normal irradiance). These are different quantities.
  Fixed: it now requests `direct_normal_irradiance`.
- **The plant dashboard broke above 1,000 rows:**
  - The charts fetched the *oldest* rows, so "latest conditions" showed the
    oldest reading.
  - Totals were capped by Supabase's 1,000-row default response limit.

  Fixed with paged reads and a 7-day chart window.

- **Live and backfill fault rates disagree** (2026-10-11, found when INV-2
  showed "Fault active" right after seeding). The live pipeline
  (`frontend/src/lib/generation.ts`) starts faults at 4% per 15-min tick with
  15–50% severity, so an inverter is faulted roughly half the time over a day.
  The backfill uses 2% per hour with 5–40% severity. The INV-2 fault came from
  the live tick, not the seeded history. *Not fixed yet*: align the live
  constants with the backfill's (frontend, Harsh's area) so the live
  dashboard and the ML analysis describe the same plant.
  - **Fixed** (Harsh, 2026-10-12). `generation.ts` now uses the backfill's
    2%/hour start rate, converted per tick (0.5% per 15-min tick), and its
    5–40% severity range. Fault durations (2–8 h) were already the same.

## 4. Open questions / next experiments

- ~~Gradient boosting results (Harsh).~~ Done 2026-10-12 (sections 1 and 2).
- Would a trailing (causal) smoothing window, needed for live alerts, cost
  much recall?
- Per-inverter thresholds instead of one global threshold?
- Precision and recall broken down by fault severity, to show *where* the
  detection limit is (expected: about 10%).

## 5. Optional findings — exploratory, not in the app (Abhinav, 2026-10-11)

Extra models tested outside the shared pipeline. **Nothing here changes the
app or the API**; the three shared models (plus Harsh's gradient boosting)
remain the comparison the product shows. Recorded here as the strongest
candidate for a post-MVP upgrade, and as talking points for the demo. The
experiment code is in Abhinav's local sandbox; ask if you want it.

Method: same canonical weather, split and metrics as section 1, averaged over
8 seeded datasets. Models are compared **paired per seed**, not by their
±std: the std mostly reflects how hard each dataset is (one seed is hard for
every model).

| Model | Mean F1 | vs RF (paired, seeds won) | Notes |
|---|---|---|---|
| Supervised ceiling (trained *on the labels*, not deployable) | 0.787 | +0.082 (7/8) | Upper bound for per-hour detection |
| **Peer z-score** (no ML) | **0.781** | **+0.076 (7/8)** | Each inverter vs. the median of the others, in robust σ of its own usual ratio |
| **Peer hybrid**: peer z-score OR weather-only Ridge | 0.765 | +0.06 | **0.781 when plant-wide faults occur**, where the peer model alone drops to 0.714 |
| Ridge regression (expected power) | 0.758 | +0.053 (7/8) | Best power fit, R² 0.991 (RF 0.988) |
| `random_forest` (shared) | 0.705 | — | |

**What we learned**
1. **A simple peer comparison beats the Random Forest and nearly matches a
   model trained on the answers** (0.781 vs ceiling 0.787,
   statistically indistinguishable). It works because the biggest noise
   source, the gap between reported weather and the real sky, hits every
   inverter equally, and dividing by the peers cancels it. It runs in about
   0.04 s against RF's 0.8 s, and explains itself: "INV-3 made 2.8σ less
   than its neighbours".
2. **Per-hour detection is at the data's ceiling.** Fancier per-hour models
   (k-NN, MLP, LOF, SVM) were skipped as a result: at best they could tie.
3. **Blind spot: plant-wide faults.** When every inverter drops together
   (outage, curtailment), peer comparison catches **3%** of them. RF and
   Ridge catch about 60%, because they use the peer feature too. Adding a
   weather-only check (the hybrid) brings this to **98%**, costing about
   0.02 F1 when plant-wide faults never occur.
4. **Mild faults (<10%) are the frontier.** Every per-hour method, including
   the supervised one, catches at most 13%. Accumulating evidence over time
   (a CUSUM variant) reached 33% at the same F1, at the cost of precision.
5. **Live alerting is viable without smoothing.** A trailing (live-safe) 3h
   median lags every fault by an hour and costs 0.15 F1; for the peer model,
   no smoothing at all is as good as or better than the centered median.
6. **Small plants are fine.** Peer comparison stays the best deployable model
   with 3 inverters (−0.014) and 2 inverters (−0.09; every model drops there,
   including the ceiling).

**Caveat**: every simulated inverter shares one orientation and one sky,
which is close to ideal for peer comparison. On a plant with mixed
tilt/azimuth per inverter it would be weaker. This is untested.

**If we upgrade post-MVP**: promote the peer hybrid as a 4th/5th model
(`app/models/peer_hybrid.py`). It's additive to the API contract (one more
row in `comparison`), and since the API picks the best F1 it would likely
become the default.

## 6. Analytics round: uncertainty, limits, skill (Harsh, 2026-10-12)

Full write-up with figures: [`webapp/backend/analysis/REPORT.md`](webapp/backend/analysis/REPORT.md),
regenerated by `python -m analysis.run_all`. Headlines:

1. **Only some of the model ranking is statistically real.** Day-block
   bootstrap (72 seed-days, 2,000 resamples): RF F1 0.699 (95% CI
   0.624–0.767). RF beats the physics baseline (+0.065, CI +0.007 to +0.124)
   and Isolation Forest (+0.072, CI +0.005 to +0.146), but **not Gradient
   Boosting** (+0.028, CI −0.008 to +0.070). A Wilcoxon test on the 8
   per-seed F1s finds nothing significant (smallest p = 0.078): with n = 8
   it's underpowered. Section 1's "RF best" should read "RF and GB tied,
   both ahead of the rest".
2. **Per-hour F1 hid an episode-level trade-off.** Of 96 fault episodes in
   the pooled test windows, the physics baseline notices 84% but 65% of its
   alarm runs are false; RF notices 68% with 65% of alarms real; GB 60% with
   72% real. Which is "best" depends on whether an owner prefers catching
   everything or trusting every alarm.
3. **The detection limit, measured:** RF catches 10% of hours with 5–10%
   losses, 53% at 10–15%, 78% at 15–20%, 96%+ above 20% (pooled seeds 1–8).
   This replaces the "below ~10% is undetectable" estimate in §1 with a curve.
4. **Sky error is what separates the methods.** Re-simulating with the
   plant-wide sunlight error at 2% → 15%: the physics baseline falls from
   0.74 to 0.41 F1, RF only 0.79 → 0.67. Comparing with neighbours cancels a
   shared error. With an on-site irradiance sensor, the simple baseline
   would be competitive. Measurement noise (1% → 8%) hurts every model; RF
   stays on top (0.74 → 0.57).
5. **RF is effectively a peer comparison.** Permutation importance: shuffling
   `peer_median_kw` drops R² by 1.51; no weather input by more than 0.015.
   This explains §5's result that a no-ML peer z-score does as well, and
   the plant-wide-fault blind spot.
6. **The temperature coefficient can be recovered from the data:**
   −0.41%/°C (95% CI −0.50 to −0.33) against the configured −0.38%/°C;
   seeds 1–8 average −0.40%/°C. Sampling noise, not bias.
7. **The forecast has real skill.** 334 days at the test plant (Nov 2025 –
   Oct 2026), day-ahead forecast as issued vs ERA5-based actual: MAE 1.54
   kWh/day (4.6%), **42% lower than persistence** and 59% lower than a
   30-day climatology. Monsoon (Jun–Sep) roughly triples the error (0.83 →
   2.77 kWh/day) but the lead holds (34% over persistence). The app now
   shows persistence and the skill score next to its own 7-day accuracy.
   *Caveat:* ERA5 is reanalysis, not an on-site pyranometer; this measures
   the weather forecast's skill through our model, not model error.
