from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


BASE = Path("/Users/chloe/Documents/New project")
RESULT_DIR = BASE / "result" / "rolling_eval_autoform"
OUT_DIR = BASE / "docs" / "surveilance" / "figures"

MODELS = ["Qwen3.5-27B", "Qwen3.5-9B", "Qwen3.5-4B"]
MODEL_COLORS = {
    "Qwen3.5-27B": "#0d3b66",
    "Qwen3.5-9B": "#2a9d8f",
    "Qwen3.5-4B": "#e76f51",
}

SEMANTICS = {
    "Persistent\nEpisode": {
        "infection_suspected",
        "infection_confirmed_or_strongly_supported",
        "sepsis_alert",
    },
    "Cumulative\nMax Stage": {
        "aki_stage1",
        "aki_stage2",
        "aki_stage3",
    },
    "Active\nInterval": {
        "resp_support_hfnc_or_niv",
        "resp_support_invasive_vent",
        "vasoactive_support_any",
        "vasoactive_multi_agent_or_high_intensity",
        "crrt_active",
    },
    "Recent\nMeasurement + TTL": {
        "oliguria_6h",
        "severe_oliguria_or_anuria",
        "hypoxemia_pf_lt_200",
        "hypoxemia_pf_lt_100",
        "gcs_moderate_impairment_9_12",
        "gcs_severe_impairment_le_8",
        "hyperlactatemia_ge_2",
        "severe_hyperlactatemia_ge_4",
        "acidemia_ph_lt_7_30",
        "severe_acidemia_ph_le_7_20",
        "coagulopathy_inr_ge_1_5",
        "coagulopathy_inr_ge_2",
    },
    "Composite\nCurrent State": {
        "septic_shock_alert",
        "shock_hypoperfusion_alert",
    },
}


def metric_set(gt: list[str], pred: list[str]) -> tuple[float, float, float]:
    gt_set, pred_set = set(gt or []), set(pred or [])
    tp = len(gt_set & pred_set)
    fp = len(pred_set - gt_set)
    fn = len(gt_set - pred_set)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not pred_set and not gt_set else 0.0)
    recall = tp / (tp + fn) if tp + fn else (1.0 if not pred_set and not gt_set else 0.0)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def load_rollouts(model: str) -> list[dict]:
    path = RESULT_DIR / model / "benchmark_2k" / "rollouts.json"
    return json.load(path.open())


def compute_model_metrics(rollouts: list[dict]) -> dict[str, float]:
    total_steps = 0
    ga = pr = sem = aem = 0
    sf1 = ap = ar = af1 = 0.0
    first_pairs: list[tuple[int | None, int | None]] = []
    strict = 0
    gt_alert_trajectories = 0
    for rollout in rollouts:
        gt_first = pred_first = None
        perfect = True
        for step in rollout["steps"]:
            total_steps += 1
            gt = step.get("gt_surveillance") or {}
            pred = step.get("predicted_surveillance") or {}
            gt_action = gt.get("global_action")
            pred_action = pred.get("global_action")
            gt_priority = gt.get("priority")
            pred_priority = pred.get("priority")
            gt_sus = gt.get("suspected_conditions") or []
            pred_sus = pred.get("suspected_conditions") or []
            gt_alerts = gt.get("alerts") or []
            pred_alerts = pred.get("alerts") or []
            ga += int(gt_action == pred_action)
            pr += int(gt_priority == pred_priority)
            sem += int(set(gt_sus) == set(pred_sus))
            aem += int(set(gt_alerts) == set(pred_alerts))
            _, _, f1 = metric_set(gt_sus, pred_sus)
            sf1 += f1
            p, r, f1 = metric_set(gt_alerts, pred_alerts)
            ap += p
            ar += r
            af1 += f1
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
        if gt_first is not None:
            gt_alert_trajectories += 1
        first_pairs.append((gt_first, pred_first))
        strict += int(perfect)
    errs = [pred - gt for gt, pred in first_pairs if gt is not None and pred is not None]
    false_early = sum(1 for gt, pred in first_pairs if gt is not None and pred is not None and pred < gt)
    missed = sum(1 for gt, pred in first_pairs if gt is not None and pred is None)
    return {
        "global_action_accuracy": ga / total_steps,
        "priority_accuracy": pr / total_steps,
        "suspected_conditions_macro_f1": sf1 / total_steps,
        "alerts_macro_f1": af1 / total_steps,
        "alerts_macro_precision": ap / total_steps,
        "alerts_macro_recall": ar / total_steps,
        "suspected_conditions_exact_match": sem / total_steps,
        "alerts_exact_match": aem / total_steps,
        "first_alert_mean_abs_error_hours": sum(abs(x) for x in errs) / len(errs),
        "false_early_alert_trajectories": false_early,
        "missed_alert_trajectories": missed,
        "missed_alert_rate": missed / gt_alert_trajectories,
        "false_early_rate": false_early / gt_alert_trajectories,
        "strict_all4_trajectory_rate": strict / len(rollouts),
    }


