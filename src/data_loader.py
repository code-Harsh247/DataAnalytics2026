"""Load and merge the Plant 1 / Plant 2 generation + weather sensor data."""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


_GENERATION_FORMAT = {1: "%d-%m-%Y %H:%M", 2: "%Y-%m-%d %H:%M:%S"}


def _load_generation(plant: int) -> pd.DataFrame:
    # Format differs *between plants*, not just between generation/weather files:
    # Plant 1 uses DD-MM-YYYY HH:MM, Plant 2 is already ISO. Do NOT use
    # format="mixed" here — pandas' per-element inference misreads ambiguous
    # ISO dates like 2020-06-01 (day<=12) as Jan 6 instead of June 1 when
    # dayfirst=True is set globally. Explicit per-plant format avoids that.
    df = pd.read_csv(RAW_DIR / f"Plant_{plant}_Generation_Data.csv")
    df["DATE_TIME"] = pd.to_datetime(df["DATE_TIME"], format=_GENERATION_FORMAT[plant])
    return df


def _load_weather(plant: int) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / f"Plant_{plant}_Weather_Sensor_Data.csv")
    df["DATE_TIME"] = pd.to_datetime(df["DATE_TIME"], format="%Y-%m-%d %H:%M:%S")
    return df


def load_plant(plant: int) -> pd.DataFrame:
    """Return generation data (per-inverter) joined with plant-level weather.

    Weather is measured once per plant per timestamp (single sensor), so it is
    broadcast across all inverters (SOURCE_KEY) at that timestamp.
    """
    gen = _load_generation(plant)
    weather = _load_weather(plant).drop(columns=["PLANT_ID", "SOURCE_KEY"])

    merged = gen.merge(weather, on="DATE_TIME", how="left")
    merged["PLANT"] = plant
    return merged


def load_all() -> pd.DataFrame:
    return pd.concat([load_plant(1), load_plant(2)], ignore_index=True)


if __name__ == "__main__":
    df = load_all()
    print(df.shape)
    print(df.dtypes)
    print(df.isna().sum())
    print(df.head())
