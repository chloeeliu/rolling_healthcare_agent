import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sepsis_mvp.agent import QwenChatAgent, _coerce_agent_output, HeuristicAgent
from sepsis_mvp.dataset import (
    build_dataset,
    load_concept_tables,
    load_multitask_csv_dataset,
    load_rolling_csv_dataset,
    save_trajectories,
)
from sepsis_mvp.environment import BenchmarkEnvironment, evaluate_rollouts
from sepsis_mvp.schemas import Checkpoint, Trajectory
from sepsis_mvp.tools import ConceptToolRuntime


SAMPLE = ROOT / "data" / "sample_concepts.json"


class PipelineTest(unittest.TestCase):
    def _multitask_step_input(self):
        return {
            "trajectory_id": "mimiciv_stay_1",
            "stay_id": 30,
            "step_index": 0,
            "t_hour": 4,
            "available_tools": [
                "query_suspicion_of_infection",
                "query_sofa",
                "query_kdigo_stage",
                "query_ventilation_status",
            ],
            "instruction": "Use tools if needed. Then output one decision for each monitored task.",
            "task_names": ["sepsis", "aki", "respiratory_support"],
            "label_spaces": {
                "sepsis": ["keep_monitoring", "infection_suspect", "trigger_sepsis_alert"],
                "aki": ["keep_monitoring", "suspect_aki", "trigger_aki_alert"],
                "respiratory_support": [
                    "room_air_or_low_support",
                    "high_flow_or_noninvasive_support",
                    "invasive_vent_required",
                ],
            },
        }

    def test_multitask_task_action_alias_is_normalized(self):
        response = _coerce_agent_output(
            {
                "task_actions": {
                    "sepsis": "keep_monitoring",
                    "aki": "keep_monitoring",
                    "resp_support": "room_air_or_low_support",
                }
            }
        )
        self.assertEqual(
            response.task_actions,
            {
                "sepsis": "keep_monitoring",
                "aki": "keep_monitoring",
                "respiratory_support": "room_air_or_low_support",
            },
        )

    def test_qwen_agent_forces_next_required_tool_when_model_skips_tool_use(self):
        class FakeClient:
            def __init__(self):
                self.max_new_tokens = 250

            def generate(self, messages):
                return '{"task_actions":{"sepsis":"keep_monitoring","aki":"keep_monitoring","respiratory_support":"room_air_or_low_support"}}'

        trace_events = []
        agent = object.__new__(QwenChatAgent)
        agent.model = "fake"
        agent.temperature = 0.0
        agent.top_p = 0.95
        agent.max_new_tokens = 250
        agent.repair_max_new_tokens = 120
        agent.trace_callback = trace_events.append
        agent.client = FakeClient()

        response = agent.next_response(
            self._multitask_step_input(),
            history=[],
            available_tools=[
                "query_suspicion_of_infection",
                "query_sofa",
                "query_kdigo_stage",
                "query_ventilation_status",
            ],
        )
        self.assertEqual(response.tool_name, "query_suspicion_of_infection")
        self.assertEqual(response.arguments, {"stay_id": 30, "t_hour": 4})
        self.assertTrue(any(event["event_type"] == "model_output_forced_tool" for event in trace_events))

    def test_qwen_agent_forces_next_required_tool_when_model_repeats_prior_tool(self):
        class FakeClient:
            def __init__(self):
                self.max_new_tokens = 250

            def generate(self, messages):
                return '{"tool_name":"query_suspicion_of_infection","arguments":{"stay_id":30,"t_hour":4}}'

        agent = object.__new__(QwenChatAgent)
        agent.model = "fake"
        agent.temperature = 0.0
        agent.top_p = 0.95
        agent.max_new_tokens = 250
        agent.repair_max_new_tokens = 120
        agent.trace_callback = None
        agent.client = FakeClient()

        history = [
            {
                "type": "tool_call",
                "tool_name": "query_suspicion_of_infection",
                "payload": {"tool_name": "query_suspicion_of_infection", "arguments": {"stay_id": 30, "t_hour": 4}},
            },
            {
                "type": "tool_output",
                "tool_name": "query_suspicion_of_infection",
                "payload": {"stay_id": 30, "t_hour": 4, "has_suspected_infection": True},
            },
        ]

        response = agent.next_response(
            self._multitask_step_input(),
            history=history,
            available_tools=[
                "query_suspicion_of_infection",
                "query_sofa",
                "query_kdigo_stage",
                "query_ventilation_status",
            ],
        )
        self.assertEqual(response.tool_name, "query_sofa")
        self.assertEqual(response.arguments, {"stay_id": 30, "t_hour": 4})

    def test_qwen_agent_repairs_to_final_decision_after_all_tools_are_done(self):
        class FakeClient:
            def __init__(self):
                self.max_new_tokens = 250
                self.outputs = [
                    '{"tool_name":"query_ventilation_status","arguments":{"stay_id":30,"t_hour":4}}',
                    '{"task_actions":{"sepsis":"infection_suspect","aki":"suspect_aki","respiratory_support":"high_flow_or_noninvasive_support"}}',
                ]

            def generate(self, messages):
                return self.outputs.pop(0)

        agent = object.__new__(QwenChatAgent)
        agent.model = "fake"
        agent.temperature = 0.0
        agent.top_p = 0.95
        agent.max_new_tokens = 250
        agent.repair_max_new_tokens = 120
        agent.trace_callback = None
        agent.client = FakeClient()

        history = []
        for tool_name, payload in [
            (
                "query_suspicion_of_infection",
                {"stay_id": 30, "t_hour": 4, "has_suspected_infection": True},
            ),
            ("query_sofa", {"stay_id": 30, "t_hour": 4, "latest_sofa_24hours": 1}),
            ("query_kdigo_stage", {"stay_id": 30, "t_hour": 4, "latest_aki_stage_smoothed": 1}),
            (
                "query_ventilation_status",
                {
                    "stay_id": 30,
                    "t_hour": 4,
                    "current_support_level": "high_flow_or_noninvasive_support",
                    "highest_support_level_so_far": "high_flow_or_noninvasive_support",
                },
            ),
        ]:
            history.append({"type": "tool_call", "tool_name": tool_name, "payload": {"tool_name": tool_name}})
            history.append({"type": "tool_output", "tool_name": tool_name, "payload": payload})

        response = agent.next_response(
            self._multitask_step_input(),
            history=history,
            available_tools=[
                "query_suspicion_of_infection",
                "query_sofa",
                "query_kdigo_stage",
                "query_ventilation_status",
            ],
        )
        self.assertEqual(
            response.task_actions,
            {
                "sepsis": "infection_suspect",
                "aki": "suspect_aki",
                "respiratory_support": "high_flow_or_noninvasive_support",
            },
        )

    def test_dataset_builder_snaps_transitions_to_checkpoints(self):
        concepts = load_concept_tables(SAMPLE)
        trajectories = build_dataset(concepts)
        first = next(trajectory for trajectory in trajectories if trajectory.stay_id == 300001)
        self.assertEqual(first.transitions["infection_start_hour"], 8)
        self.assertEqual(first.transitions["sepsis_start_hour"], 16)
        labels = [checkpoint.state_label for checkpoint in first.checkpoints]
        self.assertEqual(
            labels,
            [
                "keep_monitoring",
                "keep_monitoring",
                "infection_suspect",
                "infection_suspect",
                "trigger_sepsis_alert",
                "trigger_sepsis_alert",
                "trigger_sepsis_alert",
            ],
        )

    def test_tools_are_time_gated(self):
        concepts = load_concept_tables(SAMPLE)
        runtime = ConceptToolRuntime(concepts)
        early = runtime.query_suspicion_of_infection(300001, 4)
        late = runtime.query_suspicion_of_infection(300001, 8)
        self.assertFalse(early["has_suspected_infection"])
        self.assertTrue(late["has_suspected_infection"])
        self.assertAlmostEqual(late["first_visible_suspected_infection_hour"], 6.7, places=1)

    def test_end_to_end_run(self):
        concepts = load_concept_tables(SAMPLE)
        trajectories = build_dataset(concepts)
        runtime = ConceptToolRuntime(concepts)
        environment = BenchmarkEnvironment(trajectories, runtime)
        rollouts = environment.run_all(HeuristicAgent())
        metrics = evaluate_rollouts(trajectories, rollouts)
        self.assertIn("step_level", metrics)
        self.assertIn("transition_timing", metrics)
        self.assertEqual(len(rollouts), 2)

    def test_environment_emits_incremental_events(self):
        concepts = load_concept_tables(SAMPLE)
        trajectories = build_dataset(concepts)
        runtime = ConceptToolRuntime(concepts)
        events = []
        environment = BenchmarkEnvironment(trajectories[:1], runtime, event_callback=events.append)
        rollouts = environment.run_all(HeuristicAgent())
        self.assertEqual(len(rollouts), 1)
        event_types = {event["event_type"] for event in events}
        self.assertIn("trajectory_start", event_types)
        self.assertIn("tool_call", event_types)
        self.assertIn("tool_output", event_types)
        self.assertIn("action", event_types)
        self.assertIn("trajectory_complete", event_types)

    def test_dataset_can_be_saved(self):
        concepts = load_concept_tables(SAMPLE)
        trajectories = build_dataset(concepts)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "trajectories.json"
            save_trajectories(trajectories, output)
            payload = json.loads(output.read_text())
            self.assertEqual(len(payload), 2)

    def test_csv_loader_filters_out_of_scope_trajectory_in_strict_mode(self):
        csv_text = """trajectory_id,subject_id,hadm_id,stay_id,icu_intime,icu_outtime,icu_los_hours,is_sepsis,infection_start_time,organ_dysfunction_start_time,sepsis_start_time,infection_start_hour,organ_dysfunction_start_hour,sepsis_start_hour,t_hour,checkpoint_time,state_label,terminal
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,1,2150-01-01T02:00:00,2150-01-01T08:00:00,2150-01-01T12:00:00,4,8,12,0,2150-01-01T00:00:00,keep_monitoring,false
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,1,2150-01-01T02:00:00,2150-01-01T08:00:00,2150-01-01T12:00:00,4,8,12,4,2150-01-01T04:00:00,infection_suspect,false
mimiciv_stay_2,11,21,31,2150-01-01T00:00:00,2150-01-02T00:00:00,24,1,2150-01-03T00:00:00,2150-01-01T04:00:00,2150-01-01T12:00:00,48,4,12,0,2150-01-01T00:00:00,keep_monitoring,false
mimiciv_stay_2,11,21,31,2150-01-01T00:00:00,2150-01-02T00:00:00,24,1,2150-01-03T00:00:00,2150-01-01T04:00:00,2150-01-01T12:00:00,48,4,12,4,2150-01-01T04:00:00,organ_dysfunction_suspect,false
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rolling.csv"
            path.write_text(csv_text)
            result = load_rolling_csv_dataset(path, strict_mvp=True)
            self.assertEqual(result.included_trajectories, 1)
            self.assertEqual(result.skipped_trajectories, 1)
            self.assertEqual(result.skipped_reasons["unsupported_labels"], 1)

    def test_multitask_csv_loader_parses_task_labels(self):
        csv_text = """trajectory_id,subject_id,hadm_id,stay_id,icu_intime,icu_outtime,icu_los_hours,sepsis_positive,aki_positive,respiratory_support_positive,infection_start_time,sepsis_start_time,aki_stage1_start_time,aki_stage23_start_time,medium_support_start_time,invasive_support_start_time,infection_start_hour,sepsis_start_hour,aki_stage1_start_hour,aki_stage23_start_hour,medium_support_start_hour,invasive_support_start_hour,t_hour,checkpoint_time,sepsis_label,aki_label,respiratory_support_label,sepsis_terminal,aki_terminal,respiratory_support_terminal,terminal_any
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,1,1,1,2150-01-01T01:00:00,2150-01-01T08:00:00,2150-01-01T02:00:00,2150-01-01T12:00:00,2150-01-01T04:00:00,2150-01-01T16:00:00,4,8,4,12,4,16,0,2150-01-01T00:00:00,keep_monitoring,keep_monitoring,room_air_or_low_support,false,false,false,false
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,1,1,1,2150-01-01T01:00:00,2150-01-01T08:00:00,2150-01-01T02:00:00,2150-01-01T12:00:00,2150-01-01T04:00:00,2150-01-01T16:00:00,4,8,4,12,4,16,4,2150-01-01T04:00:00,infection_suspect,suspect_aki,high_flow_or_noninvasive_support,false,false,false,false
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "multitask.csv"
            path.write_text(csv_text)
            result = load_multitask_csv_dataset(path)
            self.assertEqual(result.included_trajectories, 1)
            trajectory = result.trajectories[0]
            self.assertEqual(trajectory.task_names, ["sepsis", "aki", "respiratory_support"])
            self.assertEqual(
                trajectory.checkpoints[1].task_labels,
                {
                    "sepsis": "infection_suspect",
                    "aki": "suspect_aki",
                    "respiratory_support": "high_flow_or_noninvasive_support",
                },
            )

    def test_multitask_heuristic_run(self):
        class StubRuntime:
            def execute(self, tool_name, arguments):
                t = arguments["t_hour"]
                if tool_name == "query_suspicion_of_infection":
                    return {"stay_id": 30, "t_hour": t, "has_suspected_infection": t >= 4}
                if tool_name == "query_sofa":
                    return {"stay_id": 30, "t_hour": t, "latest_sofa_24hours": 2 if t >= 8 else 1}
                if tool_name == "query_kdigo_stage":
                    return {
                        "stay_id": 30,
                        "t_hour": t,
                        "latest_aki_stage_smoothed": 2 if t >= 8 else (1 if t >= 4 else 0),
                    }
                if tool_name == "query_ventilation_status":
                    return {
                        "stay_id": 30,
                        "t_hour": t,
                        "current_support_level": "room_air_or_low_support",
                        "highest_support_level_so_far": (
                            "invasive_vent_required"
                            if t >= 8
                            else ("high_flow_or_noninvasive_support" if t >= 4 else "room_air_or_low_support")
                        ),
                    }
                raise ValueError(tool_name)

        trajectory = Trajectory(
            trajectory_id="mimiciv_stay_1",
            stay_id=30,
            subject_id=10,
            hadm_id=20,
            anchor="icu_intime",
            step_hours=4,
            horizon_hours=8,
            transitions={},
            checkpoints=[
                Checkpoint(
                    t_hour=0,
                    task_labels={
                        "sepsis": "keep_monitoring",
                        "aki": "keep_monitoring",
                        "respiratory_support": "room_air_or_low_support",
                    },
                ),
                Checkpoint(
                    t_hour=4,
                    task_labels={
                        "sepsis": "infection_suspect",
                        "aki": "suspect_aki",
                        "respiratory_support": "high_flow_or_noninvasive_support",
                    },
                ),
                Checkpoint(
                    t_hour=8,
                    task_labels={
                        "sepsis": "trigger_sepsis_alert",
                        "aki": "trigger_aki_alert",
                        "respiratory_support": "invasive_vent_required",
                    },
                ),
            ],
            task_name="multitask",
            task_names=["sepsis", "aki", "respiratory_support"],
            tool_names=[
                "query_suspicion_of_infection",
                "query_sofa",
                "query_kdigo_stage",
                "query_ventilation_status",
            ],
            label_spaces={
                "sepsis": ["keep_monitoring", "infection_suspect", "trigger_sepsis_alert"],
                "aki": ["keep_monitoring", "suspect_aki", "trigger_aki_alert"],
                "respiratory_support": [
                    "room_air_or_low_support",
                    "high_flow_or_noninvasive_support",
                    "invasive_vent_required",
                ],
            },
        )
        environment = BenchmarkEnvironment([trajectory], StubRuntime())
        rollouts = environment.run_all(HeuristicAgent())
        metrics = evaluate_rollouts([trajectory], rollouts)
        self.assertIn("joint_step_accuracy", metrics)
        self.assertEqual(metrics["joint_step_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
