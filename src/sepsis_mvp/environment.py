from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Any

from .agent import Agent
from .schemas import (
    ActionDecision,
    AgentStepInput,
    CODE_EXEC_TOOL_NAME,
    SEPSIS_TOOLBOX_TOOL_NAMES,
    SQL_EXEC_TOOL_NAME,
    TASK_BASELINE_ACTION,
    TASK_LABEL_SPACES,
    TASK_TOOL_NAMES,
    TASK_TRANSITION_FIELDS,
    Trajectory,
    TrajectoryRollout,
    StepRecord,
    ToolCall,
)
from .tools import ToolRuntime


class BenchmarkEnvironment:
    SUPPORTED_PROTOCOLS = {"rolling_no_history", "rolling_with_history", "rolling_toolbox_with_history"}

    def __init__(
        self,
        trajectories: list[Trajectory],
        tool_runtime: ToolRuntime,
        *,
        max_tool_calls_per_step: int = 4,
        event_callback: Any | None = None,
        tool_backend: str = "official",
        task_mode: str = "auto",
        protocol: str = "rolling_no_history",
    ) -> None:
        self.trajectories = trajectories
        self.tool_runtime = tool_runtime
        self.max_tool_calls_per_step = max_tool_calls_per_step
        self.event_callback = event_callback
        self.tool_backend = tool_backend
        self.task_mode = task_mode
        if protocol not in self.SUPPORTED_PROTOCOLS:
            raise ValueError(
                f"Unsupported protocol '{protocol}'. Supported protocols: {sorted(self.SUPPORTED_PROTOCOLS)}"
            )
        self.protocol = protocol

    def _emit(self, event: dict[str, Any]) -> None:
        if self.event_callback is not None:
            self.event_callback(event)

    def run_trajectory(self, trajectory: Trajectory, agent: Agent) -> TrajectoryRollout:
        steps: list[StepRecord] = []
        first_predicted_infection_hour = None
        first_predicted_alert_hour = None
        first_predicted_task_hours: dict[str, dict[str, int | None]] = defaultdict(dict)
        task_names = trajectory.resolved_task_names()
        task_mode = self._resolve_task_mode(trajectory)

        self._emit(
            {
                "event_type": "trajectory_start",
                "trajectory_id": trajectory.trajectory_id,
                "stay_id": trajectory.stay_id,
                "task_names": task_names,
                "task_mode": task_mode,
                "tool_backend": self.tool_backend,
            }
        )

        available_tools = self._available_tools_for_protocol(trajectory)
        rolling_history: list[dict[str, Any]] = []

        for step_index, checkpoint in enumerate(trajectory.checkpoints):
            instruction = self._instruction_for_trajectory(trajectory)
            step_rolling_history = (
                list(rolling_history)
                if self.protocol in {"rolling_with_history", "rolling_toolbox_with_history"}
                else []
            )
            step_max_interactions = self._max_step_interactions_for_protocol(available_tools)
            step_input = AgentStepInput(
                trajectory_id=trajectory.trajectory_id,
                stay_id=trajectory.stay_id,
                step_index=step_index,
                t_hour=checkpoint.t_hour,
                available_tools=available_tools,
                instruction=instruction,
                task_names=task_names,
                task_variant=trajectory.task_variant,
                label_spaces=trajectory.label_spaces,
                task_mode=task_mode,
                tool_backend=self.tool_backend,
                max_step_interactions=step_max_interactions,
                protocol=self.protocol,
                rolling_history=step_rolling_history,
            )
            history: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
            tool_outputs: list[dict[str, Any]] = []
            primary_task = trajectory.primary_task_name()
            predicted_action: str | None = TASK_BASELINE_ACTION.get(primary_task)
            predicted_task_actions: dict[str, str] | None = None
            step_session_id = None
            if hasattr(self.tool_runtime, "start_step_session"):
                step_session_id = self.tool_runtime.start_step_session(
                    stay_id=trajectory.stay_id,
                    t_hour=checkpoint.t_hour,
                )

            self._emit(
                {
                    "event_type": "step_start",
                    "trajectory_id": trajectory.trajectory_id,
                    "stay_id": trajectory.stay_id,
                    "step_index": step_index,
                    "t_hour": checkpoint.t_hour,
                    "gt_action": checkpoint.state_label,
                    "gt_task_actions": checkpoint.task_labels,
                    "protocol": self.protocol,
                    "rolling_history_length": len(step_rolling_history),
                    "available_tools": available_tools,
                }
            )

            try:
                for _ in range(step_max_interactions + 1):
                    response = agent.next_response(
                        step_input=step_input.to_dict(),
                        history=history,
                        available_tools=step_input.available_tools,
                    )
                    if isinstance(response, ToolCall):
                        arguments = dict(response.arguments)
                        if response.tool_name in {CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME} and step_session_id is not None:
                            arguments["session_id"] = step_session_id
                        output = self.tool_runtime.execute(response.tool_name, arguments)
                        call_payload = {"tool_name": response.tool_name, "arguments": arguments}
                        self._emit(
                            {
                                "event_type": "tool_call",
                                "trajectory_id": trajectory.trajectory_id,
                                "stay_id": trajectory.stay_id,
                                "step_index": step_index,
                                "t_hour": checkpoint.t_hour,
                                "tool_name": response.tool_name,
                                "arguments": arguments,
                            }
                        )
                        history.append({"type": "tool_call", "tool_name": response.tool_name, "payload": call_payload})
                        history.append({"type": "tool_output", "tool_name": response.tool_name, "payload": output})
                        tool_calls.append(call_payload)
                        tool_outputs.append(output)
                        self._emit(
                            {
                                "event_type": "tool_output",
                                "trajectory_id": trajectory.trajectory_id,
                                "stay_id": trajectory.stay_id,
                                "step_index": step_index,
                                "t_hour": checkpoint.t_hour,
                                "tool_name": response.tool_name,
                                "output": output,
                            }
                        )
                        continue
                    if isinstance(response, ActionDecision):
                        predicted_action = response.action
                        predicted_task_actions = response.task_actions
                        self._emit(
                            {
                                "event_type": "action",
                                "trajectory_id": trajectory.trajectory_id,
                                "stay_id": trajectory.stay_id,
                                "step_index": step_index,
                                "t_hour": checkpoint.t_hour,
                                "gt_action": checkpoint.state_label,
                                "gt_task_actions": checkpoint.task_labels,
                                "predicted_action": predicted_action,
                                "predicted_task_actions": predicted_task_actions,
                            }
                        )
                        break
                    raise TypeError(f"Unsupported agent response: {response}")
            finally:
                if hasattr(self.tool_runtime, "close_step_session"):
                    self.tool_runtime.close_step_session(step_session_id)

            if not trajectory.is_multitask():
                if (
                    predicted_action is not None
                    and predicted_action != TASK_BASELINE_ACTION.get(primary_task)
                ):
                    first_predicted_task_hours[primary_task].setdefault(predicted_action, checkpoint.t_hour)
                if primary_task in {"sepsis", "infection_only"}:
                    if predicted_action == "infection_suspect" and first_predicted_infection_hour is None:
                        first_predicted_infection_hour = checkpoint.t_hour
                    if primary_task == "sepsis" and predicted_action == "trigger_sepsis_alert":
                        if first_predicted_infection_hour is None:
                            first_predicted_infection_hour = checkpoint.t_hour
                        if first_predicted_alert_hour is None:
                            first_predicted_alert_hour = checkpoint.t_hour
            else:
                for task_name, action in (predicted_task_actions or {}).items():
                    if action != TASK_BASELINE_ACTION.get(task_name):
                        first_predicted_task_hours[task_name].setdefault(action, checkpoint.t_hour)

            steps.append(
                StepRecord(
                    step_index=step_index,
                    t_hour=checkpoint.t_hour,
                    gt_action=checkpoint.state_label,
                    predicted_action=predicted_action,
                    gt_task_actions=checkpoint.task_labels,
                    predicted_task_actions=predicted_task_actions,
                    tool_calls=tool_calls,
                    tool_outputs=tool_outputs,
                )
            )
            history_entry = _build_rolling_history_entry(
                trajectory=trajectory,
                checkpoint=checkpoint,
                step_index=step_index,
                tool_outputs=tool_outputs,
            )
            if history_entry is not None and self.protocol in {"rolling_with_history", "rolling_toolbox_with_history"}:
                rolling_history.append(history_entry)

        rollout = TrajectoryRollout(
            trajectory_id=trajectory.trajectory_id,
            stay_id=trajectory.stay_id,
            steps=steps,
            first_predicted_infection_hour=first_predicted_infection_hour,
            first_predicted_alert_hour=first_predicted_alert_hour,
            first_predicted_task_hours=dict(first_predicted_task_hours) if first_predicted_task_hours else None,
        )
        self._emit(
            {
                "event_type": "trajectory_complete",
                "trajectory_id": trajectory.trajectory_id,
                "stay_id": trajectory.stay_id,
                "task_mode": task_mode,
                "tool_backend": self.tool_backend,
                "protocol": self.protocol,
                "first_predicted_infection_hour": first_predicted_infection_hour,
                "first_predicted_alert_hour": first_predicted_alert_hour,
                "first_predicted_task_hours": rollout.first_predicted_task_hours or None,
                "num_steps": len(steps),
            }
        )
        return rollout

    def run_all(self, agent: Agent) -> list[TrajectoryRollout]:
        return [self.run_trajectory(trajectory, agent) for trajectory in self.trajectories]

    def _resolve_task_mode(self, trajectory: Trajectory) -> str:
        inferred = "multitask" if trajectory.is_multitask() else "single"
        if self.task_mode == "auto":
            return inferred
        if self.task_mode != inferred:
            raise ValueError(
                f"Dataset/task-mode mismatch: trajectory {trajectory.trajectory_id} is {inferred}, "
                f"but runner requested {self.task_mode}."
        )
        return self.task_mode

    def _available_tools_for_protocol(self, trajectory: Trajectory) -> list[str]:
        if self.protocol == "rolling_toolbox_with_history":
            if trajectory.is_multitask() or trajectory.primary_task_name() != "sepsis":
                raise ValueError(
                    "Protocol 'rolling_toolbox_with_history' currently supports only the single-task sepsis dataset."
                )
            return list(SEPSIS_TOOLBOX_TOOL_NAMES)
        return trajectory.resolved_tool_names()

    def _max_step_interactions_for_protocol(self, available_tools: list[str]) -> int:
        if self.protocol == "rolling_toolbox_with_history":
            return max(self.max_tool_calls_per_step, len(available_tools) + 2)
        return self.max_tool_calls_per_step

    def _instruction_for_trajectory(self, trajectory: Trajectory) -> str:
        if trajectory.is_multitask():
            return "Use tools if needed. Then output one decision for each monitored task."
        task_name = trajectory.primary_task_name()
        label_space = (trajectory.label_spaces or {}).get(task_name, TASK_LABEL_SPACES[task_name])
        return (
            f"Use tools if needed. Then output exactly one action for task '{task_name}': "
            + ", ".join(label_space)
            + "."
        )


