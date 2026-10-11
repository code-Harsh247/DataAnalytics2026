"""Evaluation harness: one time-based split, every registered model, same
metrics -- so the model comparison is apples to apples.

Usage (from webapp/backend):
    .venv/bin/python -m app.models.evaluate --data data/backfill/sample_plant.csv
    .venv/bin/python -m app.models.evaluate --data ... --model random_forest
"""

import argparse

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, mean_absolute_error, precision_score, r2_score, recall_score

from . import get_registry
from .base import LABEL_COLUMNS, OUTPUT_COLUMNS, AnomalyModel

TRAIN_FRACTION = 0.7  # first 70% of timestamps train, last 30% test -- no shuffling


def load_dataset(path: str) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["timestamp"])


def time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    times = np.sort(df["timestamp"].unique())
    cutoff = times[int(len(times) * TRAIN_FRACTION)]
    return df[df["timestamp"] < cutoff], df[df["timestamp"] >= cutoff]


def fit_and_score(model: AnomalyModel, train: pd.DataFrame, test: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Fits on train, predicts test, scores against the labels. Returns the
    metrics and the test predictions (with labels re-attached)."""
    model.fit(train.drop(columns=LABEL_COLUMNS))
    pred = model.predict(test.drop(columns=LABEL_COLUMNS))

    missing = [c for c in OUTPUT_COLUMNS if c not in pred.columns]
    if missing:
        raise ValueError(f"{model.name}.predict() is missing columns: {missing}")

    pred = pred.join(test[LABEL_COLUMNS])
    day = pred[pred["is_daylight"]]
    y_true, y_pred = day["is_fault"].astype(bool), day["flagged"].astype(bool)

    # Undefined metrics are None, not 0: a test window with no faults says
    # nothing about recall, and a model that flags nothing has no precision.
    has_faults, has_flags = bool(y_true.any()), bool(y_pred.any())
    result = {
        "model": model.name,
        "precision": round(precision_score(y_true, y_pred), 3) if has_flags else None,
        "recall": round(recall_score(y_true, y_pred), 3) if has_faults else None,
        "f1": round(f1_score(y_true, y_pred), 3) if has_faults else None,
        "r2": None,
        "mae_kw": None,
    }
    # Power-fit quality is judged on healthy daylight rows only: the model is
    # meant to predict *healthy* output, so faulted rows aren't its target.
    healthy = day[~y_true & day["expected_kw"].notna()]
    if len(healthy):
        result["r2"] = round(r2_score(healthy["ac_power_kw"], healthy["expected_kw"]), 3)
        result["mae_kw"] = round(mean_absolute_error(healthy["ac_power_kw"], healthy["expected_kw"]), 4)
    return result, pred


def evaluate_model(model: AnomalyModel, train: pd.DataFrame, test: pd.DataFrame) -> dict:
    return fit_and_score(model, train, test)[0]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--model", help="evaluate only this model (default: all)")
    args = p.parse_args()

    registry = get_registry()
    names = [args.model] if args.model else sorted(registry)
    if not names:
        print("No models registered yet -- add one in app/models/ (see base.py).")
        return

    train, test = time_split(load_dataset(args.data))
    print(f"train {train['timestamp'].min()} .. {train['timestamp'].max()}, "
          f"test {test['timestamp'].min()} .. {test['timestamp'].max()}, "
          f"test faulted daylight rows: {int(test[test['is_daylight']]['is_fault'].sum())}")
    rows = [evaluate_model(registry[n](), train, test) for n in names]
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
