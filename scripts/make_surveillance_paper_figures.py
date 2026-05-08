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
OPEN_WEIGHT_ZERO_MODELS = ["Qwen3.5-4B", "Qwen3.5-9B", "Qwen3.5-27B", "gemma-4-31B-it", "gpt-oss-120b"]
QWEN_COLORS = {
    "Qwen3.5-27B": "#0d3b66",
    "Qwen3.5-9B": "#2a9d8f",
    "Qwen3.5-4B": "#e76f51",
}
FAMILY_COLORS = {"closed-source": "#264653", "open-weight": "#e76f51"}
ZEROSHOT_SESSION_HELPERS = [
    "search_guidelines(keyword='')",
    "get_guideline(name)",
    "search_functions(keyword='')",
    "get_function_info(name)",
    "load_function(name)",
    "query_db(sql, params=None)",
]


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


def load_evaluation(root: Path, model: str, benchmark: str) -> dict:
    return json.loads((root / model / benchmark / "evaluation.json").read_text())


def normalize_rolling_history_from_rollout(rollout: dict, current_step_index: int) -> dict[str, str]:
    rolling_history: dict[str, str] = {}
    for prev_step in rollout.get("steps", [])[:current_step_index]:
        summary = ((prev_step.get("predicted_surveillance") or {}).get("checkpoint_summary"))
        if summary:
            rolling_history[str(prev_step.get("step_index", len(rolling_history)))] = str(summary)
    return rolling_history


def summarize_zeroshot_history_prefix(step: dict, pairs_used: int) -> list[dict]:
    summarized: list[dict] = []
    tool_calls = step.get("tool_calls") or []
    tool_outputs = step.get("tool_outputs") or []
    for call_payload, output in zip(tool_calls[:pairs_used], tool_outputs[:pairs_used]):
        if call_payload.get("tool_name") == "run_python":
            summarized.append(
                {
                    "type": "python_code",
                    "code": (call_payload.get("arguments") or {}).get("code"),
                }
            )
            summarized.append(
                {
                    "type": "python_output",
                    "ok": output.get("ok"),
                    "stdout": output.get("stdout"),
                    "stderr": output.get("stderr"),
                    "result": output.get("result"),
                    "error_type": output.get("error_type"),
                    "error_message": output.get("error_message"),
                }
            )
    return summarized


def surveillance_zeroshot_system_prompt(remaining_exec_calls: int) -> str:
    prompt = (
        "You are a general ICU rolling surveillance agent operating in a checkpoint-scoped DuckDB Python session.\n"
        "This is a rolling monitoring task, not a forecasting task.\n"
        "At each checkpoint, visible tables already contain only data available by that checkpoint.\n"
        "Your job is to decide the current surveillance state at this checkpoint from memory plus current checkpoint evidence.\n"
        "Use one short Python snippet when you need additional guideline, function, or patient-state evidence.\n"
        "The Python session persists within the current checkpoint only.\n"
        "Do not output reasoning outside the required JSON fields.\n"
        "Return exactly one response and nothing else.\n\n"
        "Monitored surveillance families:\n"
        "- infection and sepsis\n"
        "- renal injury and urine-output failure, including CRRT when relevant\n"
        "- respiratory support escalation and hypoxemia\n"
        "- hemodynamic instability, vasoactive support, and shock\n"
        "- neurologic deterioration\n"
        "- metabolic failure, including lactate elevation and acidemia\n"
        "- coagulation abnormality\n\n"
        "Decision semantics:\n"
        "- suspected_conditions means clinically meaningful concern that should keep monitoring focused on that condition family.\n"
        "- alerts means higher-acuity or higher-confidence states that justify escalation now.\n"
        "- global_action must be exactly one of: continue_monitoring, escalate.\n"
        "- priority must be exactly one of: low, medium, high.\n"
        "- Do not generate the rolling memory summary here; a separate summarizer call will write that summary after your decision.\n\n"
        "General workflow:\n"
        "- Step 1: Use rolling_history first. If memory already establishes a disease family clearly and nothing new must be checked, you may decide directly.\n"
        "- Step 2: If memory is not enough for a disease family, search guideline files for that family to refresh the monitoring criteria.\n"
        "- Step 3: If you still need operational clinical logic, search the autoformalized function library for useful functions for that family.\n"
        "- Step 4: Use the functions or query_db to inspect the current patient state at this checkpoint.\n"
        "- Step 5: After evidence review, return the final surveillance decision.\n\n"
        "Evidence principle:\n"
        "- Do not claim that a disease family is normal, absent, or unchanged unless that conclusion is supported by current checkpoint evidence or explicit rolling_history.\n"
        "- If current-step evidence is empty and rolling_history does not establish the state, retrieve evidence before deciding.\n"
        "- Absence of retrieved evidence is not evidence that the patient is normal.\n"
        "- Do not say that there is 'no data', 'no abnormality', or 'no concern' just because you have not inspected the current checkpoint yet.\n"
        "- If current-step evidence is empty and the state is not already established by rolling_history, your next response should usually be evidence retrieval rather than a final negative decision.\n"
        "- Treat Python execution as an evidence-gathering path, not as free-form analysis.\n\n"
        "Preferred tool-use order inside Python:\n"
        "- First, search guideline files when you need condition definitions or surveillance criteria.\n"
        "- Second, search the autoformalized function library for relevant reusable patient-state functions.\n"
        "- Third, inspect and load the most relevant function files.\n"
        "- Fourth, use the functions or query_db to inspect the patient state for the current checkpoint.\n\n"
        "If you choose execution, these session helpers are available inside Python:\n"
        "- search_guidelines / get_guideline for lightweight filename-based guideline retrieval.\n"
        "- search_functions / get_function_info / load_function for discovering the autoformalized function library.\n"
        "- query_db for checkpoint-scoped SQL queries.\n"
        "- The full function library is not prelisted; discover relevant functions yourself.\n\n"
        "Python execution contract for the fallback execution path:\n"
        "- Use query_db(sql, params=None) for database access.\n"
        "- Use the search_* and load_* helpers directly from the session when needed.\n"
        "- Preloaded variables: stay_id, subject_id, hadm_id, visible_until, pd, np, datetime, timedelta.\n"
        "- Set RESULT before the code ends and/or print concise findings.\n"
        "- Keep snippets short and focused.\n"
        "- Do not open database connections directly.\n\n"
        "Final decision JSON contract:\n"
        "{"
        '"global_action":"continue_monitoring|escalate",'
        '"suspected_conditions":["..."],'
        '"alerts":["..."],'
        '"priority":"low|medium|high",'
        '"rationale":"..."'
        "}\n"
        "- suspected_conditions and alerts must be arrays; use [] when empty.\n"
        "- If no action-level state is active, return continue_monitoring with empty alerts.\n"
    )
    if remaining_exec_calls > 0:
        prompt += (
            f"\nYou have {remaining_exec_calls} Python execution(s) remaining before you must commit to a final surveillance decision."
        )
    else:
        prompt += "\nYou have no Python executions remaining. The next response must be a final surveillance decision."
    return prompt