def _f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def evaluate_rollouts(trajectories: list[Trajectory], rollouts: list[TrajectoryRollout]) -> dict[str, Any]:
    if trajectories and trajectories[0].is_multitask():
        return evaluate_multitask_rollouts(trajectories, rollouts)
    return evaluate_single_task_rollouts(trajectories, rollouts)


def evaluate_single_task_rollouts(trajectories: list[Trajectory], rollouts: list[TrajectoryRollout]) -> dict[str, Any]:
    trajectory_by_id = {trajectory.trajectory_id: trajectory for trajectory in trajectories}
    if not trajectories:
        return {}
    task_name = trajectories[0].primary_task_name()
    label_space = trajectories[0].label_spaces.get(task_name, TASK_LABEL_SPACES[task_name]) if trajectories[0].label_spaces else TASK_LABEL_SPACES[task_name]
    if _is_non_monotonic_aki_task(trajectories[0], label_space):
        return evaluate_single_task_current_state_rollouts(trajectories, rollouts)
    total_steps = 0
    correct_steps = 0
    confusion = Counter()
    per_class = {}
    transition_fields = TASK_TRANSITION_FIELDS.get(task_name, {})
    gt_hours_by_action = {action: [] for action in transition_fields}
    pred_hours_by_action = {action: [] for action in transition_fields}
    grounding_counts = _single_task_grounding_counters(task_name, label_space)

    for rollout in rollouts:
        trajectory = trajectory_by_id[rollout.trajectory_id]
        for step in rollout.steps:
            total_steps += 1
            if step.gt_action == step.predicted_action:
                correct_steps += 1
            confusion[(step.gt_action, step.predicted_action)] += 1
            _update_single_task_grounding(
                task_name,
                step.predicted_action,
                step.tool_calls,
                grounding_counts,
                label_space,
            )

        predicted_hours = (rollout.first_predicted_task_hours or {}).get(task_name, {})
        for action, transition_field in transition_fields.items():
            gt_hours_by_action[action].append(trajectory.transitions.get(transition_field))
            pred_hours_by_action[action].append(predicted_hours.get(action))

    for action in label_space:
        tp = confusion[(action, action)]
        fp = sum(confusion[(gt, action)] for gt in label_space if gt != action)
        fn = sum(confusion[(action, pred)] for pred in label_space if pred != action)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_class[action] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_f1(tp, fp, fn), 4),
        }

    macro_f1 = round(sum(metrics["f1"] for metrics in per_class.values()) / len(label_space), 4)
    transition_timing = {
        action: _timing_metrics(gt_hours_by_action[action], pred_hours_by_action[action])
        for action in transition_fields
    }
    transition_timing = _format_single_task_transition_timing(task_name, transition_timing)

    return {
        "task_name": task_name,
        "step_level": {
            "accuracy": round(correct_steps / total_steps, 4) if total_steps else 0.0,
            "macro_f1": macro_f1,
            "per_class": per_class,
        },
        "transition_timing": transition_timing,
        "tool_grounding": _finalize_single_task_grounding(grounding_counts),
    }


