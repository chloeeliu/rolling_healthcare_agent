from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Any

from .agent import Agent
from .schemas import (
    ActionDecision,
    AgentStepInput,
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
    def __init__(
        self,
        trajectories: list[Trajectory],
        tool_runtime: ToolRuntime,
        *,
        max_tool_calls_per_step: int = 4,
        event_callback: Any | None = None,
        tool_backend: str = "official",
        task_mode: str = "auto",
    ) -> None:
        self.trajectories = trajectories
        self.tool_runtime = tool_runtime
        self.max_tool_calls_per_step = max_tool_calls_per_step
        self.event_callback = event_callback
        self.tool_backend = tool_backend
        self.task_mode = task_mode

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

        available_tools = trajectory.resolved_tool_names()

        for step_index, checkpoint in enumerate(trajectory.checkpoints):
            instruction = self._instruction_for_trajectory(trajectory)
            step_input = AgentStepInput(
                trajectory_id=trajectory.trajectory_id,
                stay_id=trajectory.stay_id,
                step_index=step_index,
                t_hour=checkpoint.t_hour,
                available_tools=available_tools,
                instruction=instruction,
                task_names=task_names,
                label_spaces=trajectory.label_spaces,
                task_mode=task_mode,
                tool_backend=self.tool_backend,
            )
            history: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
            tool_outputs: list[dict[str, Any]] = []
            primary_task = trajectory.primary_task_name()
            predicted_action: str | None = TASK_BASELINE_ACTION.get(primary_task)
            predicted_task_actions: dict[str, str] | None = None

            self._emit(
                {
                    "event_type": "step_start",
                    "trajectory_id": trajectory.trajectory_id,
                    "stay_id": trajectory.stay_id,
                    "step_index": step_index,
                    "t_hour": checkpoint.t_hour,
                    "gt_action": checkpoint.state_label,
                    "gt_task_actions": checkpoint.task_labels,
                }
            )

            for _ in range(self.max_tool_calls_per_step + 1):
                response = agent.next_response(
                    step_input=step_input.to_dict(),
                    history=history,
                    available_tools=step_input.available_tools,
                )
                if isinstance(response, ToolCall):
                    output = self.tool_runtime.execute(response.tool_name, response.arguments)
                    call_payload = {"tool_name": response.tool_name, "arguments": response.arguments}
                    self._emit(
                        {
                            "event_type": "tool_call",
                            "trajectory_id": trajectory.trajectory_id,
                            "stay_id": trajectory.stay_id,
                            "step_index": step_index,
                            "t_hour": checkpoint.t_hour,
                            "tool_name": response.tool_name,
                            "arguments": response.arguments,
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

            if not trajectory.is_multitask():
                if (
                    predicted_action is not None
                    and predicted_action != TASK_BASELINE_ACTION.get(primary_task)
                ):
                    first_predicted_task_hours[primary_task].setdefault(predicted_action, checkpoint.t_hour)
                if primary_task == "sepsis":
                    if predicted_action == "infection_suspect" and first_predicted_infection_hour is None:
                        first_predicted_infection_hour = checkpoint.t_hour
                    if predicted_action == "trigger_sepsis_alert":
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
    baseline_action = TASK_BASELINE_ACTION[task_name]
    total_steps = 0
    correct_steps = 0
    confusion = Counter()
    per_class = {}
    transition_fields = TASK_TRANSITION_FIELDS.get(task_name, {})
    gt_hours_by_action = {action: [] for action in transition_fields}
    pred_hours_by_action = {action: [] for action in transition_fields}
    grounded_predictions = 0
    total_nonbaseline_predictions = 0

    for rollout in rollouts:
        trajectory = trajectory_by_id[rollout.trajectory_id]
        for step in rollout.steps:
            total_steps += 1
            if step.gt_action == step.predicted_action:
                correct_steps += 1
            confusion[(step.gt_action, step.predicted_action)] += 1
            if step.predicted_action is not None and step.predicted_action != baseline_action:
                total_nonbaseline_predictions += 1
                if _is_grounded(task_name, step.tool_calls):
                    grounded_predictions += 1

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
    if task_name == "sepsis":
        transition_timing = {
            "infection": transition_timing.get("infection_suspect"),
            "sepsis_alert": transition_timing.get("trigger_sepsis_alert"),
        }

    return {
        "task_name": task_name,
        "step_level": {
            "accuracy": round(correct_steps / total_steps, 4) if total_steps else 0.0,
            "macro_f1": macro_f1,
            "per_class": per_class,
        },
        "transition_timing": transition_timing,
        "tool_grounding": {
            "nonbaseline_predictions_grounded_rate": round(
                grounded_predictions / total_nonbaseline_predictions, 4
            )
            if total_nonbaseline_predictions
            else None,
        },
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
        return bool(tools & {"query_suspicion_of_infection", "query_sofa"})
    if task_name == "aki":
        return "query_kdigo_stage" in tools
    if task_name == "respiratory_support":
        return "query_ventilation_status" in tools
    return False


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