def surveillance_summary_system_prompt() -> str:
    return (
        "You write the rolling memory summary for a general ICU surveillance benchmark.\n"
        "This is a separate summarizer step after the surveillance decision is already final.\n"
        "Write one very short summary for the next checkpoint.\n"
        "Requirements:\n"
        "- under 20 words when possible\n"
        "- mention only the key active surveillance state or change\n"
        "- do not restate the full rationale\n"
        "- do not include markdown or extra commentary\n"
        '- return exactly one JSON object: {"checkpoint_summary":"..."}\n'
    )


def reconstruct_zero_shot_prompt_mix(rollouts: list[dict], resource_usage: dict) -> dict[str, float]:
    char_buckets = {
        "instruction_scaffold": 0.0,
        "checkpoint_payload": 0.0,
        "tool_code_history": 0.0,
        "tool_output_context": 0.0,
        "summary_writer": 0.0,
    }
    extra_model_calls = 0
    total_model_calls = 0

    for rollout in rollouts:
        steps = rollout.get("steps") or []
        for step_pos, step in enumerate(steps):
            tool_pairs = len(step.get("tool_calls") or [])
            rolling_history = normalize_rolling_history_from_rollout(rollout, step_pos)
            total_model_calls += int((step.get("resource_usage") or {}).get("model_calls", 0) or 0)
            agent_calls = int((step.get("resource_usage") or {}).get("agent_calls", 0) or 0)
            extra_model_calls += max(0, int((step.get("resource_usage") or {}).get("model_calls", 0) or 0) - (agent_calls + 1))

            for used_pairs in range(tool_pairs + 1):
                history = summarize_zeroshot_history_prefix(step, used_pairs)
                code_history = [item for item in history if item.get("type") == "python_code"]
                output_history = [item for item in history if item.get("type") == "python_output"]
                base_payload = {
                    "step_input": {
                        "trajectory_id": rollout["trajectory_id"],
                        "stay_id": rollout["stay_id"],
                        "step_index": step["step_index"],
                        "t_hour": step["t_hour"],
                        "task_name": "general_icu_surveillance",
                    },
                    "tool_backend": "zeroshot_python",
                    "session_helpers": ZEROSHOT_SESSION_HELPERS,
                    "remaining_python_executions": max(0, 6 - used_pairs),
                    "rolling_history": rolling_history,
                    "history": [],
                }
                payload_empty = json.dumps(base_payload, indent=2)
                payload_with_code = json.dumps({**base_payload, "history": code_history}, indent=2)
                payload_full = json.dumps({**base_payload, "history": history}, indent=2)

                char_buckets["instruction_scaffold"] += len(surveillance_zeroshot_system_prompt(max(0, 6 - used_pairs)))
                char_buckets["checkpoint_payload"] += len(payload_empty)
                char_buckets["tool_code_history"] += max(0, len(payload_with_code) - len(payload_empty))
                char_buckets["tool_output_context"] += max(0, len(payload_full) - len(payload_with_code))

            decision = dict(step.get("predicted_surveillance") or {})
            decision.pop("checkpoint_summary", None)
            summary_payload = {
                "step_input": {
                    "trajectory_id": rollout["trajectory_id"],
                    "stay_id": rollout["stay_id"],
                    "step_index": step["step_index"],
                    "t_hour": step["t_hour"],
                    "task_name": "general_icu_surveillance",
                },
                "final_decision": decision,
                "current_checkpoint_tool_history": summarize_zeroshot_history_prefix(step, tool_pairs)[-4:],
            }
            char_buckets["summary_writer"] += len(surveillance_summary_system_prompt())
            char_buckets["summary_writer"] += len(json.dumps(summary_payload, indent=2))

    totals = resource_usage["totals"]
    prompt_tokens = float(totals["prompt_tokens"])
    completion_tokens = float(totals["completion_tokens"])
    repair_prompt_tokens = (
        prompt_tokens * extra_model_calls / total_model_calls if total_model_calls else 0.0
    )
    alloc_prompt_tokens = max(0.0, prompt_tokens - repair_prompt_tokens)
    char_total = sum(char_buckets.values())
    token_buckets = {
        key: (alloc_prompt_tokens * value / char_total if char_total else 0.0)
        for key, value in char_buckets.items()
    }
    token_buckets["repair_retry_overhead"] = repair_prompt_tokens
    token_buckets["completion_tokens"] = completion_tokens
    n_trajectories = max(1, int(totals["num_trajectories"]))
    token_buckets = {key: value / n_trajectories for key, value in token_buckets.items()}
    return token_buckets


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


