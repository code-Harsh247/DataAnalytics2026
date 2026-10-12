# Presentation script (~10 minutes)

Plain language, about a minute per slide. Suggested split: Harsh slides
1–5, Abhinav slides 6–10. Change it however you like.

---

## 1. Title

Hi everyone. We're Harsh and Abhinav, and our project is **Solar Plant
Manager**: a web app that helps the owner of a small solar plant monitor it,
forecast how much it will produce, and find out when something goes wrong.

---

## 2. What we built

Imagine you own a small solar plant, say on a factory roof. You want simple
answers: how much did I make today, is my plant doing well, what will it
produce this week, is anything broken, and when will it pay for itself?

Our app answers those on five pages:

- **Overview**: power right now, compared with what the plant *should* be
  producing, plus energy, earnings and CO₂ saved.
- **Production**: daily and monthly output, and a side-by-side comparison of
  the inverters.
- **Forecast**: how much energy to expect over the next seven days.
- **Health**: it spots inverters that are under-performing and tells you
  what it's costing.
- **Finance**: projected yearly earnings and the payback period.

Everything updates live as new readings arrive.

---

## 3. How it works

Here's the flow from left to right.

The **gateway** is the box at a plant that collects readings from the
inverters and sends them to the cloud. We don't have real hardware, so we
built a **simulated gateway**. I want to be upfront about that. It uses
**real weather** for the plant's location and real solar physics to work out
what each inverter would produce, and it adds realistic noise and occasional
faults.

The readings go into a **database** (Supabase). Our **analytics server**
reads them, calculates the metrics, makes the forecasts and runs the fault
detection. The **web app** shows the results.

About the data: it starts from real weather, meaning sunlight, temperature
and clouds. A physics model turns that into the electricity each panel would
make, accounting for the sun's angle, the panel's tilt and the heat. Then we
add real-life mess: sensor noise, the gap between the weather report and the
actual sky, passing shadows, and faults that cut output by 5 to 40% for a few
hours.

One important detail: because we simulate the faults, we know exactly when
and where they happened. That gives us an **answer key**, so we can actually
measure how good our fault detection is. Real solar data almost never has that.

*(If asked whether the data is realistic:)* As a sanity check, we measured
the panels' heat loss from the data alone and got minus 0.41% per degree.
The true value is minus 0.38%, inside our confidence interval.

---

## 4. Plant metrics

These are the numbers a plant owner actually looks at.

The most important is the **performance ratio**: of all the sunlight that
hit the panels, how much became electricity? Healthy plants are at 75 to
85%; our test plant is at 86%.

**Specific yield** is energy per kilowatt installed, so you can compare
plants of any size.

The chart on the right shows **where the energy went** over 30 days. We
start with what the sunlight could have given, then subtract the losses:
heat, panel ageing, the inverter, downtime, faults and other losses like
dust. The green bar is what was actually delivered.

And for finance, we run a full year of real weather through the model to
estimate yearly earnings. For our test plant, it pays for itself in about
**5.6 years**.

---

## 5. Forecasting

To forecast, we take the weather forecast, run it through the same physics,
and adjust it for how this particular plant has actually been performing.

The real question is whether it's any good. So we compared it, over a
**full year**, with two naive guesses: "tomorrow will be the same as today",
and "tomorrow will be like the average of the last month".

Our forecast was off by about **1.5 kWh a day, around 4.6%**. That's **42%
better** than "same as yesterday" and 59% better than the monthly average.

We were careful to score each day against the forecast **as it was issued
the day before**, not with hindsight. The chart shows that the monsoon
months are the hardest, but we stay ahead every month.

---

## 6. Fault detection

Now the Health page: how do we spot a failing inverter?

The idea is simple. **Learn what healthy output looks like**, then flag an
inverter when it falls well short of that. Our model predicts each
inverter's expected output from the weather and from what its neighbouring
inverters are producing right now.

If the shortfall is bigger than a threshold, we raise an alert. That
threshold is set from the normal noise in the data; it never looks at the
answer key.

We compared four methods: a simple physics rule, Random Forest, Gradient
Boosting, and Isolation Forest, which needs no training labels.

On the right is the app working live. We broke one inverter by 30% on
purpose, and within about a minute and a half the app flagged it and
estimated the money lost.

---

## 7. Which detector is best?

Here we tried to be honest about the results.

Random Forest scores best, with an F1 of 0.70. But the lines on the chart
are confidence intervals, and they overlap. When we tested the differences
properly, Random Forest is **genuinely better** than the physics rule and
Isolation Forest, but **statistically tied** with Gradient Boosting.

We also scored by whole fault events, which is what an owner cares about.
That revealed a trade-off. The simple physics rule catches the most faults,
84%, but two out of three of its alarms are false. Random Forest catches
fewer, 68%, but most of its alarms are real. So the best choice depends on
whether you'd rather catch everything or trust every alarm.

---

## 8. Detection limit, and why the ML is worth it

The left charts show how detection depends on fault size. Small faults,
under 10%, are almost invisible: they hide in the normal noise. Faults above
20% are caught about **96%** of the time.

The right charts show why machine learning is worth it. We made the weather
report less accurate on purpose. The simple physics rule falls apart, from
0.74 down to 0.41, but Random Forest barely changes.

Why? We looked at what the model relies on, and it's **almost only the
neighbouring inverters**. In practice it's a smart **peer comparison**. When
the weather report is wrong, it's wrong for every inverter at the same
moment, so comparing an inverter with its neighbours cancels the error out.

That's also its blind spot: if every inverter fails at once, for example in
a power cut, comparing them with each other won't catch it.

---

## 9. Limitations and next steps

What we can't claim yet:

- The inverter data is simulated, so the detection numbers describe our
  simulator. We showed how they change when its settings change.
- The detection test covers one month at one location; the forecast test
  covers a full year.
- Our "actual" weather for the forecast test comes from reanalysis data, not
  a sensor on site.

Next steps: import real data from actual inverters, use the peer comparison
as the main detector (it scored even higher in our experiments), add
cleaning advice and email alerts, and deploy the app online.

---

## 10. Takeaways

To sum up:

- The forecast is **42% better** than the naive guess.
- Fault detection reaches **0.70 F1**, and catches big faults **96%** of the
  time.
- The test plant **pays for itself in 5.6 years**.

Three things we learned. First, a working product: monitoring, forecasts,
health and finance for a real plant's own data. Second, simulating faults on
real weather let us *measure* detection, and statistics showed us which
differences are real. Third, machine learning earns its place where the
weather data can't be trusted, by comparing inverters with each other.

Thank you. We're happy to take questions.

---

## Likely questions (short answers)

- **"Isn't the data fake?"** The weather is real; the inverter output is
  simulated with real physics. That's what gives us the answer key to
  measure detection.
- **"Why not use real data?"** Real plant data almost never records exactly
  when faults happened, so you can't measure accuracy. Importing real data
  is our next step.
- **"Why did the simple rule catch more faults?"** It's very trigger-happy:
  it catches more, but most of its alarms are false.
- **"Can it work live?"** Yes. The live check only uses past readings and
  flags a fault within a few readings.
