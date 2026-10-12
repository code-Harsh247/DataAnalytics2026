"""A3 + A5 + the severity half of A2, from one pooled run of every model on
seeds 1-8 (the FINDINGS.md section 1 protocol):

- A3: 95% confidence intervals for F1 by a *day-block* bootstrap (hours
  within a day are correlated, so whole (seed, day) blocks are resampled),
  plus paired tests: Wilcoxon signed-rank on the 8 per-seed F1 pairs and a
  block-bootstrap CI for the pooled F1 difference.
- A5: episode-level detection -- the share of fault episodes caught, time
  to detect, and episode-level precision (false-alarm runs).
- A2 (severity): recall by fault severity, per hour and per episode.

    python -m analysis.model_stats
"""

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
from sklearn.metrics import f1_score

from .common import COLORS, MODEL_LABELS, MODEL_ORDER, OUT, SEEDS, dataset, run_models, save, write_json

N_BOOT = 2000
SEVERITY_BINS = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
rng = np.random.default_rng(0)


def pooled_predictions() -> pd.DataFrame:
    """Test-window predictions of every model on every seed, cached."""
    path = OUT / "predictions.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["timestamp"])
    frames = []
    for seed in SEEDS:
        for name, (_, pred) in run_models(dataset(seed)).items():
            frames.append(pred.assign(seed=seed, model=name)[[
                "seed", "model", "timestamp", "inverter", "is_daylight", "ac_power_kw", "expected_kw",
                "anomaly_score", "flagged", "is_fault", "fault_severity",
            ]])
        print(f"  seed {seed} done")
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(path, index=False)
    return df


# ---------------------------------------------------------------- A3

def _f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return f1_score(y_true, y_pred, zero_division=0.0)


def bootstrap(day: pd.DataFrame) -> dict:
    """Day-block bootstrap of pooled F1 per model and of RF-vs-model differences."""
    day = day.assign(block=day["seed"].astype(str) + "/" + day["timestamp"].dt.strftime("%m-%d"))
    blocks = day["block"].unique()
    by_model = {m: day[day["model"] == m] for m in MODEL_ORDER}
    # index each model's rows by block once
    idx = {m: {b: g.index.to_numpy() for b, g in d.groupby("block")} for m, d in by_model.items()}
    y = day["is_fault"].to_numpy(bool)
    f = day["flagged"].to_numpy(bool)

    point = {m: _f1(y[d.index], f[d.index]) for m, d in by_model.items()}
    samples = {m: np.empty(N_BOOT) for m in MODEL_ORDER}
    for b in range(N_BOOT):
        chosen = rng.choice(blocks, size=len(blocks), replace=True)
        for m in MODEL_ORDER:
            rows = np.concatenate([idx[m][c] for c in chosen])
            samples[m][b] = _f1(y[rows], f[rows])

    out = {"n_blocks": int(len(blocks)), "models": {}, "differences_vs_rf": {}}
    for m in MODEL_ORDER:
        lo, hi = np.quantile(samples[m], [0.025, 0.975])
        out["models"][m] = {"f1": round(point[m], 3), "ci95": [round(lo, 3), round(hi, 3)]}
    for m in MODEL_ORDER[1:]:
        diff = samples["random_forest"] - samples[m]
        lo, hi = np.quantile(diff, [0.025, 0.975])
        out["differences_vs_rf"][m] = {
            "diff": round(point["random_forest"] - point[m], 3), "ci95": [round(lo, 3), round(hi, 3)],
            "share_of_resamples_rf_better": round(float((diff > 0).mean()), 3),
        }
    return out


