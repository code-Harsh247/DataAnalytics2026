"""Model 1: Random Forest expected-power model + residual threshold -- the
same approach as the original Plant 1/2 analysis (fault_model.py), adapted
to the backfill dataset.

Predicts each inverter's healthy AC output from weather + its peers' output,
then flags hours where actual falls well short of expected. Labels are never
seen, so two label-free tricks keep it honest:
- Robust refit: fault hours are in the training data too (unlabeled), so fit
  once, drop the rows with the worst out-of-bag residuals, refit.
- The threshold comes from the spread of out-of-bag residuals on the train
  window (median + K robust standard deviations), not from tuning against
  the labels. Spread is measured on the first, untrimmed fit: trimming cuts
  one tail and makes the noise look smaller than it is.
- Scores are smoothed with a centered 3-hour rolling median per inverter,
  which suppresses single-hour noise spikes (real faults last 2+ hours).
  Centered = uses the next hour too; fine for this retrospective analysis,
  would need to be trailing for live alerting.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from .base import WEATHER_FEATURES, AnomalyModel, add_peer_features, smooth_daylight_scores

FEATURES = WEATHER_FEATURES + ["peer_median_kw", "inverter_code"]
TRIM_QUANTILE = 0.9  # keep the 90% best-explained rows for the refit
SIGMA_K = 2.5
MAD_TO_SIGMA = 1.4826  # MAD -> standard deviation for normally distributed noise
MIN_EXPECTED_KW = 0.05


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = add_peer_features(df)
    out["inverter_code"] = out["inverter"].str.extract(r"(\d+)$")[0].astype(int)
    return out


def _relative_shortfall(expected: np.ndarray, actual: np.ndarray) -> np.ndarray:
    return (expected - actual) / np.clip(expected, MIN_EXPECTED_KW, None)


class RandomForestModel(AnomalyModel):
    name = "random_forest"

    def _new_forest(self) -> RandomForestRegressor:
        return RandomForestRegressor(
            n_estimators=300, min_samples_leaf=3, oob_score=True, n_jobs=-1, random_state=42,
        )

    def fit(self, train: pd.DataFrame) -> None:
        day = _prepare(train)
        day = day[day["is_daylight"]]
        X, y = day[FEATURES], day["ac_power_kw"]

        first = self._new_forest().fit(X, y)
        shortfall = _relative_shortfall(first.oob_prediction_, y.to_numpy())
        median = np.median(shortfall)
        sigma = MAD_TO_SIGMA * np.median(np.abs(shortfall - median))
        self.threshold = median + SIGMA_K * sigma

        keep = shortfall <= np.quantile(shortfall, TRIM_QUANTILE)
        self.forest = self._new_forest().fit(X[keep], y[keep])

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = _prepare(df)
        out = df.copy()
        out["expected_kw"] = np.where(
            out["is_daylight"], self.forest.predict(prepared[FEATURES]), 0.0,
        )
        out["anomaly_score"] = _relative_shortfall(out["expected_kw"].to_numpy(), out["ac_power_kw"].to_numpy())
        out["anomaly_score"] = smooth_daylight_scores(out)
        out["flagged"] = out["is_daylight"] & (out["anomaly_score"] > self.threshold)
        return out