def plot_zeroshot_cost_breakdown(zero_resource_usage: dict[str, dict]) -> None:
    labels = ["Qwen3.5 4B", "Qwen3.5 9B", "Qwen3.5 27B", "Gemma-4 31B", "GPT-OSS 120B"]
    rollouts_by_model = {model: load_rollouts(ZEROSHOT_DIR, model, "benchmark_100") for model in OPEN_WEIGHT_ZERO_MODELS}
    mixes = {model: reconstruct_zero_shot_prompt_mix(rollouts_by_model[model], zero_resource_usage[model]) for model in OPEN_WEIGHT_ZERO_MODELS}

    components = [
        ("instruction_scaffold", "Instruction scaffold", "#ff5a5f"),
        ("checkpoint_payload", "Checkpoint payload + memory", "#f4a261"),
        ("tool_code_history", "Python code history", "#e9c46a"),
        ("tool_output_context", "Tool output context", "#2a9d8f"),
        ("summary_writer", "Summary writer", "#8d99ae"),
        ("repair_retry_overhead", "Repair / retry overhead", "#6d597a"),
        ("completion_tokens", "Completion tokens", "#5b8bd9"),
    ]

    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(13.2, 6.2))
    bottoms = np.zeros(len(labels))

    for key, label, color in components:
        vals = np.array([mixes[model][key] / 1000 for model in OPEN_WEIGHT_ZERO_MODELS])
        ax.bar(x, vals, bottom=bottoms, color=color, label=label)
        bottoms += vals

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=16, ha="right")
    ax.set_ylabel("Avg. Tokens / Trajectory (K)")
    ax.set_title("Reconstructed Zero-shot Token Budget per Trajectory")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, ncol=2, fontsize=9, loc="upper left")

    for idx, model in enumerate(OPEN_WEIGHT_ZERO_MODELS):
        total_k = sum(mixes[model].values()) / 1000
        tool_share = 100 * mixes[model]["tool_output_context"] / max(
            1.0,
            mixes[model]["instruction_scaffold"]
            + mixes[model]["checkpoint_payload"]
            + mixes[model]["tool_code_history"]
            + mixes[model]["tool_output_context"]
            + mixes[model]["summary_writer"]
            + mixes[model]["repair_retry_overhead"],
        )
        ax.text(idx, total_k + 10, f"{total_k:.0f}K", ha="center", va="bottom", fontsize=10)
        ax.text(
            idx,
            (mixes[model]["instruction_scaffold"] + mixes[model]["checkpoint_payload"] + mixes[model]["tool_code_history"] + mixes[model]["tool_output_context"] / 2) / 1000,
            f"{tool_share:.0f}%",
            ha="center",
            va="center",
            fontsize=9,
            color="white",
            fontweight="bold",
        )

    fig.suptitle("Zero-shot benchmark_100 Open-Weight Cost Decomposition", y=1.02, fontsize=14)
    save(fig, "zeroshot_benchmark100_open_weight_cost_breakdown")


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
    zero_resource_usage = {
        model: load_evaluation(ZEROSHOT_DIR, model, "benchmark_100")["metrics"]["resource_usage"]
        for model in OPEN_WEIGHT_ZERO_MODELS
    }

    plot_qwen_bottleneck(auto_qwen_2k)
    plot_qwen_backend_comparison(auto_qwen_100, zero_qwen_100)
    plot_zeroshot_open_vs_closed(zero_metrics)
    plot_zeroshot_cost_breakdown(zero_resource_usage)


if __name__ == "__main__":
    main()
