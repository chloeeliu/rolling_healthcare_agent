from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


BASE = Path("/Users/chloe/Documents/New project")
AUTOFORM_DIR = BASE / "result" / "rolling_eval_autoform"
ZEROSHOT_DIR = BASE / "result" / "rolling_eval_zeroshot"
OUT_DIR = BASE / "docs" / "surveilance" / "figures"

QWEN_MODELS = ["Qwen3.5-27B", "Qwen3.5-9B", "Qwen3.5-4B"]
QWEN_COLORS = {
    "Qwen3.5-27B": "#0d3b66",
    "Qwen3.5-9B": "#2a9d8f",
    "Qwen3.5-4B": "#e76f51",
}
FAMILY_COLORS = {"closed-source": "#264653", "open-weight": "#e76f51"}


def set_f1(gt_items: list[str], pred_items: list[str]) -> tuple[float, float, float]:
    gt = set(gt_items or [])
    pred = set(pred_items or [])
    tp = len(gt & pred)
    fp = len(pred - gt)
    fn = len(gt - pred)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not pred and not gt else 0.0)
    recall = tp / (tp + fn) if tp + fn else (1.0 if not pred and not gt else 0.0)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def load_rollouts(root: Path, model: str, benchmark: str) -> list[dict]:
    bench_dir = root / model / benchmark
    rollouts_path = bench_dir / "rollouts.json"
    if rollouts_path.exists():
        return json.loads(rollouts_path.read_text())
    return [json.loads(line) for line in (bench_dir / "trajectories.jsonl").open()]


def summarize_rollouts(rollouts: list[dict]) -> dict[str, float]:
    total_steps = 0
    ga = pr = sem = aem = 0
    sf1 = ap = ar = af1 = 0.0
    first_pairs: list[tuple[int | None, int | None]] = []
    strict = 0

    pos = {
        "sus_n": 0,
        "sus_exact": 0,
        "sus_f1": 0.0,
        "alert_n": 0,
        "alert_exact": 0,
        "alert_f1": 0.0,
        "alert_p": 0.0,
        "alert_r": 0.0,
    }

    neg = {"sus_n": 0, "sus_exact": 0, "alert_n": 0, "alert_exact": 0}

    gold_alert_trajectories = 0
    pred_continue = 0

    for rollout in rollouts:
        gt_first = pred_first = None
        perfect = True
        for step in rollout["steps"]:
            gt = step.get("gt_surveillance") or {}
            pred = step.get("predicted_surveillance") or {}
            gt_action = gt.get("global_action") or step.get("gt_action")
            pred_action = pred.get("global_action") or step.get("predicted_action")
            gt_priority = gt.get("priority")
            pred_priority = pred.get("priority")
            gt_sus = gt.get("suspected_conditions") or []
            pred_sus = pred.get("suspected_conditions") or []
            gt_alerts = gt.get("alerts") or []
            pred_alerts = pred.get("alerts") or []

            total_steps += 1
            ga += int(gt_action == pred_action)
            pr += int(gt_priority == pred_priority)
            sem += int(set(gt_sus) == set(pred_sus))
            aem += int(set(gt_alerts) == set(pred_alerts))
            pred_continue += int(pred_action == "continue_monitoring")

            _, _, sus_f1 = set_f1(gt_sus, pred_sus)
            alert_p, alert_r, alert_f1 = set_f1(gt_alerts, pred_alerts)
            sf1 += sus_f1
            ap += alert_p
            ar += alert_r
            af1 += alert_f1

            if not (
                gt_action == pred_action
                and gt_priority == pred_priority
                and set(gt_sus) == set(pred_sus)
                and set(gt_alerts) == set(pred_alerts)
            ):
                perfect = False

            if gt_first is None and gt_alerts:
                gt_first = step.get("t_hour")
            if pred_first is None and pred_alerts:
                pred_first = step.get("t_hour")

            if gt_sus:
                pos["sus_n"] += 1
                pos["sus_exact"] += int(set(gt_sus) == set(pred_sus))
                pos["sus_f1"] += sus_f1
            else:
                neg["sus_n"] += 1
                neg["sus_exact"] += int(set(gt_sus) == set(pred_sus))

            if gt_alerts:
                pos["alert_n"] += 1
                pos["alert_exact"] += int(set(gt_alerts) == set(pred_alerts))
                pos["alert_f1"] += alert_f1
                pos["alert_p"] += alert_p
                pos["alert_r"] += alert_r
            else:
                neg["alert_n"] += 1
                neg["alert_exact"] += int(set(gt_alerts) == set(pred_alerts))

        if gt_first is not None:
            gold_alert_trajectories += 1
        first_pairs.append((gt_first, pred_first))
        strict += int(perfect)

    errs = [abs(pred - gt) for gt, pred in first_pairs if gt is not None and pred is not None]
    false_early = sum(1 for gt, pred in first_pairs if gt is not None and pred is not None and pred < gt)
    missed = sum(1 for gt, pred in first_pairs if gt is not None and pred is None)

    return {
        "completed": len(rollouts),
        "global_action_accuracy": ga / total_steps,
        "priority_accuracy": pr / total_steps,
        "suspected_conditions_macro_f1": sf1 / total_steps,
        "alerts_macro_f1": af1 / total_steps,
        "alerts_macro_precision": ap / total_steps,
        "alerts_macro_recall": ar / total_steps,
        "suspected_conditions_exact_match": sem / total_steps,
        "alerts_exact_match": aem / total_steps,
        "first_alert_mean_abs_error_hours": sum(errs) / len(errs),
        "false_early_alert_trajectories": false_early,
        "missed_alert_trajectories": missed,
        "strict_all4_trajectory_rate": strict / len(rollouts),
        "positive_suspected_conditions_macro_f1": pos["sus_f1"] / pos["sus_n"] if pos["sus_n"] else 0.0,
        "positive_alerts_macro_f1": pos["alert_f1"] / pos["alert_n"] if pos["alert_n"] else 0.0,
        "positive_suspected_conditions_exact": pos["sus_exact"] / pos["sus_n"] if pos["sus_n"] else 0.0,
        "positive_alerts_exact": pos["alert_exact"] / pos["alert_n"] if pos["alert_n"] else 0.0,
        "negative_suspected_conditions_exact": neg["sus_exact"] / neg["sus_n"] if neg["sus_n"] else 0.0,
        "negative_alerts_exact": neg["alert_exact"] / neg["alert_n"] if neg["alert_n"] else 0.0,
        "pred_continue_rate": pred_continue / total_steps,
        "missed_alert_rate": missed / gold_alert_trajectories if gold_alert_trajectories else 0.0,
    }


