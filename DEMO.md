# Demo script (~5 minutes)

The story: **a small solar plant owner's day-to-day manager.** How much did
I make, how well is the plant doing, what will it make this week, is
anything wrong, when does it pay for itself.

**Say this early:** the gateway is *simulated*. It's a separate program
that behaves like a real inverter data logger (pairs with a code, holds its
own device token, buffers readings when offline) and generates telemetry
from **real weather** at the plant. The app can't tell it from hardware,
and the app labels it "Simulated device".

## Before the demo

1. **Daylight at the plant.** Fault detection needs sun. Use a plant where
   it's daytime during your slot (e.g. 18.52 / 73.86 for an IST morning or
   afternoon).
2. Servers running (README → "Running it"); open <http://localhost:3000>
   once so the first compile isn't on camera.
3. Supabase: "Confirm email" off; `webapp/supabase/001`–`006` run.
4. **A prepared account** with a month of history and a paired gateway
   running at `--interval 30 --no-random-faults`. The Forecast accuracy and
   Finance numbers need that history, so don't rely on a fresh account for
   the main tour.
5. Optional: enter a system cost on Finance (e.g. `350000` for 7.5 kWp) so
   payback shows.
6. A second terminal in `webapp/backend` for `gateway/commands.txt`.

## The walkthrough

| Time | Page | Do / say |
|---|---|---|
| 0:00 | Login → **Overview** | "This is the owner's home screen." Point at **Power now vs expected**, **Today / This month / Lifetime** earnings, **CO₂ avoided**. |
| 0:40 | Overview | "**Performance ratio** is the industry's health number: how much of the sunlight that hit the panels became electricity. Healthy plants run at 75–85%." Show the **today curve**: actual so far against the forecast. |
| 1:10 | **Production** | Daily energy bars with PR, best/worst day, inverters side by side: "similar inverters should land close together; one that drifts down is worth a look." |
| 1:40 | **Forecast** | "Next 7 days, with a likely range and cloud cover." Then the key point: **"How good is the forecast?"** "Each day's forecast as it was issued the day before, against what the plant actually made. About ±6% here." |
| 2:20 | **Health** | Live verdict per inverter, availability, alert history with what each episode cost, and **where the energy went**: sunlight potential → heat → ageing → conversion → faults → delivered. |
| 2:50 | Health + terminal | `echo inject INV-3 30 > gateway/commands.txt`. "I'm breaking one inverter, like a failed string." About a minute later the banner turns red: **"INV-3 is under-producing by ~27% since …"**, and a red dot appears on Health in the nav. "Nobody told the app which one." |
| 3:40 | Health | Scroll to the **30-day detection report**: "Four models, scored against the faults the simulator injected. That record is what lets us prove detection accuracy at all." Then `clear INV-3`. |
| 4:10 | **Finance** | Earnings to date, average per day, **projected per year** (a full year of real weather at this site through the same model) and **payback**. |
| 4:40 | Wrap up | "Monitoring, analytics, forecasting, health and finance on one plant's own data, with ML where it earns its place: fault detection and forecast calibration." |

## Optional: onboarding from scratch (~1 min)

Sign up with a fresh email → set up a plant → **Get pairing code** →
`python -m gateway pair <CODE>` → `python -m gateway run --interval 30` →
the badge flips to **Connected** and a month of history appears as the
gateway catches up.

## If something goes wrong

- **A page says it needs `006_finance.sql`:** run it in the Supabase SQL Editor.
- **Pairing fails, "invalid or expired code":** codes last 15 minutes and
  work once; get a new one.
- **Health says "Learning…":** the plant has under ~4 days of history. Use
  the prepared account.
- **No detection after injecting:** it's night at the plant, or the loss is
  under ~10%. Use 30%+ in daylight.
- **Numbers look stale:** pages refresh as readings arrive (at most every
  30 s); reload if the gateway was restarted.

## Likely questions

- **"Isn't the data fake?"** The weather is real, the inverters simulated,
  with physics (pvlib) rather than random numbers. The gateway uses the same
  interface real hardware would.
- **"How is the forecast made?"** Weather forecast → physics → × this
  plant's calibration (its actual output ÷ the physics over the last 14
  days). Accuracy is measured against the day-ahead forecast, not hindsight.
- **"Where's the ML?"** Fault detection (Random Forest expected-power model;
  four models benchmarked, see README) and the per-plant calibration.
  A no-ML peer comparison scored even better (0.78 F1); it's the next model.
- **"How fast is fault detection?"** A few readings: ~1 minute at the demo's
  30 s interval, ~15–20 minutes at the default 5-minute interval.
