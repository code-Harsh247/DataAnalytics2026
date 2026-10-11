"""Model 3: Gradient Boosting expected-power model + residual threshold.

Deliberately the same recipe as random_forest.py -- same features, robust
refit, label-free threshold and 3-hour smoothing -- with only the learner
swapped, so any difference in the comparison is down to boosting vs bagging
rather than to a different pipeline. The small helpers are repeated here
instead of imported because random_forest.py is another model's file.

One real difference: HistGradientBoostingRegressor has no out-of-bag
predictions, and in-sample residuals of a boosted model are far smaller
than its real error, which would set the threshold too tight and flag
everything. So the held-out residuals come from 5-fold cross-validation on
the train window instead, with *shuffled* folds -- the closest analogue of
out-of-bag, which also holds out random rows. Contiguous (time-block) folds
were tried first and were much worse (mean F1 0.51 vs 0.68 over seeds 1-8,
see FINDINGS.md): each block is a weather stretch the model never saw, so
the worst residuals were unusual-but-healthy hours rather than faults. That
both loosened the threshold and made the trimmed refit drop healthy rows
while keeping the faulty ones.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold, cross_val_predict

from .base import WEATHER_FEATURES, AnomalyModel, add_peer_features, smooth_daylight_scores

FEATURES = WEATHER_FEATURES + ["peer_median_kw", "inverter_code"]
CV_FOLDS = 5
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


class GradientBoostingModel(AnomalyModel):
    name = "gradient_boosting"

    def _new_model(self) -> HistGradientBoostingRegressor:
        return HistGradientBoostingRegressor(
            max_iter=300,
            learning_rate=0.05,
            # sklearn's default of 20 smooths over the sharp peer relationship
            # (mean average precision 0.55 -> 0.76 going to 5 on seeds 1-8).
            min_samples_leaf=5,
            # Inverters are labels, not quantities: INV-3 isn't "more" than INV-2.
            categorical_features=[FEATURES.index("inverter_code")],
            random_state=42,
        )

    def fit(self, train: pd.DataFrame) -> None:
        day = _prepare(train)
        day = day[day["is_daylight"]]
        X, y = day[FEATURES], day["ac_power_kw"]

        folds = KFold(CV_FOLDS, shuffle=True, random_state=42)
        held_out = cross_val_predict(self._new_model(), X, y, cv=folds)
        shortfall = _relative_shortfall(held_out, y.to_numpy())
        median = np.median(shortfall)
        sigma = MAD_TO_SIGMA * np.median(np.abs(shortfall - median))
        self.threshold = median + SIGMA_K * sigma

        keep = shortfall <= np.quantile(shortfall, TRIM_QUANTILE)
        self.model = self._new_model().fit(X[keep], y[keep])

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = _prepare(df)
        out = df.copy()
        out["expected_kw"] = np.where(
            out["is_daylight"], self.model.predict(prepared[FEATURES]), 0.0,
        )
        out["anomaly_score"] = _relative_shortfall(out["expected_kw"].to_numpy(), out["ac_power_kw"].to_numpy())
        out["anomaly_score"] = smooth_daylight_scores(out)
        out["flagged"] = out["is_daylight"] & (out["anomaly_score"] > self.threshold)
        return out