def compute_semantic_metrics(rollouts: list[dict]) -> dict[str, dict[str, float]]:
    results: dict[str, dict[str, float]] = {}
    for semantic_name, labels in SEMANTICS.items():
        total = gt_pos = gt_neg = exact_pos = any_pred_pos = any_pred_neg = 0
        tp = fp = fn = 0
        for rollout in rollouts:
            for step in rollout["steps"]:
                gt = set((step.get("gt_surveillance") or {}).get("suspected_conditions") or []) | set(
                    (step.get("gt_surveillance") or {}).get("alerts") or []
                )
                pred = set((step.get("predicted_surveillance") or {}).get("suspected_conditions") or []) | set(
                    (step.get("predicted_surveillance") or {}).get("alerts") or []
                )
                g = gt & labels
                p = pred & labels
                total += 1
                tp += len(g & p)
                fp += len(p - g)
                fn += len(g - p)
                if g:
                    gt_pos += 1
                    exact_pos += int(g == p)
                    any_pred_pos += int(bool(p))
                else:
                    gt_neg += 1
                    any_pred_neg += int(bool(p))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        results[semantic_name] = {
            "gt_positive_step_rate": gt_pos / total,
            "any_prediction_rate_when_positive": any_pred_pos / gt_pos if gt_pos else 0.0,
            "any_prediction_rate_when_negative": any_pred_neg / gt_neg if gt_neg else 0.0,
            "exact_match_on_positive_steps": exact_pos / gt_pos if gt_pos else 0.0,
            "micro_precision": precision,
            "micro_recall": recall,
            "micro_f1": f1,
        }
    return results


def ensure_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT_DIR / f"{name}.png", dpi=220, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def plot_core_vs_auxiliary(metrics_by_model: dict[str, dict[str, float]]) -> None:
    core_metrics = [
        "suspected_conditions_macro_f1",
        "alerts_macro_f1",
        "alerts_macro_precision",
        "alerts_macro_recall",
        "suspected_conditions_exact_match",
        "alerts_exact_match",
    ]
    aux_metrics = ["global_action_accuracy", "priority_accuracy"]
    core_labels = [
        "Suspect F1",
        "Alert F1",
        "Alert Prec.",
        "Alert Recall",
        "Suspect Exact",
        "Alert Exact",
    ]
    aux_labels = ["Global Action", "Priority"]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [2.3, 1]})
    x = np.arange(len(core_metrics))
    width = 0.23
    for idx, model in enumerate(MODELS):
        vals = [metrics_by_model[model][m] for m in core_metrics]
        axes[0].bar(x + (idx - 1) * width, vals, width=width, color=MODEL_COLORS[model], label=model)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(core_labels, rotation=25, ha="right")
    axes[0].set_ylim(0, 0.32)
    axes[0].set_title("Core Benchmark Metrics")
    axes[0].set_ylabel("Score")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False, ncol=3, loc="upper center")

    x2 = np.arange(len(aux_metrics))
    for idx, model in enumerate(MODELS):
        vals = [metrics_by_model[model][m] for m in aux_metrics]
        axes[1].bar(x2 + (idx - 1) * width, vals, width=width, color=MODEL_COLORS[model])
    axes[1].set_xticks(x2)
    axes[1].set_xticklabels(aux_labels, rotation=15)
    axes[1].set_ylim(0, 0.5)
    axes[1].set_title("Auxiliary Coarse Summaries")
    axes[1].grid(axis="y", alpha=0.25)

    fig.suptitle("Finished Qwen Models on benchmark_2k", y=1.02, fontsize=14)
    save(fig, "qwen_benchmark2k_core_vs_auxiliary")