def paired_tests(day: pd.DataFrame) -> dict:
    per_seed = (day.groupby(["model", "seed"])
                .apply(lambda g: _f1(g["is_fault"].to_numpy(bool), g["flagged"].to_numpy(bool)), include_groups=False)
                .unstack("seed"))
    out = {"per_seed_f1": {m: [round(float(v), 3) for v in per_seed.loc[m]] for m in MODEL_ORDER}}
    tests = {}
    for m in MODEL_ORDER[1:]:
        d = per_seed.loc["random_forest"] - per_seed.loc[m]
        stat, p = wilcoxon(per_seed.loc["random_forest"], per_seed.loc[m])
        tests[m] = {"mean_diff": round(float(d.mean()), 3), "rf_wins": int((d > 0).sum()), "p_value": round(float(p), 4)}
    out["wilcoxon_vs_rf"] = tests
    return out


# ---------------------------------------------------------------- A5 + severity

def episodes(model_rows: pd.DataFrame) -> pd.DataFrame:
    """True fault episodes in one model's predictions: runs of consecutive
    faulted hours with the same severity, per seed and inverter."""
    out = []
    for (seed, inv), g in model_rows.sort_values("timestamp").groupby(["seed", "inverter"]):
        new = (~g["is_fault"]) | (g["timestamp"].diff() != pd.Timedelta(hours=1)) | (g["fault_severity"].diff() != 0)
        run = new.cumsum()
        for _, e in g[g["is_fault"]].groupby(run[g["is_fault"]]):
            daylight = e[e["is_daylight"]]
            if daylight.empty:
                continue  # a night-only episode has nothing to detect
            flagged = daylight[daylight["flagged"]]
            out.append({
                "seed": seed, "inverter": inv, "severity": float(e["fault_severity"].iloc[0]),
                "daylight_hours": len(daylight), "detected": not flagged.empty,
                # in daylight hours, counted from the episode's first daylight hour
                "hours_to_detect": int(np.argmax(daylight["flagged"].to_numpy())) if not flagged.empty else None,
            })
    return pd.DataFrame(out)


def false_alarm_runs(model_rows: pd.DataFrame) -> tuple[int, int]:
    """(flagged runs, flagged runs that touch no faulted hour), over daylight rows."""
    total = false = 0
    for _, g in model_rows[model_rows["is_daylight"]].sort_values("timestamp").groupby(["seed", "inverter"]):
        run = (g["flagged"] != g["flagged"].shift()).cumsum()
        for _, r in g[g["flagged"]].groupby(run[g["flagged"]]):
            total += 1
            false += int(not r["is_fault"].any())
    return total, false


