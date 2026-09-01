"""Load and merge the Plant 1 / Plant 2 generation + weather sensor data.

Two fixes carried forward from the original analysis (see git history for
the full story, commit fcf0d88 era): Plant 1 and Plant 2 use different date
formats in their generation files (explicit per-plant format, not a "mixed"
heuristic, which silently misparses ambiguous ISO dates), and AC_POWER (not
DC_POWER) is used as the cross-plant metric since DC_POWER carries a ~10x
unit mismatch between the two plants.
"""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

_GENERATION_FORMAT = {1: "%d-%m-%Y %H:%M", 2: "%Y-%m-%d %H:%M:%S"}


def _load_generation(plant: int) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / f"Plant_{plant}_Generation_Data.csv")
    df["DATE_TIME"] = pd.to_datetime(df["DATE_TIME"], format=_GENERATION_FORMAT[plant])
    return df


def _load_weather(plant: int) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / f"Plant_{plant}_Weather_Sensor_Data.csv")
    df["DATE_TIME"] = pd.to_datetime(df["DATE_TIME"], format="%Y-%m-%d %H:%M:%S")
    return df


_cache: dict[int, pd.DataFrame] = {}


def load_plant(plant: int) -> pd.DataFrame:
    if plant in _cache:
        return _cache[plant]

    gen = _load_generation(plant)
    weather = _load_weather(plant).drop(columns=["PLANT_ID", "SOURCE_KEY"])
    merged = gen.merge(weather, on="DATE_TIME", how="left")
    merged["PLANT"] = plant

    _cache[plant] = merged
    return merged
