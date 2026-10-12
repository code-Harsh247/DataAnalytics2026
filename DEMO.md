# Demo script (~4 minutes)

The story in one line: **"Know your plant's health before it costs you money."**
Sign up, connect the plant's gateway, watch live readings arrive, then break
an inverter on purpose and watch the app catch it and put a price on it.

**Be upfront about one thing:** the gateway is *simulated*. It's a separate
program that behaves like a real inverter data logger: it pairs with a code,
holds its own device token, and pushes telemetry generated from **real
weather** at the plant's location. The app can't tell it apart from hardware,
and that's the point. Say so in the first minute, and the label in the app
says so too.

## Before the demo

1. **Daylight at the plant.** Detection needs sunlight. Set the demo plant
   somewhere it's daytime during your slot (for example India, 18.52 / 73.86,
   for a morning or afternoon slot in IST).
2. Servers running (README → "Running it"). Open <http://localhost:3000>
   once, so the first page compile isn't on camera.
3. Supabase: **"Confirm email" off**, and `webapp/supabase/001`–`005` run.
4. Two terminals in `webapp/backend`: one for the gateway, one spare for
   commands (`gateway/commands.txt`).
5. A fresh email for the sign-up (e.g. `demo+<date>@...`).
6. **Backup:** an account that is already paired, with a gateway running at
   `--interval 30`, in case pairing goes wrong on stage.

## The walkthrough

| Time | Do | Say |
|---|---|---|
| 0:00 | Login page → **Sign up** | "Owners of small solar plants usually find out about a failing inverter from the electricity bill. This tells them first." |
| 0:15 | Plant setup: name, `18.52` / `73.86`, tariff `4.5`, capacity `7.5`, inverters `4`, tilt `18`, azimuth `180` → **Save** | "Every field feeds the physics: location and tilt set the sun angle, panel type sets heat losses, age sets degradation, tariff turns energy into money." |
| 0:40 | **Connect your inverter** → **Get pairing code** | "Like any monitoring product, the plant connects through a gateway next to the inverters. Ours is simulated: it generates telemetry from real weather here, right now." |
| 0:50 | Terminal: `python -m gateway pair <CODE>` then `python -m gateway run --interval 30 --no-random-faults` | "It pairs with a short-lived code and gets its own device token. It never sees my password." |
| 1:05 | Dashboard flips to **Connected**; a month of history appears | "It just uploaded the last 30 days it had buffered, like a real logger catching up after being offline." |
| 1:25 | Point at **"All 4 inverters are producing as expected"**, the health column, and readings arriving every 30 s | "That verdict isn't a label from the simulator. A model trained on this plant's history compares each inverter with what the weather and its neighbours say it should make." |
| 1:50 | Second terminal: `echo inject INV-3 30 > gateway/commands.txt` | "Now I break one: INV-3 loses 30%, like a failed string or heavy soiling." |
| 2:00–3:00 | Wait for 3–4 readings. Banner turns red: **"INV-3 is under-producing by ~27% since …"**, Needs attention 1/4 | "About a minute later it's caught, with an estimate of what it's costing. Nobody told the app which inverter I broke." |
| 3:00 | `echo clear INV-3 > gateway/commands.txt`; optionally `offline 3m` → badge goes **Offline** after ~2 min | "If the gateway loses its internet link, the app notices; when it reconnects, the buffered readings upload." |
| 3:20 | Scroll to **30-day fault analysis** → **Run** | "Looking back over the month: four models, scored against the faults the simulator injected. That record is what lets us measure precision and recall at all." |
| 3:50 | Wrap up | "Learning expected output beats a physics-only rule. On our benchmark Random Forest averages F1 0.71, gradient boosting 0.68, the physics baseline 0.64. Faults below ~10% are inside our simulator's noise floor." |

The **Historical demo** link (top right) still has the original coursework
analysis on the real Kaggle plants.

## If something goes wrong

- **Pairing fails, "invalid or expired code":** codes last 15 minutes and work
  once. Click **Get pairing code** again.
- **`gateway_state` / `pair_gateway` "function not found":** run
  `webapp/supabase/005_devices.sql` in the Supabase SQL Editor.
- **The verdict stays "Learning…":** the plant has under ~4 days of history
  before the last 24 h. Restart the gateway with `--catch-up-days 30`, or use
  the backup account.
- **No detection after injecting:** it's night at the plant (output 0, so
  nothing to compare), or the loss is under ~10%. Use 30% or more.
- **The dashboard stops updating:** check the gateway terminal for upload
  errors, then reload the page.

## Likely questions

- **"Isn't the data fake?"** The weather is real; the inverters are
  simulated, with physics (pvlib) rather than random numbers. Simulated
  faults are what give us ground truth, so detection quality can actually be
  measured. The gateway uses the same interface real hardware would; swapping
  it for a real logger means a new gateway, not a new app.
- **"How does it know what 'should' be produced?"** A Random Forest trained on
  this plant's own history: weather plus the median of the other inverters at
  the same moment. It never sees the fault labels.
- **"Why not the best model in `FINDINGS.md`?"** A no-ML peer comparison
  scored 0.78. It's the planned next default; it misses plant-wide faults
  unless paired with a weather check.
- **"How fast is detection?"** Within a few readings: a trailing median of
  the last 6 readings must be above the threshold for 3 in a row. At 5-minute
  readings that's ~15 minutes; at the demo's 30 s, about a minute.
