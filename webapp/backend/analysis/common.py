"""Shared pieces for the analysis scripts: the canonical benchmark datasets,
running every model through the existing harness, and figure styling.

Datasets are regenerated from the canonical arguments (data/backfill/
sample_plant.meta.json) with seeds 1-8, exactly like FINDINGS.md section 1,
fetching the archive weather once and caching it under analysis/out/.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # files only, no window
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from app.backfill import build_dataset, fetch_historical_weather  # noqa: E402
from app.models import get_registry  # noqa: E402
from app.models.evaluate import fit_and_score, time_split  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
FIGURES = ROOT / "figures"
META = ROOT.parent / "data" / "backfill" / "sample_plant.meta.json"
SEEDS = list(range(1, 9))
MODEL_ORDER = ["random_forest", "gradient_boosting", "baseline_ratio", "isolation_forest"]
MODEL_LABELS = {
    "random_forest": "Random Forest", "gradient_boosting": "Gradient Boosting",
    "baseline_ratio": "Physics baseline", "isolation_forest": "Isolation Forest",
}
COLORS = {
    "random_forest": "#2563eb", "gradient_boosting": "#7c3aed",
    "baseline_ratio": "#9ca3af", "isolation_forest": "#f59e0b",
}

OUT.mkdir(exist_ok=True)
FIGURES.mkdir(exist_ok=True)
plt.rcParams.update({
    "figure.dpi": 130, "savefig.bbox": "tight", "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.3,
})


def canonical_args() -> dict:
    return json.loads(META.read_text())


def canonical_weather() -> pd.DataFrame:
    """The benchmark's archive weather, fetched once and cached."""
    path = OUT / "canonical_weather.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["timestamp"])
    a = canonical_args()
    weather = fetch_historical_weather(a["lat"], a["lon"], a["start"], a["end"])
    weather.to_csv(path, index=False)
    return weather


def dataset(seed: int, **overrides) -> pd.DataFrame:
    """The canonical dataset for a seed. `overrides` patch backfill module
    constants (e.g. NOISE_STD=0.05) for the sensitivity runs."""
    import app.backfill as bf

    a = canonical_args()
    saved = {k: getattr(bf, k) for k in overrides}
    try:
        for k, v in overrides.items():
            setattr(bf, k, v)
        return build_dataset(
            a["lat"], a["lon"], a["start"], a["end"], capacity_kw=a["capacity_kw"], tilt=a["tilt"],
            azimuth=a["azimuth"], inverter_count=a["inverters"], temp_coefficient=a["temp_coefficient"],
            degradation_factor=a["degradation_factor"], seed=seed, weather=canonical_weather(),
        )
    finally:
        for k, v in saved.items():
            setattr(bf, k, v)


def run_models(df: pd.DataFrame, models: list[str] | None = None) -> dict[str, tuple[dict, pd.DataFrame]]:
    """Every (or the given) registered model on the harness's time split:
    {name: (metrics, test predictions with labels)}."""
    registry = get_registry()
    train, test = time_split(df)
    return {name: fit_and_score(registry[name](), train, test) for name in (models or MODEL_ORDER)}


def save(fig, name: str) -> str:
    path = FIGURES / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    return f"figures/{name}.png"


def write_json(name: str, data) -> None:
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2, default=float) + "\n")
