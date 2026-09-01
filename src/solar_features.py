"""Shared solar-physics feature layer used by both modeling threads.

All features here are computable from timestamp + location alone (no measured
weather), so they carry zero leakage risk and are safe inputs for the
day-ahead forecasting thread as well as the anomaly-detection thread.

Location: see tasks.md Phase 1/3 for how (18N, 80E) was chosen — latitude is
an assumption (unverifiable from this ~34-day, near-solstice window), longitude
is data-calibrated.
"""

import pandas as pd
import pvlib

LATITUDE = 18.0
LONGITUDE = 80.0
TZ = "Asia/Kolkata"

_LOCATION = pvlib.location.Location(LATITUDE, LONGITUDE, tz=TZ)


def add_solar_features(df: pd.DataFrame, irradiation_col: str | None = "IRRADIATION") -> pd.DataFrame:
    """Add solar-position, clear-sky, and calendar features to df (in place copy).

    If irradiation_col is given and present, also adds CLEARSKY_INDEX =
    irradiation / clearsky_ghi (capped, NaN at night). Pass None to skip that
    (e.g. when building forecast-only features with no measured irradiance).
    """
    out = df.copy()
    times = pd.DatetimeIndex(out["DATE_TIME"]).tz_localize(TZ, ambiguous="NaT", nonexistent="NaT")

    solpos = _LOCATION.get_solarposition(times)
    clearsky = _LOCATION.get_clearsky(times, model="ineichen")

    out["SOLAR_ZENITH"] = solpos["apparent_zenith"].values
    out["SOLAR_ELEVATION"] = solpos["apparent_elevation"].values
    out["CLEARSKY_GHI"] = clearsky["ghi"].values

    out["HOUR"] = out["DATE_TIME"].dt.hour + out["DATE_TIME"].dt.minute / 60
    out["DAY_OF_YEAR"] = out["DATE_TIME"].dt.dayofyear

    if irradiation_col is not None and irradiation_col in out.columns:
        # Clear-sky index needs an irradiance UNIT match, but IRRADIATION here is
        # a normalized fraction (~0-1.2, see eda.py), not W/m^2 like CLEARSKY_GHI.
        # Rescale clearsky_ghi onto the same normalized basis (divide by its own
        # daytime max) so the ratio is meaningful rather than comparing apples
        # to oranges.
        max_ghi = out["CLEARSKY_GHI"].max()
        clearsky_norm = out["CLEARSKY_GHI"] / max_ghi if max_ghi > 0 else out["CLEARSKY_GHI"]
        ratio = (out[irradiation_col] / clearsky_norm).replace([float("inf"), float("-inf")], pd.NA)
        out["CLEARSKY_INDEX"] = ratio.where(out["SOLAR_ELEVATION"] > 5).clip(upper=1.5)

    return out


if __name__ == "__main__":
    from data_loader import load_plant

    df = load_plant(1).drop_duplicates(subset=["DATE_TIME"])[["DATE_TIME", "IRRADIATION"]]
    feats = add_solar_features(df)
    print(feats.describe())
    print(feats[feats["SOLAR_ELEVATION"] > 5][["DATE_TIME", "IRRADIATION", "CLEARSKY_INDEX"]].head(10))