def ensure_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT_DIR / f"{name}.png", dpi=220, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def plot_qwen_bottleneck(auto_metrics: dict[str, dict[str, float]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    x = np.arange(len(QWEN_MODELS))
    width = 0.18

    f1_series = [
        ("Overall Suspect F1", "suspected_conditions_macro_f1", "#457b9d"),
        ("Positive Suspect F1", "positive_suspected_conditions_macro_f1", "#a8dadc"),
        ("Overall Alert F1", "alerts_macro_f1", "#e76f51"),
        ("Positive Alert F1", "positive_alerts_macro_f1", "#f4a261"),
    ]
    for idx, (label, key, color) in enumerate(f1_series):
        vals = [auto_metrics[m][key] for m in QWEN_MODELS]
        axes[0].bar(x + (idx - 1.5) * width, vals, width=width, color=color, label=label)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(QWEN_MODELS, rotation=15)
    axes[0].set_ylim(0, 0.30)
    axes[0].set_title("Overall vs Positive-Only F1")
    axes[0].set_ylabel("Score")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False, fontsize=8)

    exact_series = [
        ("Overall Suspect Exact", "suspected_conditions_exact_match", "#457b9d"),
        ("Positive Suspect Exact", "positive_suspected_conditions_exact", "#a8dadc"),
        ("Overall Alert Exact", "alerts_exact_match", "#e76f51"),
        ("Positive Alert Exact", "positive_alerts_exact", "#f4a261"),
    ]
    for idx, (label, key, color) in enumerate(exact_series):
        vals = [auto_metrics[m][key] for m in QWEN_MODELS]
        axes[1].bar(x + (idx - 1.5) * width, vals, width=width, color=color, label=label)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(QWEN_MODELS, rotation=15)
    axes[1].set_ylim(0, 0.30)
    axes[1].set_title("Overall vs Positive-Only Exact Match")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(frameon=False, fontsize=8)

    fig.suptitle("Longitudinal Bottleneck in Completed Qwen benchmark_2k Runs", y=1.03, fontsize=14)
    save(fig, "qwen_benchmark2k_bottleneck_decomposition")


def plot_qwen_backend_comparison(
    auto_metrics: dict[str, dict[str, float]], zero_metrics: dict[str, dict[str, float]]
) -> None:
    metrics = [
        ("Global Action", "global_action_accuracy", (0.0, 0.45)),
        ("Alert F1", "alerts_macro_f1", (0.0, 0.30)),
        ("Positive Alert F1", "positive_alerts_macro_f1", (0.0, 0.06)),
        ("Positive Suspect F1", "positive_suspected_conditions_macro_f1", (0.0, 0.06)),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.5))
    axes = axes.flatten()
    for ax, (title, key, ylim) in zip(axes, metrics):
        for model in QWEN_MODELS:
            vals = [zero_metrics[model][key], auto_metrics[model][key]]
            ax.plot([0, 1], vals, marker="o", linewidth=2.5, color=QWEN_COLORS[model], label=model)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Zero-shot", "Autoformalization"])
        ax.set_ylim(*ylim)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.suptitle("Qwen benchmark_100: Backend Changes Accuracy and Failure Mode", y=1.01, fontsize=14)
    save(fig, "qwen_benchmark100_backend_comparison")


