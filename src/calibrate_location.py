"""Estimate each plant's (lat, lon) purely from its irradiance data.

Idea: sunrise/sunset time and day length depend on latitude (+ day-of-year);
solar noon timing depends on longitude (IST is a fixed UTC+5:30 offset, so
solar noon drifts from clock-noon depending on how far east/west of the IST
reference meridian, 82.5E, the site actually is). By comparing the plant's
*observed* sunrise/sunset/noon against pvlib's predictions across a grid of
candidate coordinates, we can find the best-fitting location without ever
being told it — a data-driven check on the ~18N assumption in tasks.md,
rather than leaving that assumption unverified.

Run: .venv/Scripts/python.exe src/calibrate_location.py
"""

import numpy as np
import pandas as pd
import pvlib

from data_loader import load_plant

TZ = "Asia/Kolkata"
# Relative threshold (% of that day's peak), not an absolute cutoff: an absolute
# threshold systematically shrinks apparent day length (haze/dust means the
# sensor reads ~0 for a while after true astronomical sunrise), which biases
# any latitude fit toward the equator. Relative-to-daily-peak is more robust.
RELATIVE_THRESHOLD = 0.02


def observed_sun_times(weather: pd.DataFrame) -> pd.DataFrame:
    """Per-day observed sunrise/sunset/noon from when IRRADIATION is non-trivial."""
    w = weather.dropna(subset=["IRRADIATION"]).copy()
    w["date"] = w["DATE_TIME"].dt.date

    rows = []
    for date, grp in w.groupby("date"):
        day_max = grp["IRRADIATION"].max()
        if day_max <= 0:
            continue
        daylight = grp[grp["IRRADIATION"] > RELATIVE_THRESHOLD * day_max]
        if daylight.empty:
            continue
        sunrise = daylight["DATE_TIME"].min()
        sunset = daylight["DATE_TIME"].max()
        noon = grp.loc[grp["IRRADIATION"].idxmax(), "DATE_TIME"]
        rows.append({"date": date, "sunrise": sunrise, "sunset": sunset, "noon": noon})
    return pd.DataFrame(rows)


def _minutes_since_midnight(ts_series: pd.Series) -> np.ndarray:
    return ts_series.dt.hour.values * 60 + ts_series.dt.minute.values


def score_location(lat: float, lon: float, obs: pd.DataFrame) -> float:
    """Mean absolute error (minutes) between observed and predicted sun times."""
    loc = pvlib.location.Location(lat, lon, tz=TZ)
    days = pd.DatetimeIndex(obs["date"].astype(str)).tz_localize(TZ)
    rst = loc.get_sun_rise_set_transit(days, method="spa")

    obs_sunrise = _minutes_since_midnight(obs["sunrise"])
    obs_sunset = _minutes_since_midnight(obs["sunset"])
    obs_noon = _minutes_since_midnight(obs["noon"])

    pred_sunrise = _minutes_since_midnight(rst["sunrise"].dt.tz_convert(TZ))
    pred_sunset = _minutes_since_midnight(rst["sunset"].dt.tz_convert(TZ))
    pred_noon = _minutes_since_midnight(rst["transit"].dt.tz_convert(TZ))

    err = (
        np.abs(obs_sunrise - pred_sunrise).mean()
        + np.abs(obs_sunset - pred_sunset).mean()
        + np.abs(obs_noon - pred_noon).mean()
    ) / 3
    return err


def grid_search(obs: pd.DataFrame, lat_range, lon_range) -> tuple[float, float, float]:
    best = (None, None, np.inf)
    for lat in lat_range:
        for lon in lon_range:
            err = score_location(lat, lon, obs)
            if err < best[2]:
                best = (lat, lon, err)
    return best


def calibrate(plant: int) -> None:
    weather = load_plant(plant)[["DATE_TIME", "IRRADIATION"]].drop_duplicates()
    obs = observed_sun_times(weather)
    print(f"\nPlant {plant}: {len(obs)} days of observed sun times")

    coarse_lat = np.arange(0, 35, 2.0)
    coarse_lon = np.arange(68, 97, 2.0)
    lat0, lon0, err0 = grid_search(obs, coarse_lat, coarse_lon)
    print(f"  Coarse best: lat={lat0}, lon={lon0}, mean abs err={err0:.1f} min")

    fine_lat = np.arange(lat0 - 2, lat0 + 2.01, 0.25)
    fine_lon = np.arange(lon0 - 2, lon0 + 2.01, 0.25)
    lat1, lon1, err1 = grid_search(obs, fine_lat, fine_lon)
    print(f"  Fine best:   lat={lat1:.2f}, lon={lon1:.2f}, mean abs err={err1:.1f} min")


if __name__ == "__main__":
    calibrate(1)
    calibrate(2)
