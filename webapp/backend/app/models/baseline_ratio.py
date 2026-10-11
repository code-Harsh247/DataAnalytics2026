"""Reference baseline: a single plant-wide power/irradiance ratio learned on
the train window, flag when an inverter falls more than THRESHOLD below it.
No ML -- this is the bar every real model has to clear."""

import pandas as pd

from .base import AnomalyModel

THRESHOLD = 0.12  # flag at >12% below expected
MIN_EXPECTED_KW = 0.05  # avoid dividing by ~0 at dawn/dusk


class RatioBaseline(AnomalyModel):
    name = "baseline_ratio"

    def fit(self, train: pd.DataFrame) -> None:
        day = train[train["is_daylight"] & (train["poa_irradiance"] > 0)]
        self.kw_per_wm2 = float((day["ac_power_kw"] / day["poa_irradiance"]).median())

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["expected_kw"] = self.kw_per_wm2 * out["poa_irradiance"]
        out["anomaly_score"] = (out["expected_kw"] - out["ac_power_kw"]) / out["expected_kw"].clip(lower=MIN_EXPECTED_KW)
        out["flagged"] = out["is_daylight"] & (out["anomaly_score"] > THRESHOLD)
        return out