def episode_stats(day_all: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    summary, frames = {}, []
    for m in MODEL_ORDER:
        rows = day_all[day_all["model"] == m]
        ep = episodes(rows).assign(model=m)
        frames.append(ep)
        runs, false = false_alarm_runs(rows)
        caught = ep[ep["detected"]]
        summary[m] = {
            "episodes": int(len(ep)), "caught": int(len(caught)),
            "episode_recall": round(float(ep["detected"].mean()), 3),
            "median_hours_to_detect": float(caught["hours_to_detect"].median()) if len(caught) else None,
            "detected_within_1h": round(float((caught["hours_to_detect"] <= 1).mean()), 3) if len(caught) else None,
            "alarm_runs": runs, "false_alarm_runs": false,
            "episode_precision": round(1 - false / runs, 3) if runs else None,
        }
    return summary, pd.concat(frames, ignore_index=True)


def severity_recall(day: pd.DataFrame, eps: pd.DataFrame) -> dict:
    labels = [f"{int(a * 100)}–{int(b * 100)}%" for a, b in zip(SEVERITY_BINS[:-1], SEVERITY_BINS[1:])]
    faulted = day[day["is_fault"]].copy()
    faulted["bin"] = pd.cut(faulted["fault_severity"], SEVERITY_BINS, labels=labels, include_lowest=True)
    eps = eps.copy()
    eps["bin"] = pd.cut(eps["severity"], SEVERITY_BINS, labels=labels, include_lowest=True)
    out = {"bins": labels, "hourly_recall": {}, "episode_recall": {}, "hours_per_bin": {}, "episodes_per_bin": {}}
    for m in MODEL_ORDER:
        hourly = faulted[faulted["model"] == m].groupby("bin", observed=False)["flagged"].mean()
        episodic = eps[eps["model"] == m].groupby("bin", observed=False)["detected"].mean()
        out["hourly_recall"][m] = [None if pd.isna(v) else round(float(v), 3) for v in hourly.reindex(labels)]
        out["episode_recall"][m] = [None if pd.isna(v) else round(float(v), 3) for v in episodic.reindex(labels)]
    rf = faulted[faulted["model"] == "random_forest"]
    out["hours_per_bin"] = [int(x) for x in rf.groupby("bin", observed=False).size().reindex(labels)]
    rf_eps = eps[eps["model"] == "random_forest"]
    out["episodes_per_bin"] = [int(x) for x in rf_eps.groupby("bin", observed=False).size().reindex(labels)]
    return out


# ---------------------------------------------------------------- figures

def figures(boot: dict, sev: dict, eps: pd.DataFrame) -> dict:
    import matplotlib.pyplot as plt

    paths = {}
    fig, ax = plt.subplots(figsize=(5.2, 2.6))
    names = MODEL_ORDER[::-1]
    for i, m in enumerate(names):
        f1, (lo, hi) = boot["models"][m]["f1"], boot["models"][m]["ci95"]
        ax.errorbar(f1, i, xerr=[[f1 - lo], [hi - f1]], fmt="o", color=COLORS[m], capsize=4, lw=2)
        ax.text(hi + 0.008, i, f"{f1:.3f}  [{lo:.3f}, {hi:.3f}]", va="center", fontsize=8)
    ax.set_yticks(range(len(names)), [MODEL_LABELS[m] for m in names])
    ax.set_xlabel("F1, pooled over seeds 1–8 (95% day-block bootstrap CI)")
    ax.set_xlim(0.45, 0.88)
    paths["f1_ci"] = save(fig, "f1_ci")

    fig, axes = plt.subplots(1, 2, figsize=(8, 2.8), sharey=True)
    x = np.arange(len(sev["bins"]))
    for ax, key, title in [(axes[0], "hourly_recall", "Per hour"), (axes[1], "episode_recall", "Per episode (caught at all)")]:
        for m in MODEL_ORDER:
            ax.plot(x, [np.nan if v is None else v for v in sev[key][m]], "o-", color=COLORS[m], label=MODEL_LABELS[m])
        ax.set_xticks(x, sev["bins"])
        ax.set_xlabel("fault severity (share of output lost)")
        ax.set_title(title)
        ax.set_ylim(0, 1.05)
    axes[0].set_ylabel("recall")
    axes[1].legend(fontsize=7, loc="lower right")
    paths["recall_by_severity"] = save(fig, "recall_by_severity")

    fig, ax = plt.subplots(figsize=(4.6, 2.6))
    caught = eps[eps["detected"] & (eps["model"] == "random_forest")]
    counts = caught["hours_to_detect"].clip(upper=5).value_counts().sort_index()
    ax.bar([str(int(i)) if i < 5 else "5+" for i in counts.index], counts.to_numpy(), color=COLORS["random_forest"])
    ax.set_xlabel("daylight hours from fault start to first flag (Random Forest)")
    ax.set_ylabel("episodes")
    paths["time_to_detect"] = save(fig, "time_to_detect")
    return paths


def main() -> dict:
    preds = pooled_predictions()
    day = preds[preds["is_daylight"]].reset_index(drop=True)
    boot = bootstrap(day)
    tests = paired_tests(day)
    ep_summary, eps = episode_stats(preds)
    sev = severity_recall(day, eps)
    result = {"bootstrap": boot, "paired": tests, "episodes": ep_summary, "severity": sev,
              "figures": figures(boot, sev, eps)}
    write_json("model_stats", result)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(main(), indent=1, default=float)[:6000])