def plot_temporal_quality(metrics_by_model: dict[str, dict[str, float]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    x = np.arange(len(MODELS))

    miss_vals = [metrics_by_model[m]["missed_alert_rate"] for m in MODELS]
    early_vals = [metrics_by_model[m]["false_early_rate"] for m in MODELS]
    exact_vals = [metrics_by_model[m]["strict_all4_trajectory_rate"] for m in MODELS]
    width = 0.22
    axes[0].bar(x - width, miss_vals, width=width, color="#c1121f", label="Missed alert rate")
    axes[0].bar(x, early_vals, width=width, color="#f4a261", label="False-early rate")
    axes[0].bar(x + width, exact_vals, width=width, color="#6a994e", label="Exact trajectory rate")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(MODELS, rotation=15)
    axes[0].set_ylim(0, 0.6)
    axes[0].set_title("Trajectory-Level Temporal Quality")
    axes[0].set_ylabel("Rate")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False, fontsize=9)

    mae_vals = [metrics_by_model[m]["first_alert_mean_abs_error_hours"] for m in MODELS]
    axes[1].bar(x, mae_vals, color=[MODEL_COLORS[m] for m in MODELS], width=0.55)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(MODELS, rotation=15)
    axes[1].set_ylim(0, max(mae_vals) * 1.2)
    axes[1].set_title("First-Alert Timing Error")
    axes[1].set_ylabel("Mean Absolute Error (hours)")
    axes[1].grid(axis="y", alpha=0.25)

    fig.suptitle("Finished Qwen Models: Patient-Level and Temporal Findings", y=1.02, fontsize=14)
    save(fig, "qwen_benchmark2k_temporal_quality")


def plot_semantic_heatmap(semantic_by_model: dict[str, dict[str, dict[str, float]]]) -> None:
    semantic_names = list(SEMANTICS.keys())
    metric_names = ["micro_f1", "any_prediction_rate_when_positive"]
    metric_titles = ["Semantic-Type Micro F1", "Prediction Rate on Positive Steps"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, metric_name, title in zip(axes, metric_names, metric_titles):
        data = np.array(
            [[semantic_by_model[model][semantic][metric_name] for semantic in semantic_names] for model in MODELS]
        )
        im = ax.imshow(data, cmap="YlGnBu", vmin=0, vmax=max(0.35, float(data.max())))
        ax.set_xticks(np.arange(len(semantic_names)))
        ax.set_xticklabels(semantic_names, rotation=20, ha="right")
        ax.set_yticks(np.arange(len(MODELS)))
        ax.set_yticklabels(MODELS)
        ax.set_title(title)
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                ax.text(j, i, f"{data[i, j]:.3f}", ha="center", va="center", fontsize=8, color="black")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.suptitle("Finished Qwen Models by Temporal Semantic Type", y=1.04, fontsize=14)
    save(fig, "qwen_benchmark2k_semantic_heatmap")


def main() -> None:
    ensure_dir()
    metrics_by_model: dict[str, dict[str, float]] = {}
    semantic_by_model: dict[str, dict[str, dict[str, float]]] = {}
    for model in MODELS:
        rollouts = load_rollouts(model)
        metrics_by_model[model] = compute_model_metrics(rollouts)
        semantic_by_model[model] = compute_semantic_metrics(rollouts)
    plot_core_vs_auxiliary(metrics_by_model)
    plot_temporal_quality(metrics_by_model)
    plot_semantic_heatmap(semantic_by_model)


if __name__ == "__main__":
    main()