def evaluate_single_task_current_state_rollouts(
    trajectories: list[Trajectory],
    rollouts: list[TrajectoryRollout],
) -> dict[str, Any]:
    trajectory_by_id = {trajectory.trajectory_id: trajectory for trajectory in trajectories}
    task_name = trajectories[0].primary_task_name()
    label_space = trajectories[0].label_spaces.get(task_name, TASK_LABEL_SPACES[task_name]) if trajectories[0].label_spaces else TASK_LABEL_SPACES[task_name]
    total_steps = 0
    correct_steps = 0
    confusion = Counter()
    per_class = {}
    change_counts = {
        "worsening": {"tp": 0, "fp": 0, "fn": 0},
        "recovery": {"tp": 0, "fp": 0, "fn": 0},
    }
    exact_path_matches = 0
    grounding_counts = _single_task_grounding_counters(task_name, label_space)

    for rollout in rollouts:
        trajectory = trajectory_by_id[rollout.trajectory_id]
        gt_path: list[str] = []
        pred_path: list[str] = []
        for step in rollout.steps:
            total_steps += 1
            if step.gt_action == step.predicted_action:
                correct_steps += 1
            confusion[(step.gt_action, step.predicted_action)] += 1
            _update_single_task_grounding(task_name, step.predicted_action, step.tool_calls, grounding_counts, label_space)
            if step.gt_action is not None:
                gt_path.append(step.gt_action)
            if step.predicted_action is not None:
                pred_path.append(step.predicted_action)

        if gt_path == pred_path:
            exact_path_matches += 1

        for idx in range(1, min(len(gt_path), len(pred_path))):
            gt_delta = _state_order(label_space, gt_path[idx]) - _state_order(label_space, gt_path[idx - 1])
            pred_delta = _state_order(label_space, pred_path[idx]) - _state_order(label_space, pred_path[idx - 1])
            _update_change_counts(change_counts["worsening"], gt_delta > 0, pred_delta > 0)
            _update_change_counts(change_counts["recovery"], gt_delta < 0, pred_delta < 0)

    for action in label_space:
        tp = confusion[(action, action)]
        fp = sum(confusion[(gt, action)] for gt in label_space if gt != action)
        fn = sum(confusion[(action, pred)] for pred in label_space if pred != action)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_class[action] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_f1(tp, fp, fn), 4),
        }

    return {
        "task_name": task_name,
        "task_variant": trajectories[0].task_variant,
        "step_level": {
            "accuracy": round(correct_steps / total_steps, 4) if total_steps else 0.0,
            "macro_f1": round(sum(metrics["f1"] for metrics in per_class.values()) / len(label_space), 4),
            "per_class": per_class,
        },
        "state_change": {
            "worsening": _event_metrics(change_counts["worsening"]),
            "recovery": _event_metrics(change_counts["recovery"]),
            "exact_path_match_rate": round(exact_path_matches / len(rollouts), 4) if rollouts else 0.0,
        },
        "tool_grounding": _finalize_single_task_grounding(grounding_counts),
    }


