"""Solar-physics feature layer: solar position, clear-sky irradiance, and
calendar features from timestamp + location alone (zero leakage risk).

Location (18N, 80E): see the original analysis for how this was chosen —
latitude is an assumption (unidentifiable from a ~34-day, near-solstice
window), longitude was calibrated from the data (sunrise/sunset/solar-noon
timing vs pvlib predictions).
"""

import pandas as pd
import pvlib

LATITUDE = 18.0
LONGITUDE = 80.0
TZ = "Asia/Kolkata"

_LOCATION = pvlib.location.Location(LATITUDE, LONGITUDE, tz=TZ)


def add_solar_features(df: pd.DataFrame, irradiation_col: str | None = "IRRADIATION") -> pd.DataFrame:
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
        # IRRADIATION is a normalized fraction (~0-1.2), not raw W/m^2 like
        # pvlib's clearsky GHI — rescale onto the same basis before the ratio.
        max_ghi = out["CLEARSKY_GHI"].max()
        clearsky_norm = out["CLEARSKY_GHI"] / max_ghi if max_ghi > 0 else out["CLEARSKY_GHI"]
        ratio = (out[irradiation_col] / clearsky_norm).replace([float("inf"), float("-inf")], pd.NA)
        out["CLEARSKY_INDEX"] = ratio.where(out["SOLAR_ELEVATION"] > 5).clip(upper=1.5)

    return out
