"""Model 2: Isolation Forest -- fully unsupervised, no expected-power model.

Tests whether a detector that never learns "what healthy output should be"
can still find faults just by spotting unusual combinations of conditions
and output. Features describe the operating point (sun, temperature, cloud)
and how the inverter is performing relative to the sun and to its peers.

Isolation Forest also isolates *over*-performing hours (e.g. a peer having a
bad hour), which aren't faults, so a flag additionally requires the inverter
to be below its peers. Its contamination setting is the expected anomaly
rate -- a prior about the plant, not something tuned on labels.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .base import AnomalyModel, add_peer_features, smooth_daylight_scores

FEATURES = ["poa_irradiance", "cell_temp", "cloud_cover", "solar_elevation", "kw_per_poa", "ratio_to_peers"]
CONTAMINATION = 0.08  # prior: a plant is faulted well under 10% of daylight hours
MIN_PEER_KW = 0.05


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = add_peer_features(df)
    out["kw_per_poa"] = out["ac_power_kw"] / out["poa_irradiance"].clip(lower=1.0) * 1000
    out["ratio_to_peers"] = out["ac_power_kw"] / out["peer_median_kw"].clip(lower=MIN_PEER_KW)
    return out


class IsolationForestModel(AnomalyModel):
    name = "isolation_forest"

    def fit(self, train: pd.DataFrame) -> None:
        day = _prepare(train)
        day = day[day["is_daylight"]]
        self.forest = IsolationForest(
            n_estimators=300, contamination=CONTAMINATION, random_state=42,
        ).fit(day[FEATURES])
        # decision_function < 0 means "anomalous" at the contamination rate,
        # so its negation is a score where > 0 is anomalous.
        self.threshold = 0.0

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = _prepare(df)
        out = df.copy()
        out["expected_kw"] = np.nan
        out["anomaly_score"] = np.where(
            out["is_daylight"], -self.forest.decision_function(prepared[FEATURES].fillna(0)), -1.0,
        )
        out["anomaly_score"] = smooth_daylight_scores(out)
        below_peers = prepared["ratio_to_peers"] < 1.0
        out["flagged"] = out["is_daylight"] & below_peers & (out["anomaly_score"] > self.threshold)
        return out