def evaluate_multitask_rollouts(trajectories: list[Trajectory], rollouts: list[TrajectoryRollout]) -> dict[str, Any]:
    total_steps = 0
    joint_correct = 0
    per_task_counts = defaultdict(int)
    per_task_correct = defaultdict(int)
    per_task_confusion = defaultdict(Counter)
    grounding = {
        "sepsis": {"num": 0, "den": 0},
        "aki": {"num": 0, "den": 0},
        "respiratory_support": {"num": 0, "den": 0},
    }

    for rollout in rollouts:
        for step in rollout.steps:
            total_steps += 1
            gt = step.gt_task_actions or {}
            pred = step.predicted_task_actions or {}
            if gt == pred:
                joint_correct += 1
            for task_name, gt_action in gt.items():
                pred_action = pred.get(task_name)
                per_task_counts[task_name] += 1
                if gt_action == pred_action:
                    per_task_correct[task_name] += 1
                per_task_confusion[task_name][(gt_action, pred_action)] += 1
                if pred_action is not None and pred_action != TASK_BASELINE_ACTION[task_name]:
                    grounding[task_name]["den"] += 1
                    if _is_grounded(task_name, step.tool_calls):
                        grounding[task_name]["num"] += 1

    per_task_metrics = {}
    for task_name, counts in per_task_counts.items():
        label_space = TASK_LABEL_SPACES[task_name]
        class_metrics = {}
        for action in label_space:
            tp = per_task_confusion[task_name][(action, action)]
            fp = sum(per_task_confusion[task_name][(gt, action)] for gt in label_space if gt != action)
            fn = sum(per_task_confusion[task_name][(action, pred)] for pred in label_space if pred != action)
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            class_metrics[action] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(_f1(tp, fp, fn), 4),
            }
        per_task_metrics[task_name] = {
            "accuracy": round(per_task_correct[task_name] / counts, 4) if counts else 0.0,
            "macro_f1": round(sum(metric["f1"] for metric in class_metrics.values()) / len(label_space), 4),
            "per_class": class_metrics,
            "grounded_rate": round(grounding[task_name]["num"] / grounding[task_name]["den"], 4)
            if grounding[task_name]["den"]
            else None,
        }

    return {
        "joint_step_accuracy": round(joint_correct / total_steps, 4) if total_steps else 0.0,
        "per_task": per_task_metrics,
    }

