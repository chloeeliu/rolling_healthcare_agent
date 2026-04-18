import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sepsis_mvp.agent import (
    QwenChatAgent,
    _build_messages,
    _build_zeroshot_messages,
    _coerce_agent_output,
    _coerce_zeroshot_output,
    _extract_zeroshot_response,
    HeuristicAgent,
)
from sepsis_mvp.cli import run_command
from sepsis_mvp.dataset import (
    build_dataset,
    load_concept_tables,
    load_dataset_auto,
    load_multitask_csv_dataset,
    load_rolling_csv_dataset,
    load_single_task_csv_dataset,
    save_trajectories,
)
from sepsis_mvp.environment import BenchmarkEnvironment, evaluate_rollouts
from sepsis_mvp.schemas import CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME, Checkpoint, Trajectory, ToolCall, ActionDecision
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

    def test_prompt_includes_basic_clinical_guidance(self):
        messages = _build_messages(
            self._multitask_step_input(),
            history=[],
            available_tools=[
                "query_suspicion_of_infection",
                "query_sofa",
                "query_kdigo_stage",
                "query_ventilation_status",
            ],
        )
        system_prompt = messages[0]["content"]
        self.assertIn("SOFA is 2 or higher", system_prompt)
        self.assertIn("KDIGO stage is 2 or 3", system_prompt)
        self.assertIn("Map HFNC and non-invasive ventilation", system_prompt)

    def test_non_monotonic_aki_prompt_includes_deescalation_guidance(self):
        step_input = {
            "trajectory_id": "mimiciv_stay_1",
            "stay_id": 30,
            "step_index": 0,
            "t_hour": 8,
            "available_tools": ["query_kdigo_stage"],
            "instruction": "Use tools if needed. Then output exactly one action.",
            "task_names": ["aki"],
            "task_variant": "non_monotonic_current_state",
            "label_spaces": {
                "aki": ["no_aki", "aki_stage_1", "aki_stage_2", "aki_stage_3"],
            },
        }
        messages = _build_messages(step_input, history=[], available_tools=["query_kdigo_stage"])
        system_prompt = messages[0]["content"]
        self.assertIn("do not assume AKI states are permanent".lower(), system_prompt.lower())
        self.assertIn("aki_stage_1", system_prompt)
        self.assertIn("current_aki_state_label", system_prompt)

    def test_zeroshot_prompt_mentions_prescriptions_and_raw_views(self):
        step_input = {
            "trajectory_id": "mimiciv_stay_1",
            "stay_id": 30,
            "step_index": 0,
            "t_hour": 4,
            "task_names": ["sepsis"],
            "tool_backend": "zeroshot_raw",
            "max_step_interactions": 4,
        }
        messages = _build_zeroshot_messages(step_input, history=[], guideline_text="guideline body")
        system_prompt = messages[0]["content"]
        self.assertIn("hospital prescriptions", system_prompt.lower())
        self.assertIn("microbiology", system_prompt.lower())
        self.assertIn("visible_until", system_prompt)

    def test_infection_only_zeroshot_prompt_uses_overlap_windows_without_sofa_label(self):
        step_input = {
            "trajectory_id": "mimiciv_stay_1",
            "stay_id": 30,
            "step_index": 0,
            "t_hour": 4,
            "task_names": ["infection_only"],
            "label_spaces": {
                "infection_only": ["keep_monitoring", "infection_suspect"],
            },
            "tool_backend": "zeroshot_raw",
            "max_step_interactions": 4,
        }
        messages = _build_zeroshot_messages(step_input, history=[], guideline_text="guideline body")
        system_prompt = messages[0]["content"]
        self.assertIn("within the next 24 hours", system_prompt)
        self.assertIn("within the next 72 hours", system_prompt)
        self.assertNotIn("trigger_sepsis_alert", system_prompt)
        self.assertIn("fenced SQL block", system_prompt)

    def test_zeroshot_output_coercion_maps_python_code_to_run_python(self):
        response = _coerce_zeroshot_output({"python_code": "RESULT = 1"})
        self.assertEqual(response.tool_name, CODE_EXEC_TOOL_NAME)
        self.assertEqual(response.arguments, {"code": "RESULT = 1"})

    def test_zeroshot_output_coercion_maps_sql_code_to_run_sql(self):
        response = _coerce_zeroshot_output({"sql_code": "SELECT 1 AS x"}, execution_mode="sql")
        self.assertEqual(response.tool_name, SQL_EXEC_TOOL_NAME)
        self.assertEqual(response.arguments, {"sql": "SELECT 1 AS x"})

    def test_zeroshot_response_accepts_fenced_python_block(self):
        response = _extract_zeroshot_response("```python\nRESULT = {'x': 1}\n```")
        self.assertEqual(response.tool_name, CODE_EXEC_TOOL_NAME)
        self.assertEqual(response.arguments, {"code": "RESULT = {'x': 1}"})

    def test_zeroshot_response_accepts_fenced_sql_block_for_infection_only(self):
        response = _extract_zeroshot_response(
            "```sql\nSELECT TRUE AS has_suspected_infection\n```",
            execution_mode="sql",
        )
        self.assertEqual(response.tool_name, SQL_EXEC_TOOL_NAME)
        self.assertEqual(response.arguments, {"sql": "SELECT TRUE AS has_suspected_infection"})

    def test_zeroshot_response_accepts_infection_only_action(self):
        response = _extract_zeroshot_response(
            '{"action":"infection_suspect"}',
            allowed_actions=["keep_monitoring", "infection_suspect"],
        )
        self.assertEqual(response.action, "infection_suspect")

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

    def test_qwen_agent_zeroshot_returns_python_then_final_action(self):
        class FakeClient:
            def __init__(self):
                self.max_new_tokens = 250
                self.outputs = [
                    '{"python_code":"RESULT = {\\"visible_infection\\": True}"}',
                    '{"action":"infection_suspect"}',
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
        agent.zeroshot_guideline_text = "guideline"

        step_input = {
            "trajectory_id": "mimiciv_stay_1",
            "stay_id": 30,
            "step_index": 0,
            "t_hour": 4,
            "task_names": ["sepsis"],
            "tool_backend": "zeroshot_raw",
            "max_step_interactions": 4,
        }

        first = agent.next_response(step_input, history=[], available_tools=[])
        self.assertEqual(first.tool_name, CODE_EXEC_TOOL_NAME)

        history = [
            {
                "type": "tool_call",
                "tool_name": CODE_EXEC_TOOL_NAME,
                "payload": {"tool_name": CODE_EXEC_TOOL_NAME, "arguments": {"code": "RESULT = {'visible_infection': True}"}},
            },
            {
                "type": "tool_output",
                "tool_name": CODE_EXEC_TOOL_NAME,
                "payload": {"backend": "zeroshot_raw", "ok": True, "stdout": "", "stderr": "", "result": {"kind": "dict", "preview": {"visible_infection": True}}},
            },
        ]
        second = agent.next_response(step_input, history=history, available_tools=[])
        self.assertEqual(second.action, "infection_suspect")

    def test_qwen_agent_infection_only_zeroshot_returns_sql_then_final_action(self):
        class FakeClient:
            def __init__(self):
                self.max_new_tokens = 250
                self.outputs = [
                    "```sql\nSELECT TRUE AS has_suspected_infection\n```",
                    '{"action":"infection_suspect"}',
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
        agent.zeroshot_guideline_text = "guideline"

        step_input = {
            "trajectory_id": "mimiciv_stay_1",
            "stay_id": 30,
            "step_index": 0,
            "t_hour": 4,
            "task_names": ["infection_only"],
            "label_spaces": {"infection_only": ["keep_monitoring", "infection_suspect"]},
            "tool_backend": "zeroshot_raw",
            "max_step_interactions": 4,
        }

        first = agent.next_response(step_input, history=[], available_tools=[])
        self.assertEqual(first.tool_name, SQL_EXEC_TOOL_NAME)

        history = [
            {
                "type": "tool_call",
                "tool_name": SQL_EXEC_TOOL_NAME,
                "payload": {"tool_name": SQL_EXEC_TOOL_NAME, "arguments": {"sql": "SELECT TRUE AS has_suspected_infection"}},
            },
            {
                "type": "tool_output",
                "tool_name": SQL_EXEC_TOOL_NAME,
                "payload": {
                    "backend": "zeroshot_raw",
                    "ok": True,
                    "stdout": "",
                    "stderr": "",
                    "result": {
                        "kind": "dataframe",
                        "rows": 1,
                        "columns": ["has_suspected_infection"],
                        "head": [{"has_suspected_infection": True}],
                    },
                },
            },
        ]
        second = agent.next_response(step_input, history=history, available_tools=[])
        self.assertEqual(second.action, "infection_suspect")

    def test_qwen_agent_zeroshot_repairs_truncated_json_with_fenced_python(self):
        class FakeClient:
            def __init__(self):
                self.max_new_tokens = 250
                self.outputs = [
                    '{"python_code":"RESULT = query_db(\\"SELECT 1 AS x\\")',
                    "```python\nRESULT = {'visible_infection': True}\n```",
                ]

            def generate(self, messages):
                return self.outputs.pop(0)

        agent = object.__new__(QwenChatAgent)
        agent.model = "fake"
        agent.temperature = 0.0
        agent.top_p = 0.95
        agent.max_new_tokens = 250
        agent.repair_max_new_tokens = 240
        agent.trace_callback = None
        agent.client = FakeClient()
        agent.zeroshot_guideline_text = "guideline"

        step_input = {
            "trajectory_id": "mimiciv_stay_1",
            "stay_id": 30,
            "step_index": 0,
            "t_hour": 4,
            "task_names": ["sepsis"],
            "tool_backend": "zeroshot_raw",
            "max_step_interactions": 4,
        }

        first = agent.next_response(step_input, history=[], available_tools=[])
        self.assertEqual(first.tool_name, CODE_EXEC_TOOL_NAME)
        self.assertEqual(first.arguments, {"code": "RESULT = {'visible_infection': True}"})

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

    def test_environment_supports_zero_shot_python_sessions(self):
        class StubZeroShotRuntime:
            def __init__(self):
                self.started = []
                self.closed = []

            def start_step_session(self, *, stay_id, t_hour):
                session_id = f"{stay_id}:{t_hour}"
                self.started.append(session_id)
                return session_id

            def close_step_session(self, session_id):
                self.closed.append(session_id)

            def execute(self, tool_name, arguments):
                if tool_name != CODE_EXEC_TOOL_NAME:
                    raise ValueError(tool_name)
                return {
                    "backend": "zeroshot_raw",
                    "ok": True,
                    "stdout": "",
                    "stderr": "",
                    "result": {"kind": "dict", "preview": {"has_infection": True}},
                }

        class StubZeroShotAgent:
            def __init__(self):
                self.calls = 0

            def next_response(self, step_input, history, available_tools):
                self.calls += 1
                if not history:
                    return ToolCall(tool_name=CODE_EXEC_TOOL_NAME, arguments={"code": "RESULT = {'has_infection': True}"})
                return ActionDecision(action="infection_suspect")

        trajectory = Trajectory(
            trajectory_id="mimiciv_stay_1",
            stay_id=30,
            subject_id=10,
            hadm_id=20,
            anchor="icu_intime",
            step_hours=4,
            horizon_hours=0,
            transitions={"infection_start_hour": 0, "sepsis_start_hour": 8},
            checkpoints=[Checkpoint(t_hour=0, state_label="infection_suspect")],
            task_name="sepsis",
            task_names=["sepsis"],
        )
        runtime = StubZeroShotRuntime()
        environment = BenchmarkEnvironment([trajectory], runtime, task_mode="single", tool_backend="zeroshot_raw")
        rollout = environment.run_all(StubZeroShotAgent())[0]
        self.assertEqual(rollout.steps[0].predicted_action, "infection_suspect")
        self.assertEqual(runtime.started, ["30:0"])
        self.assertEqual(runtime.closed, ["30:0"])
        self.assertEqual(rollout.steps[0].tool_calls[0]["tool_name"], CODE_EXEC_TOOL_NAME)

    def test_environment_supports_zero_shot_sql_sessions(self):
        class StubZeroShotRuntime:
            def __init__(self):
                self.started = []
                self.closed = []

            def start_step_session(self, *, stay_id, t_hour):
                session_id = f"{stay_id}:{t_hour}"
                self.started.append(session_id)
                return session_id

            def close_step_session(self, session_id):
                self.closed.append(session_id)

            def execute(self, tool_name, arguments):
                if tool_name != SQL_EXEC_TOOL_NAME:
                    raise ValueError(tool_name)
                return {
                    "backend": "zeroshot_raw",
                    "ok": True,
                    "stdout": "",
                    "stderr": "",
                    "result": {"kind": "dataframe", "rows": 1, "columns": ["has_suspected_infection"], "head": [{"has_suspected_infection": True}]},
                }

        class StubZeroShotAgent:
            def next_response(self, step_input, history, available_tools):
                if not history:
                    return ToolCall(tool_name=SQL_EXEC_TOOL_NAME, arguments={"sql": "SELECT TRUE AS has_suspected_infection"})
                return ActionDecision(action="infection_suspect")

        trajectory = Trajectory(
            trajectory_id="mimiciv_stay_1",
            stay_id=30,
            subject_id=10,
            hadm_id=20,
            anchor="icu_intime",
            step_hours=4,
            horizon_hours=0,
            transitions={"infection_start_hour": 0},
            checkpoints=[Checkpoint(t_hour=0, state_label="infection_suspect")],
            task_name="infection_only",
            task_names=["infection_only"],
        )
        runtime = StubZeroShotRuntime()
        environment = BenchmarkEnvironment([trajectory], runtime, task_mode="single", tool_backend="zeroshot_raw")
        rollout = environment.run_all(StubZeroShotAgent())[0]
        self.assertEqual(rollout.steps[0].predicted_action, "infection_suspect")
        self.assertEqual(runtime.started, ["30:0"])
        self.assertEqual(runtime.closed, ["30:0"])
        self.assertEqual(rollout.steps[0].tool_calls[0]["tool_name"], SQL_EXEC_TOOL_NAME)

    def test_dataset_can_be_saved(self):
        concepts = load_concept_tables(SAMPLE)
        trajectories = build_dataset(concepts)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "trajectories.json"
            save_trajectories(trajectories, output)
            payload = json.loads(output.read_text())
            self.assertEqual(len(payload), 2)

    def test_run_command_writes_evaluation_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluation_output = Path(tmpdir) / "evaluation.json"
            args = argparse.Namespace(
                concepts=str(SAMPLE),
                db_path=None,
                dataset=str(ROOT / "data" / "sample_trajectories.json"),
                task_mode="single",
                tool_backend="official",
                autoformalized_library=str(ROOT / "autoformalized_library"),
                include_out_of_scope=False,
                agent="heuristic",
                model="Qwen/Qwen3.5-9B",
                temperature=0.0,
                top_p=0.95,
                max_new_tokens=250,
                sample_size=1,
                resume=False,
                sofa_alert_threshold=2,
                rollouts_output=None,
                evaluation_output=str(evaluation_output),
                events_output=None,
                trajectory_output=None,
            )
            exit_code = run_command(args)
            self.assertEqual(exit_code, 0)
            payload = json.loads(evaluation_output.read_text())
            self.assertEqual(payload["task_mode"], "single")
            self.assertEqual(payload["tool_backend"], "official")
            self.assertEqual(payload["agent"], "heuristic")
            self.assertIn("metrics", payload)
            self.assertIn("infection_predictions_grounded_rate", payload["metrics"]["tool_grounding"])
            self.assertIn("alert_predictions_grounded_rate", payload["metrics"]["tool_grounding"])

    def test_run_command_can_resume_from_existing_trajectory_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            concepts = load_concept_tables(SAMPLE)
            trajectories = build_dataset(concepts)
            dataset_path = tmpdir / "dataset.json"
            save_trajectories(trajectories, dataset_path)

            runtime = ConceptToolRuntime(concepts)
            environment = BenchmarkEnvironment(trajectories[:1], runtime)
            existing_rollout = environment.run_all(HeuristicAgent())[0]

            trajectory_output = tmpdir / "trajectories.jsonl"
            with trajectory_output.open("w") as handle:
                handle.write(json.dumps(existing_rollout.to_dict()) + "\n")

            evaluation_output = tmpdir / "evaluation.json"
            rollouts_output = tmpdir / "rollouts.json"
            args = argparse.Namespace(
                concepts=str(SAMPLE),
                db_path=None,
                dataset=str(dataset_path),
                task_mode="single",
                tool_backend="official",
                autoformalized_library=str(ROOT / "autoformalized_library"),
                include_out_of_scope=False,
                agent="heuristic",
                model="Qwen/Qwen3.5-9B",
                temperature=0.0,
                top_p=0.95,
                max_new_tokens=250,
                sample_size=None,
                resume=True,
                sofa_alert_threshold=2,
                rollouts_output=str(rollouts_output),
                evaluation_output=str(evaluation_output),
                events_output=None,
                trajectory_output=str(trajectory_output),
            )

            exit_code = run_command(args)
            self.assertEqual(exit_code, 0)

            trajectory_lines = [
                json.loads(line)
                for line in trajectory_output.read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(len(trajectory_lines), len(trajectories))
            self.assertEqual(
                {item["trajectory_id"] for item in trajectory_lines},
                {trajectory.trajectory_id for trajectory in trajectories},
            )

            payload = json.loads(evaluation_output.read_text())
            self.assertTrue(payload["resume"])
            self.assertEqual(payload["existing_completed_trajectories"], 1)
            self.assertEqual(payload["newly_processed_trajectories"], len(trajectories) - 1)
            self.assertEqual(payload["num_trajectories"], len(trajectories))

            saved_rollouts = json.loads(rollouts_output.read_text())
            self.assertEqual(len(saved_rollouts), len(trajectories))

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

    def test_single_task_csv_loader_parses_aki_dataset(self):
        csv_text = """trajectory_id,subject_id,hadm_id,stay_id,icu_intime,icu_outtime,icu_los_hours,aki_bucket,aki_stage1_start_time,aki_stage23_start_time,aki_stage1_start_hour,aki_stage23_start_hour,t_hour,checkpoint_time,state_label,terminal
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,stage23,2150-01-01T04:00:00,2150-01-01T08:00:00,4,8,0,2150-01-01T00:00:00,keep_monitoring,false
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,stage23,2150-01-01T04:00:00,2150-01-01T08:00:00,4,8,4,2150-01-01T04:00:00,suspect_aki,false
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "aki.csv"
            path.write_text(csv_text)
            result = load_single_task_csv_dataset(path, task_name="aki")
            trajectory = result.trajectories[0]
            self.assertEqual(trajectory.task_names, ["aki"])
            self.assertEqual(trajectory.tool_names, ["query_kdigo_stage"])
            self.assertEqual(trajectory.transitions["aki_stage23_start_hour"], 8)

    def test_single_task_csv_loader_parses_respiratory_dataset(self):
        csv_text = """trajectory_id,subject_id,hadm_id,stay_id,icu_intime,icu_outtime,icu_los_hours,resp_bucket,medium_support_start_time,invasive_start_time,medium_support_start_hour,invasive_support_start_hour,t_hour,checkpoint_time,state_label,terminal
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,high,2150-01-01T04:00:00,2150-01-01T08:00:00,4,8,0,2150-01-01T00:00:00,room_air_or_low_support,false
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,high,2150-01-01T04:00:00,2150-01-01T08:00:00,4,8,4,2150-01-01T04:00:00,high_flow_or_noninvasive_support,false
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "resp.csv"
            path.write_text(csv_text)
            result = load_single_task_csv_dataset(path, task_name="respiratory_support")
            trajectory = result.trajectories[0]
            self.assertEqual(trajectory.task_names, ["respiratory_support"])
            self.assertEqual(trajectory.tool_names, ["query_ventilation_status"])
            self.assertEqual(trajectory.transitions["invasive_support_start_hour"], 8)

    def test_load_dataset_auto_detects_infection_only_csv(self):
        csv_text = """trajectory_id,task_name,subject_id,hadm_id,stay_id,icu_intime,icu_outtime,icu_los_hours,infection_start_time,infection_start_hour,t_hour,checkpoint_time,state_label,terminal
mimiciv_stay_1,infection_only,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,2150-01-01T04:00:00,4,0,2150-01-01T00:00:00,keep_monitoring,false
mimiciv_stay_1,infection_only,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,2150-01-01T04:00:00,4,4,2150-01-01T04:00:00,infection_suspect,true
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rolling_infection_only.csv"
            path.write_text(csv_text)
            trajectories = load_dataset_auto(path)
            trajectory = trajectories[0]
            self.assertEqual(trajectory.task_name, "infection_only")
            self.assertEqual(trajectory.task_names, ["infection_only"])
            self.assertEqual(trajectory.tool_names, ["query_suspicion_of_infection"])
            self.assertEqual(trajectory.label_spaces["infection_only"], ["keep_monitoring", "infection_suspect"])
            self.assertEqual(trajectory.transitions["infection_start_hour"], 4)

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

    def test_single_task_aki_heuristic_run(self):
        class StubRuntime:
            def execute(self, tool_name, arguments):
                t = arguments["t_hour"]
                if tool_name == "query_kdigo_stage":
                    return {
                        "stay_id": 30,
                        "t_hour": t,
                        "latest_aki_stage_smoothed": 2 if t >= 8 else (1 if t >= 4 else 0),
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
            transitions={"aki_stage1_start_hour": 4, "aki_stage23_start_hour": 8},
            checkpoints=[
                Checkpoint(t_hour=0, state_label="keep_monitoring"),
                Checkpoint(t_hour=4, state_label="suspect_aki"),
                Checkpoint(t_hour=8, state_label="trigger_aki_alert"),
            ],
            task_name="aki",
            task_names=["aki"],
            tool_names=["query_kdigo_stage"],
            label_spaces={"aki": ["keep_monitoring", "suspect_aki", "trigger_aki_alert"]},
        )
        environment = BenchmarkEnvironment([trajectory], StubRuntime(), task_mode="single")
        rollout = environment.run_all(HeuristicAgent())[0]
        self.assertEqual(
            [step.predicted_action for step in rollout.steps],
            ["keep_monitoring", "suspect_aki", "trigger_aki_alert"],
        )
        metrics = evaluate_rollouts([trajectory], [rollout])
        self.assertEqual(metrics["task_name"], "aki")
        self.assertIn("aki_suspect", metrics["transition_timing"])
        self.assertIn("alert_predictions_grounded_rate", metrics["tool_grounding"])

    def test_single_task_infection_only_heuristic_run(self):
        class StubRuntime:
            def execute(self, tool_name, arguments):
                t = arguments["t_hour"]
                if tool_name == "query_suspicion_of_infection":
                    return {"stay_id": 30, "t_hour": t, "has_suspected_infection": t >= 4}
                raise ValueError(tool_name)

        trajectory = Trajectory(
            trajectory_id="mimiciv_stay_1",
            stay_id=30,
            subject_id=10,
            hadm_id=20,
            anchor="icu_intime",
            step_hours=4,
            horizon_hours=8,
            transitions={"infection_start_hour": 4},
            checkpoints=[
                Checkpoint(t_hour=0, state_label="keep_monitoring"),
                Checkpoint(t_hour=4, state_label="infection_suspect"),
                Checkpoint(t_hour=8, state_label="infection_suspect"),
            ],
            task_name="infection_only",
            task_names=["infection_only"],
            tool_names=["query_suspicion_of_infection"],
            label_spaces={"infection_only": ["keep_monitoring", "infection_suspect"]},
        )
        environment = BenchmarkEnvironment([trajectory], StubRuntime(), task_mode="single")
        rollout = environment.run_all(HeuristicAgent())[0]
        self.assertEqual(
            [step.predicted_action for step in rollout.steps],
            ["keep_monitoring", "infection_suspect", "infection_suspect"],
        )
        metrics = evaluate_rollouts([trajectory], [rollout])
        self.assertEqual(metrics["task_name"], "infection_only")
        self.assertIn("infection", metrics["transition_timing"])
        self.assertIn("infection_predictions_grounded_rate", metrics["tool_grounding"])

    def test_single_task_non_monotonic_aki_heuristic_run(self):
        class StubRuntime:
            def execute(self, tool_name, arguments):
                t = arguments["t_hour"]
                mapping = {0: 0, 4: 1, 8: 2, 12: 1}
                if tool_name == "query_kdigo_stage":
                    return {
                        "stay_id": 30,
                        "t_hour": t,
                        "latest_aki_stage_smoothed": mapping[t],
                    }
                raise ValueError(tool_name)

        trajectory = Trajectory(
            trajectory_id="mimiciv_stay_1",
            stay_id=30,
            subject_id=10,
            hadm_id=20,
            anchor="icu_intime",
            step_hours=4,
            horizon_hours=12,
            transitions={"path_family": "stage2_recovery_or_fluctuating", "path_0_24": "0>1>2>1"},
            checkpoints=[
                Checkpoint(t_hour=0, state_label="no_aki"),
                Checkpoint(t_hour=4, state_label="aki_stage_1"),
                Checkpoint(t_hour=8, state_label="aki_stage_2"),
                Checkpoint(t_hour=12, state_label="aki_stage_1"),
            ],
            task_name="aki",
            task_variant="non_monotonic_current_state",
            task_names=["aki"],
            tool_names=["query_kdigo_stage"],
            label_spaces={"aki": ["no_aki", "aki_stage_1", "aki_stage_2", "aki_stage_3"]},
        )
        environment = BenchmarkEnvironment([trajectory], StubRuntime(), task_mode="single")
        rollout = environment.run_all(HeuristicAgent())[0]
        self.assertEqual(
            [step.predicted_action for step in rollout.steps],
            ["no_aki", "aki_stage_1", "aki_stage_2", "aki_stage_1"],
        )
        metrics = evaluate_rollouts([trajectory], [rollout])
        self.assertEqual(metrics["task_variant"], "non_monotonic_current_state")
        self.assertIn("state_change", metrics)
        self.assertIn("stage2_predictions_grounded_rate", metrics["tool_grounding"])

    def test_single_task_non_monotonic_aki_prefers_explicit_state_label(self):
        class StubRuntime:
            def execute(self, tool_name, arguments):
                if tool_name == "query_kdigo_stage":
                    return {
                        "stay_id": 30,
                        "t_hour": arguments["t_hour"],
                        "latest_aki_stage": 0,
                        "latest_aki_stage_smoothed": 2,
                        "current_aki_state_label": "aki_stage_2",
                    }
                raise ValueError(tool_name)

        trajectory = Trajectory(
            trajectory_id="mimiciv_stay_1",
            stay_id=30,
            subject_id=10,
            hadm_id=20,
            anchor="icu_intime",
            step_hours=4,
            horizon_hours=0,
            transitions={"path_family": "stage2_progressive_or_persistent"},
            checkpoints=[Checkpoint(t_hour=0, state_label="aki_stage_2")],
            task_name="aki",
            task_variant="non_monotonic_current_state",
            task_names=["aki"],
            tool_names=["query_kdigo_stage"],
            label_spaces={"aki": ["no_aki", "aki_stage_1", "aki_stage_2", "aki_stage_3"]},
        )
        environment = BenchmarkEnvironment([trajectory], StubRuntime(), task_mode="single")
        rollout = environment.run_all(HeuristicAgent())[0]
        self.assertEqual(rollout.steps[0].predicted_action, "aki_stage_2")

    def test_load_single_task_non_monotonic_aki_csv(self):
        csv_text = """trajectory_id,subject_id,hadm_id,stay_id,icu_intime,icu_outtime,icu_los_hours,path_family,path_0_24,max_stage_24h,has_up_24h,has_down_24h,num_changes_24h,t_hour,checkpoint_time,current_aki_stage_smoothed,state_label,terminal
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,stage2_recovery_or_fluctuating,0>1>2>1,2,true,true,3,0,2150-01-01T00:00:00,0,no_aki,false
mimiciv_stay_1,10,20,30,2150-01-01T00:00:00,2150-01-02T00:00:00,24,stage2_recovery_or_fluctuating,0>1>2>1,2,true,true,3,4,2150-01-01T04:00:00,1,aki_stage_1,false
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rolling_aki_non_monotonic.csv"
            path.write_text(csv_text)
            result = load_single_task_csv_dataset(path, task_name="aki")
        self.assertEqual(result.included_trajectories, 1)
        trajectory = result.trajectories[0]
        self.assertEqual(trajectory.task_variant, "non_monotonic_current_state")
        self.assertEqual(trajectory.label_spaces["aki"], ["no_aki", "aki_stage_1", "aki_stage_2", "aki_stage_3"])

    def test_environment_rejects_task_mode_mismatch(self):
        concepts = load_concept_tables(SAMPLE)
        trajectory = build_dataset(concepts)[0]
        runtime = ConceptToolRuntime(concepts)
        environment = BenchmarkEnvironment([trajectory], runtime, task_mode="multitask")
        with self.assertRaises(ValueError):
            environment.run_all(HeuristicAgent())


if __name__ == "__main__":
    unittest.main()
