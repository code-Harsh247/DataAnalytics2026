# Demo script (~3 minutes)

The story in one line: **"Know your plant's health before it costs you
money."** Sign up, describe your plant, watch it run, then let four models
find the inverter that's losing you money, and show that the detection is
measured against ground truth rather than just claimed.

## Before the demo

1. Both servers running (see the README's "Running it"). Open
   <http://localhost:3000> (or the deployed URL) once, so the first page
   compile isn't on camera.
2. **"Confirm email" is off** in Supabase (Authentication → Providers →
   Email). Otherwise sign-up stops at "check your inbox".
3. **A backup account with history.** A brand-new plant has only a few
   15-minute readings, so its live charts are nearly empty. Make one account
   ahead of time, set up its plant, and give it 30 days of history (from
   `webapp/backend`):
   ```bash
   SEED_EMAIL=<backup account email> .venv/bin/python -m app.seed_supabase
   ```
   On Windows use `.venv/Scripts/python`. It asks for the password.
4. Pick a fresh email for the live sign-up (e.g. `demo+<date>@...`). Each
   account holds one plant.
5. Click **Run 30-day analysis** once on the backup account. This confirms
   the backend can reach Open-Meteo from the demo network.

## The walkthrough

| Time | Do | Say |
|---|---|---|
| 0:00 | Login page → **Sign up** with the fresh email | "Owners of small solar plants usually find out about a failing inverter from the electricity bill. This is a dashboard that tells them first." |
| 0:15 | Plant setup form: name, latitude/longitude (e.g. `18.52`, `73.86`), tariff `4.5`, capacity `7.5`, inverters `4`, module type, tilt `18`, azimuth `180` → **Save** | "Every field is used. Location and tilt drive real sun-position physics, panel type sets the heat-loss coefficient, panel age sets degradation, and the tariff turns lost energy into lost money." |
| 0:45 | The plant dashboard appears (nearly empty: that's expected) | "This is fetching **real current weather** for these coordinates every 15 minutes. There's no real inverter hardware, so output is simulated from that weather with physics. It's honest, labelled synthetic data." |
| 1:00 | **Sign out** → sign in to the **backup account** | "Here's the same dashboard after a month of data." Point at energy and revenue to date, and at the weather and output charts. |
| 1:15 | Scroll down → **Run 30-day analysis** (about 5–10 s) | "This rebuilds the last 30 days from real historical weather, injects faults we know about, trains four detection models on three weeks, and tests them on the last one." |
| 1:30 | The chart: actual (blue) vs expected (grey dashed), red dots = flagged hours | "Grey is what the plant *should* have produced given the weather; the red dots are where a model thinks something's wrong." Tick **Show true faults**: "the orange rings are the faults we actually injected, so you can see the hits and the misses." |
| 1:55 | Inverter table: point at the **critical** inverter and its kWh/revenue lost | "This one's the culprit, and here's what it cost over the month. That's the number an owner acts on." |
| 2:10 | Model comparison table → click **View** on a different model | "Because we know where the faults really are, we can measure precision and recall, which the original coursework dataset never allowed." |
| 2:35 | Wrap up | "Learning what healthy output looks like beats a physics-only baseline. Across 8 test datasets, Random Forest averaged F1 0.71, gradient boosting 0.68, the baseline 0.64. Faults below about 10% are inside the noise floor for every model, which is a limit of the data, not of the models." |

If there's time, the **Historical demo** links in the nav show the original
coursework analysis on the real Kaggle plants: Command Center, Maintenance
Queue with fault diagnosis, and Forecast.

## If something goes wrong

- **Analysis error "weather fetch failed" (502):** Open-Meteo is unreachable.
  Click **Re-run** once. If it still fails, show the screenshots in
  `presentation/screenshots/` and the table in the README.
- **"Needs at least 2 inverters":** the plant was set up with 1 inverter
  (a blank field defaults to 4). Use the backup account.
- **Sign-up says "check your email":** "Confirm email" is still on in
  Supabase. Use the backup account.
- **The numbers differ from the README:** expected. The analysis uses the
  *last* 30 days of weather at the plant's location, so every run has its
  own week and its own faults. The README table is the fixed benchmark
  (`data/backfill/sample_plant.csv`, averaged over 8 seeds).

## Likely questions

- **"Isn't the data fake?"** The weather is real and the power is physics
  (pvlib), not random numbers. Synthetic faults are the *point*: they give
  ground-truth labels, so detection quality can actually be measured.
- **"Why not the best model in `FINDINGS.md`?"** A no-ML peer comparison
  (each inverter against the median of the others) scored 0.78. It's the
  planned next model. It misses plant-wide faults unless paired with a
  weather check.
- **"Why did gradient boosting lose to Random Forest?"** Same features and
  recipe; its threshold, learned from cross-validation, comes out looser, so
  it is more precise but misses more. See `FINDINGS.md` §1–2.
- **"Can it alert live?"** Not yet. Scores are smoothed with a 3-hour window
  centred on each hour, which needs the next hour. A trailing window works
  live and is the next step for alerts.