def _is_grounded(task_name: str, tool_calls: list[dict[str, Any]]) -> bool:
    tools = {call["tool_name"] for call in tool_calls}
    if task_name == "sepsis":
        return bool(tools & {"query_suspicion_of_infection", "query_sofa", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME})
    if task_name == "infection_only":
        return bool(tools & {"query_suspicion_of_infection", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME})
    if task_name == "aki":
        return bool(tools & {"query_kdigo_stage", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME})
    if task_name == "respiratory_support":
        return bool(tools & {"query_ventilation_status", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME})
    return False


def _single_task_grounding_spec(
    task_name: str,
    label_space: list[str] | None = None,
) -> dict[str, tuple[str, set[str]]]:
    if task_name == "sepsis":
        return {
            "infection_suspect": (
                "infection_predictions_grounded_rate",
                {"query_suspicion_of_infection", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME},
            ),
            "trigger_sepsis_alert": (
                "alert_predictions_grounded_rate",
                {"query_suspicion_of_infection", "query_sofa", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME},
            ),
        }
    if task_name == "infection_only":
        return {
            "infection_suspect": (
                "infection_predictions_grounded_rate",
                {"query_suspicion_of_infection", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME},
            ),
        }
    if task_name == "aki":
        if label_space and "aki_stage_1" in label_space:
            return {
                "aki_stage_1": ("stage1_predictions_grounded_rate", {"query_kdigo_stage", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME}),
                "aki_stage_2": ("stage2_predictions_grounded_rate", {"query_kdigo_stage", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME}),
                "aki_stage_3": ("stage3_predictions_grounded_rate", {"query_kdigo_stage", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME}),
            }
        return {
            "suspect_aki": ("suspect_predictions_grounded_rate", {"query_kdigo_stage", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME}),
            "trigger_aki_alert": ("alert_predictions_grounded_rate", {"query_kdigo_stage", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME}),
        }
    if task_name == "respiratory_support":
        return {
            "high_flow_or_noninvasive_support": (
                "medium_support_predictions_grounded_rate",
                {"query_ventilation_status", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME},
            ),
            "invasive_vent_required": (
                "invasive_support_predictions_grounded_rate",
                {"query_ventilation_status", CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME},
            ),
        }
    return {}


