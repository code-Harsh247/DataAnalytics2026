"""Shared interface for the anomaly models compared in evaluate.py.

Every model is one file in app/models/ defining one AnomalyModel subclass
with a unique `name`. Models are discovered automatically (see __init__.py),
so adding a model never means editing a shared file.

Contract:
- fit() and predict() never see the label columns (LABEL_COLUMNS) -- the
  harness strips them, the same way a real plant has no fault labels.
- predict() returns the input frame plus three columns:
    expected_kw    predicted healthy AC power, or NaN if the model doesn't
                   predict power (e.g. Isolation Forest)
    anomaly_score  higher = more anomalous (any scale)
    flagged        bool, the model's final fault call for that row
- Night rows are passed through too; models can flag them however they like,
  but evaluation only scores daylight rows (a fault at night is invisible).

Minimal example:

    class RatioThreshold(AnomalyModel):
        name = "ratio_threshold"

        def fit(self, train):
            day = train[train["is_daylight"]]
            self.k = (day["ac_power_kw"] / day["poa_irradiance"]).median()

        def predict(self, df):
            out = df.copy()
            out["expected_kw"] = self.k * out["poa_irradiance"]
            out["anomaly_score"] = (out["expected_kw"] - out["ac_power_kw"]) / out["expected_kw"].clip(lower=0.05)
            out["flagged"] = out["anomaly_score"] > 0.12
            return out
"""

from abc import ABC, abstractmethod

import pandas as pd

LABEL_COLUMNS = ["is_fault", "fault_severity"]

# Columns models may use as inputs. ac_power_kw/dc_power_kw are the observed
# output -- a model predicting expected power must not use them as features
# (its own output, that is; peer inverters via add_peer_features() are fine).
WEATHER_FEATURES = [
    "ghi", "dni", "dhi", "poa_irradiance", "air_temp", "cell_temp",
    "wind_speed", "cloud_cover", "solar_elevation",
]
OUTPUT_COLUMNS = ["expected_kw", "anomaly_score", "flagged"]


def add_peer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Adds peer_median_kw: median ac_power_kw of the *other* inverters at the
    same timestamp. Allowed as a feature (unlike an inverter's own output):
    it's what real fleet monitoring compares against, and it absorbs the
    plant-wide gap between reported weather and the sun the panels actually
    saw, which no weather feature can explain."""
    out = df.copy()
    power = out.pivot(index="timestamp", columns="inverter", values="ac_power_kw")
    peers = pd.DataFrame(
        {inv: power.drop(columns=inv).median(axis=1) for inv in power.columns}
    ).stack().rename("peer_median_kw")
    peers.index.names = ["timestamp", "inverter"]
    return out.join(peers, on=["timestamp", "inverter"])


def smooth_daylight_scores(df: pd.DataFrame, smooth_hours: int = 3) -> pd.Series:
    """Centered rolling median of anomaly_score over consecutive daylight
    hours of each inverter; night rows are left as-is. Centered = uses the
    next hour too: fine for retrospective analysis, not for live alerting."""
    day = df[df["is_daylight"]].sort_values(["inverter", "timestamp"])
    smoothed = day.groupby("inverter")["anomaly_score"].transform(
        lambda s: s.rolling(smooth_hours, center=True, min_periods=1).median()
    )
    return smoothed.reindex(df.index).fillna(df["anomaly_score"])


class AnomalyModel(ABC):
    name: str = ""

    @abstractmethod
    def fit(self, train: pd.DataFrame) -> None: ...

    @abstractmethod
    def predict(self, df: pd.DataFrame) -> pd.DataFrame: ...
