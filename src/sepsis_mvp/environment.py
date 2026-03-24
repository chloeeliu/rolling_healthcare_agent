from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from .agent import Agent
from .schemas import ACTIONS, ActionDecision, AgentStepInput, ToolCall, Trajectory, TrajectoryRollout, StepRecord
from .tools import ConceptToolRuntime


class BenchmarkEnvironment:
    def __init__(
        self,
        trajectories: list[Trajectory],
        tool_runtime: ConceptToolRuntime,
        *,
        max_tool_calls_per_step: int = 4,
    ) -> None:
        self.trajectories = trajectories
        self.tool_runtime = tool_runtime
        self.max_tool_calls_per_step = max_tool_calls_per_step

    def run_trajectory(self, trajectory: Trajectory, agent: Agent) -> TrajectoryRollout:
        steps: list[StepRecord] = []
        first_predicted_infection_hour = None
        first_predicted_alert_hour = None

        for step_index, checkpoint in enumerate(trajectory.checkpoints):
            step_input = AgentStepInput(
                trajectory_id=trajectory.trajectory_id,
                stay_id=trajectory.stay_id,
                step_index=step_index,
                t_hour=checkpoint.t_hour,
                available_tools=["query_suspicion_of_infection", "query_sofa"],
                instruction=(
                    "Use tools if needed. Then output exactly one action: "
                    "keep_monitoring, infection_suspect, or trigger_sepsis_alert."
                ),
            )
            history: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
            tool_outputs: list[dict[str, Any]] = []
            predicted_action = "keep_monitoring"

            for _ in range(self.max_tool_calls_per_step + 1):
                response = agent.next_response(
                    step_input=step_input.to_dict(),
                    history=history,
                    available_tools=step_input.available_tools,
                )
                if isinstance(response, ToolCall):
                    output = self.tool_runtime.execute(response.tool_name, response.arguments)
                    call_payload = {"tool_name": response.tool_name, "arguments": response.arguments}
                    history.append({"type": "tool_call", "tool_name": response.tool_name, "payload": call_payload})
                    history.append({"type": "tool_output", "tool_name": response.tool_name, "payload": output})
                    tool_calls.append(call_payload)
                    tool_outputs.append(output)
                    continue
                if isinstance(response, ActionDecision):
                    predicted_action = response.action
                    break
                raise TypeError(f"Unsupported agent response: {response}")

            if predicted_action == "infection_suspect" and first_predicted_infection_hour is None:
                first_predicted_infection_hour = checkpoint.t_hour
            if predicted_action == "trigger_sepsis_alert":
                if first_predicted_infection_hour is None:
                    first_predicted_infection_hour = checkpoint.t_hour
                if first_predicted_alert_hour is None:
                    first_predicted_alert_hour = checkpoint.t_hour

            steps.append(
                StepRecord(
                    step_index=step_index,
                    t_hour=checkpoint.t_hour,
                    gt_action=checkpoint.state_label,
                    predicted_action=predicted_action,
                    tool_calls=tool_calls,
                    tool_outputs=tool_outputs,
                )
            )

        return TrajectoryRollout(
            trajectory_id=trajectory.trajectory_id,
            stay_id=trajectory.stay_id,
            steps=steps,
            first_predicted_infection_hour=first_predicted_infection_hour,
            first_predicted_alert_hour=first_predicted_alert_hour,
        )

    def run_all(self, agent: Agent) -> list[TrajectoryRollout]:
        return [self.run_trajectory(trajectory, agent) for trajectory in self.trajectories]


def _f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def evaluate_rollouts(trajectories: list[Trajectory], rollouts: list[TrajectoryRollout]) -> dict[str, Any]:
    trajectory_by_id = {trajectory.trajectory_id: trajectory for trajectory in trajectories}
    total_steps = 0
    correct_steps = 0
    confusion = Counter()
    per_class = {}

    gt_infection_hours = []
    gt_alert_hours = []
    pred_infection_hours = []
    pred_alert_hours = []
    grounded_infection_predictions = 0
    total_infection_predictions = 0
    grounded_alert_predictions = 0
    total_alert_predictions = 0

    for rollout in rollouts:
        trajectory = trajectory_by_id[rollout.trajectory_id]
        for step in rollout.steps:
            total_steps += 1
            if step.gt_action == step.predicted_action:
                correct_steps += 1
            confusion[(step.gt_action, step.predicted_action)] += 1
            if step.predicted_action == "infection_suspect":
                total_infection_predictions += 1
                if any(call["tool_name"] == "query_suspicion_of_infection" for call in step.tool_calls):
                    grounded_infection_predictions += 1
            if step.predicted_action == "trigger_sepsis_alert":
                total_alert_predictions += 1
                if any(call["tool_name"] in {"query_suspicion_of_infection", "query_sofa"} for call in step.tool_calls):
                    grounded_alert_predictions += 1

        gt_infection_hours.append(trajectory.transitions["infection_start_hour"])
        gt_alert_hours.append(trajectory.transitions["sepsis_start_hour"])
        pred_infection_hours.append(rollout.first_predicted_infection_hour)
        pred_alert_hours.append(rollout.first_predicted_alert_hour)

    for action in ACTIONS:
        tp = confusion[(action, action)]
        fp = sum(confusion[(gt, action)] for gt in ACTIONS if gt != action)
        fn = sum(confusion[(action, pred)] for pred in ACTIONS if pred != action)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_class[action] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_f1(tp, fp, fn), 4),
        }

    macro_f1 = round(sum(metrics["f1"] for metrics in per_class.values()) / len(ACTIONS), 4)
    infection_timing = _timing_metrics(gt_infection_hours, pred_infection_hours)
    alert_timing = _timing_metrics(gt_alert_hours, pred_alert_hours)

    return {
        "step_level": {
            "accuracy": round(correct_steps / total_steps, 4) if total_steps else 0.0,
            "macro_f1": macro_f1,
            "per_class": per_class,
        },
        "transition_timing": {
            "infection": infection_timing,
            "sepsis_alert": alert_timing,
        },
        "tool_grounding": {
            "infection_predictions_grounded_rate": round(
                grounded_infection_predictions / total_infection_predictions, 4
            )
            if total_infection_predictions
            else None,
            "alert_predictions_grounded_rate": round(grounded_alert_predictions / total_alert_predictions, 4)
            if total_alert_predictions
            else None,
        },
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