def _single_task_grounding_counters(
    task_name: str,
    label_space: list[str] | None = None,
) -> dict[str, dict[str, int]]:
    return {
        metric_name: {"num": 0, "den": 0}
        for metric_name, _tools in _single_task_grounding_spec(task_name, label_space).values()
    }


def _update_single_task_grounding(
    task_name: str,
    predicted_action: str | None,
    tool_calls: list[dict[str, Any]],
    grounding_counts: dict[str, dict[str, int]],
    label_space: list[str] | None = None,
) -> None:
    if predicted_action is None:
        return
    tools = {call["tool_name"] for call in tool_calls}
    for action_name, (metric_name, required_tools) in _single_task_grounding_spec(task_name, label_space).items():
        if predicted_action != action_name:
            continue
        grounding_counts[metric_name]["den"] += 1
        if tools & required_tools:
            grounding_counts[metric_name]["num"] += 1


def _finalize_single_task_grounding(grounding_counts: dict[str, dict[str, int]]) -> dict[str, float | None]:
    return {
        metric_name: round(counts["num"] / counts["den"], 4) if counts["den"] else None
        for metric_name, counts in grounding_counts.items()
    }


def _format_single_task_transition_timing(
    task_name: str,
    transition_timing: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if task_name == "sepsis":
        return {
            "infection": transition_timing.get("infection_suspect"),
            "sepsis_alert": transition_timing.get("trigger_sepsis_alert"),
        }
    if task_name == "infection_only":
        return {
            "infection": transition_timing.get("infection_suspect"),
        }
    if task_name == "aki":
        return {
            "aki_suspect": transition_timing.get("suspect_aki"),
            "aki_alert": transition_timing.get("trigger_aki_alert"),
        }
    if task_name == "respiratory_support":
        return {
            "medium_support": transition_timing.get("high_flow_or_noninvasive_support"),
            "invasive_support": transition_timing.get("invasive_vent_required"),
        }
    return transition_timing


def _is_non_monotonic_aki_task(trajectory: Trajectory, label_space: list[str]) -> bool:
    return (
        trajectory.primary_task_name() == "aki"
        and (
            trajectory.task_variant == "non_monotonic_current_state"
            or "aki_stage_1" in label_space
        )
    )


def _state_order(label_space: list[str], label: str) -> int:
    try:
        return label_space.index(label)
    except ValueError:
        return -1


def _update_change_counts(counter: dict[str, int], gt_event: bool, pred_event: bool) -> None:
    if gt_event and pred_event:
        counter["tp"] += 1
    elif not gt_event and pred_event:
        counter["fp"] += 1
    elif gt_event and not pred_event:
        counter["fn"] += 1


def _event_metrics(counter: dict[str, int]) -> dict[str, float]:
    tp = counter["tp"]
    fp = counter["fp"]
    fn = counter["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(_f1(tp, fp, fn), 4),
    }


def _timing_metrics(gt_hours: list[int | None], pred_hours: list[int | None]) -> dict[str, Any]:
    exact_matches = 0
    abs_errors = []
    early = 0
    late = 0
    missed = 0
    for gt, pred in zip(gt_hours, pred_hours):
        if gt == pred:
            exact_matches += 1
        if gt is None and pred is None:
            abs_errors.append(0)
            continue
        if gt is None and pred is not None:
            early += 1
            abs_errors.append(pred)
            continue
        if gt is not None and pred is None:
            missed += 1
            continue
        assert gt is not None and pred is not None
        abs_errors.append(abs(pred - gt))
        if pred < gt:
            early += 1
        elif pred > gt:
            late += 1
    return {
        "exact_match_rate": round(exact_matches / len(gt_hours), 4) if gt_hours else 0.0,
        "mean_absolute_error_hours": round(sum(abs_errors) / len(abs_errors), 4) if abs_errors else None,
        "early_rate": round(early / len(gt_hours), 4) if gt_hours else 0.0,
        "late_rate": round(late / len(gt_hours), 4) if gt_hours else 0.0,
        "missed_rate": round(missed / len(gt_hours), 4) if gt_hours else 0.0,
    }


def rollout_to_dicts(rollouts: list[TrajectoryRollout]) -> list[dict[str, Any]]:
    return [asdict(rollout) for rollout in rollouts]


def _latest_step_tool_output(
    tool_outputs: list[dict[str, Any]],
    key: str,
) -> dict[str, Any] | None:
    return next((item for item in reversed(tool_outputs) if key in item), None)


def _compact_infection_history(output: dict[str, Any] | None) -> dict[str, Any] | None:
    if output is None:
        return None
    evidence_preview = []
    for item in (output.get("evidence") or [])[:2]:
        evidence_preview.append(
            {
                "antibiotic": item.get("antibiotic"),
                "antibiotic_time": item.get("antibiotic_time"),
                "culture_time": item.get("culture_time"),
                "specimen": item.get("specimen"),
            }
        )
    return {
        "infection": output.get("has_suspected_infection"),
        "infection_first_visible_hour": output.get("first_visible_suspected_infection_hour"),
        "infection_first_visible_time": output.get("first_visible_suspected_infection_time"),
        "evidence": evidence_preview,
    }


def _compact_sofa_history(output: dict[str, Any] | None) -> dict[str, Any] | None:
    if output is None:
        return None
    return {
        "sofa_score": output.get("latest_sofa_24hours"),
        "sofa_hr": output.get("latest_visible_hr"),
        "max_sofa_score_so_far": output.get("max_sofa_24hours_so_far"),
    }


def _build_rolling_history_entry(
    *,
    trajectory: Trajectory,
    checkpoint: Any,
    step_index: int,
    tool_outputs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    task_name = trajectory.primary_task_name()
    if task_name == "sepsis":
        infection = _compact_infection_history(
            _latest_step_tool_output(tool_outputs, "has_suspected_infection")
        ) or {
            "infection": None,
            "infection_first_visible_hour": None,
            "infection_first_visible_time": None,
            "evidence": [],
        }
        sofa = _compact_sofa_history(
            _latest_step_tool_output(tool_outputs, "latest_sofa_24hours")
        ) or {
            "sofa_score": None,
            "sofa_hr": None,
            "max_sofa_score_so_far": None,
        }
        return {
            "task_name": task_name,
            "step_index": step_index,
            "t_hour": checkpoint.t_hour,
            "sofa_score": sofa["sofa_score"],
            "sofa_hr": sofa["sofa_hr"],
            "max_sofa_score_so_far": sofa["max_sofa_score_so_far"],
            "infection": infection["infection"],
            "infection_first_visible_hour": infection["infection_first_visible_hour"],
            "infection_first_visible_time": infection["infection_first_visible_time"],
            "evidence": infection["evidence"],
        }
    if task_name == "infection_only":
        infection = _compact_infection_history(
            _latest_step_tool_output(tool_outputs, "has_suspected_infection")
        ) or {
            "infection": None,
            "infection_first_visible_hour": None,
            "infection_first_visible_time": None,
            "evidence": [],
        }
        return {
            "task_name": task_name,
            "step_index": step_index,
            "t_hour": checkpoint.t_hour,
            "infection": infection["infection"],
            "infection_first_visible_hour": infection["infection_first_visible_hour"],
            "infection_first_visible_time": infection["infection_first_visible_time"],
            "evidence": infection["evidence"],
        }
    return None