def plot_zeroshot_open_vs_closed(zero_metrics: dict[str, dict[str, float]]) -> None:
    models = [
        ("Gemini/gemini-3.1-pro-preview", "closed-source"),
        ("Claude/claude-sonnet-4-6", "closed-source"),
        ("GPT/gpt-5.4", "closed-source"),
        ("gpt-oss-120b", "open-weight"),
        ("Qwen3.5-27B", "open-weight"),
        ("gemma-4-31B-it", "open-weight"),
        ("Qwen3.5-9B", "open-weight"),
        ("Qwen3.5-4B", "open-weight"),
    ]
    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    for model, family in models:
        x = zero_metrics[model]["suspected_conditions_macro_f1"]
        y = zero_metrics[model]["alerts_macro_f1"]
        size = 90 + 3.0 * (100 - zero_metrics[model]["missed_alert_trajectories"])
        ax.scatter(
            x,
            y,
            s=size,
            color=FAMILY_COLORS[family],
            alpha=0.85,
            edgecolor="white",
            linewidth=0.9,
        )
        label = model.split("/")[-1] if "/" in model else model
        ax.annotate(label, (x, y), xytext=(6, 4), textcoords="offset points", fontsize=8)

    closed_avg_x = np.mean([zero_metrics[m]["suspected_conditions_macro_f1"] for m, fam in models if fam == "closed-source"])
    closed_avg_y = np.mean([zero_metrics[m]["alerts_macro_f1"] for m, fam in models if fam == "closed-source"])
    open_avg_x = np.mean([zero_metrics[m]["suspected_conditions_macro_f1"] for m, fam in models if fam == "open-weight"])
    open_avg_y = np.mean([zero_metrics[m]["alerts_macro_f1"] for m, fam in models if fam == "open-weight"])
    ax.axvline(closed_avg_x, color=FAMILY_COLORS["closed-source"], linestyle="--", alpha=0.45)
    ax.axhline(closed_avg_y, color=FAMILY_COLORS["closed-source"], linestyle="--", alpha=0.45)
    ax.axvline(open_avg_x, color=FAMILY_COLORS["open-weight"], linestyle="--", alpha=0.45)
    ax.axhline(open_avg_y, color=FAMILY_COLORS["open-weight"], linestyle="--", alpha=0.45)

    ax.scatter([], [], s=140, color=FAMILY_COLORS["closed-source"], label="Closed-source")
    ax.scatter([], [], s=140, color=FAMILY_COLORS["open-weight"], label="Open-weight")
    ax.set_xlabel("Suspected Conditions Macro F1")
    ax.set_ylabel("Alerts Macro F1")
    ax.set_title("Zero-shot benchmark_100: Closed-source Models Cluster Higher")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, loc="lower right")
    save(fig, "zeroshot_benchmark100_open_vs_closed")


def main() -> None:
    ensure_dir()

    auto_qwen_2k = {model: summarize_rollouts(load_rollouts(AUTOFORM_DIR, model, "benchmark_2k")) for model in QWEN_MODELS}
    auto_qwen_100 = {model: summarize_rollouts(load_rollouts(AUTOFORM_DIR, model, "benchmark_100")) for model in QWEN_MODELS}
    zero_qwen_100 = {model: summarize_rollouts(load_rollouts(ZEROSHOT_DIR, model, "benchmark_100")) for model in QWEN_MODELS}

    zero_models = [
        "GPT/gpt-5.4",
        "Claude/claude-sonnet-4-6",
        "Gemini/gemini-3.1-pro-preview",
        "Qwen3.5-27B",
        "Qwen3.5-9B",
        "Qwen3.5-4B",
        "gpt-oss-120b",
        "gemma-4-31B-it",
    ]
    zero_metrics = {model: summarize_rollouts(load_rollouts(ZEROSHOT_DIR, model, "benchmark_100")) for model in zero_models}

    plot_qwen_bottleneck(auto_qwen_2k)
    plot_qwen_backend_comparison(auto_qwen_100, zero_qwen_100)
    plot_zeroshot_open_vs_closed(zero_metrics)


if __name__ == "__main__":
    main()
