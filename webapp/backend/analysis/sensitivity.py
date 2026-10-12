"""A2 (noise half): how detection quality depends on the simulator's noise
settings. Regenerates the canonical datasets with one setting changed at a
time and reruns every model:

- NOISE_STD: per-inverter measurement noise (default 3%)
- SITE_IRRADIANCE_ERROR_STD: gap between reported and on-site sunlight,
  shared by the whole plant (default 6%)

Seeds 1-4 per level (the harness takes ~6 s per dataset for all models).

    python -m analysis.sensitivity
"""

import numpy as np
import pandas as pd

from .common import COLORS, MODEL_LABELS, MODEL_ORDER, dataset, run_models, save, write_json

SEEDS = [1, 2, 3, 4]
SWEEPS = {
    "NOISE_STD": [0.01, 0.03, 0.05, 0.08],
    "SITE_IRRADIANCE_ERROR_STD": [0.02, 0.06, 0.10, 0.15],
}
DEFAULTS = {"NOISE_STD": 0.03, "SITE_IRRADIANCE_ERROR_STD": 0.06}
LABELS = {"NOISE_STD": "measurement noise (per inverter)", "SITE_IRRADIANCE_ERROR_STD": "site sunlight error (whole plant)"}


def sweep() -> pd.DataFrame:
    rows = []
    for setting, levels in SWEEPS.items():
        for level in levels:
            for seed in SEEDS:
                for name, (metrics, _) in run_models(dataset(seed, **{setting: level})).items():
                    rows.append({"setting": setting, "level": level, "seed": seed, "model": name,
                                 "f1": metrics["f1"], "precision": metrics["precision"], "recall": metrics["recall"]})
            print(f"  {setting}={level} done")
    return pd.DataFrame(rows)


def figure(table: dict) -> str:
    """Mean F1 per model against each setting, from the result table."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(8, 3.0), sharey=True)
    for ax, setting in zip(axes, SWEEPS):
        for m in MODEL_ORDER:
            levels = [float(x) * 100 for x in table[setting][m]]
            ax.plot(levels, list(table[setting][m].values()), "o-", color=COLORS[m], label=MODEL_LABELS[m])
        ax.axvline(DEFAULTS[setting] * 100, color="#9ca3af", ls=":", lw=1)
        ax.set_title(LABELS[setting].capitalize(), fontsize=9)
        ax.set_xlabel("standard deviation, % (dotted = default)")
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("mean F1 (seeds 1–4)")
    axes[1].legend(fontsize=7)
    return save(fig, "sensitivity_noise")


def main() -> dict:
    df = sweep()
    table = {}
    for setting in SWEEPS:
        mean = df[df["setting"] == setting].groupby(["model", "level"])["f1"].mean().unstack("level")
        table[setting] = {m: {f"{lvl:.2f}": round(float(mean.loc[m, lvl]), 3) for lvl in mean.columns} for m in MODEL_ORDER}
    result = {"seeds": SEEDS, "f1": table, "figure": figure(table)}
    write_json("sensitivity", result)
    return result


if __name__ == "__main__":
    import json
    import sys

    from .common import OUT

    if "--figure-only" in sys.argv:  # redraw from the saved results, no rerun
        print(figure(json.loads((OUT / "sensitivity.json").read_text())["f1"]))
    else:
        print(json.dumps(main(), indent=1))
