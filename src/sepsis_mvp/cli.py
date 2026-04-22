from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .agent import HeuristicAgent, QwenChatAgent
from .dataset import (
    build_dataset,
    load_dataset_auto,
    save_trajectories,
)
from .environment import BenchmarkEnvironment, evaluate_rollouts, rollout_to_dicts
from .schemas import StepRecord, TrajectoryRollout
from .tools import build_tool_runtime


def _json_default(value):
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


class JsonlSink:
    def __init__(self, path: str | None):
        self.path = Path(path) if path else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, payload: dict) -> None:
        if self.path is None:
            return
        with self.path.open("a") as handle:
            handle.write(json.dumps(payload, default=_json_default) + "\n")
            handle.flush()


def _normalize_tool_backend(tool_backend: str) -> str:
    if tool_backend == "zeroshot_raw":
        print(
            "Warning: --tool-backend zeroshot_raw is deprecated and now maps to zeroshot_sql.",
            flush=True,
        )
        return "zeroshot_sql"
    return tool_backend


def _default_guideline_path_for_run(*, task_name: str, tool_backend: str) -> str | None:
    if tool_backend not in {"zeroshot_python", "zeroshot_sql", "zeroshot_raw"}:
        return None
    if task_name == "infection_only":
        return "baseline/infection_only_raw_tables_guideline.yaml"
    if task_name == "sepsis":
        return "baseline/sepsis_raw_tables_guideline.yaml"
    return None


def _rollout_from_dict(payload: dict) -> TrajectoryRollout:
    return TrajectoryRollout(
        trajectory_id=payload["trajectory_id"],
        stay_id=int(payload["stay_id"]),
        steps=[StepRecord(**step) for step in payload["steps"]],
        first_predicted_infection_hour=payload.get("first_predicted_infection_hour"),
        first_predicted_alert_hour=payload.get("first_predicted_alert_hour"),
        first_predicted_task_hours=payload.get("first_predicted_task_hours"),
    )


def _load_jsonl_dicts(path: Path) -> list[dict]:
    payloads = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                payloads.append(json.loads(line))
    return payloads


def _write_canonical_trajectory_output(
    trajectory_output: str | None,
    rollouts: list[TrajectoryRollout],
) -> None:
    if not trajectory_output:
        return
    path = Path(trajectory_output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_lines = [
        json.dumps(rollout.to_dict(), default=_json_default)
        for rollout in rollouts
    ]
    path.write_text("".join(f"{line}\n" for line in payload_lines))


def _load_existing_rollouts(
    trajectory_output: str | None,
    rollouts_output: str | None,
) -> tuple[list[TrajectoryRollout], list[str]]:
    existing_by_id: dict[str, TrajectoryRollout] = {}
    sources: list[str] = []

    if trajectory_output:
        trajectory_path = Path(trajectory_output)
        if trajectory_path.exists():
            for payload in _load_jsonl_dicts(trajectory_path):
                rollout = _rollout_from_dict(payload)
                existing_by_id[rollout.trajectory_id] = rollout
            sources.append(str(trajectory_path))

    if rollouts_output:
        rollouts_path = Path(rollouts_output)
        if rollouts_path.exists():
            raw = json.loads(rollouts_path.read_text())
            if not isinstance(raw, list):
                raise ValueError(f"Expected a JSON list in {rollouts_path}")
            for payload in raw:
                rollout = _rollout_from_dict(payload)
                existing_by_id.setdefault(rollout.trajectory_id, rollout)
            sources.append(str(rollouts_path))

    return list(existing_by_id.values()), sources


def build_dataset_command(args: argparse.Namespace) -> int:
    if args.rolling_csv:
        trajectories = load_dataset_auto(args.rolling_csv, strict_mvp=not args.include_out_of_scope)
        print(json.dumps({"included_trajectories": len(trajectories)}, indent=2))
    else:
        if not args.concepts:
            raise SystemExit("build-dataset requires either --rolling-csv or --concepts")
        from .dataset import load_concept_tables

        concept_tables = load_concept_tables(args.concepts)
        trajectories = build_dataset(
            concept_tables,
            step_hours=args.step_hours,
            horizon_hours=args.horizon_hours,
            sample_sepsis=args.sample_sepsis,
            sample_non_sepsis=args.sample_non_sepsis,
            seed=args.seed,
        )
    if args.sample_size is not None:
        trajectories = trajectories[: args.sample_size]
    save_trajectories(trajectories, args.output)
    print(f"Wrote {len(trajectories)} trajectories to {args.output}")
    return 0


def run_command(args: argparse.Namespace) -> int:
    args.tool_backend = _normalize_tool_backend(args.tool_backend)
    trajectories = load_dataset_auto(args.dataset, strict_mvp=not args.include_out_of_scope)
    if args.sample_size is not None:
        trajectories = trajectories[: args.sample_size]
    all_target_trajectories = list(trajectories)

    if args.tool_backend == "zeroshot_python":
        if args.agent != "qwen":
            raise SystemExit("Zero-shot python backend currently requires --agent qwen.")
        unsupported = [
            trajectory.trajectory_id
            for trajectory in all_target_trajectories
            if trajectory.is_multitask() or trajectory.primary_task_name() != "sepsis"
        ]
        if unsupported:
            raise SystemExit(
                "Zero-shot python backend currently supports only the single-task sepsis dataset. "
                f"First unsupported trajectories: {unsupported[:5]}"
            )

    if args.tool_backend == "zeroshot_sql":
        if args.agent != "qwen":
            raise SystemExit("Zero-shot SQL backend currently requires --agent qwen.")
        unsupported = [
            trajectory.trajectory_id
            for trajectory in all_target_trajectories
            if trajectory.is_multitask() or trajectory.primary_task_name() not in {"sepsis", "infection_only"}
        ]
        if unsupported:
            raise SystemExit(
                "Zero-shot SQL backend currently supports only the single-task sepsis or infection-only dataset. "
                f"First unsupported trajectories: {unsupported[:5]}"
            )

    existing_rollouts: list[TrajectoryRollout] = []
    existing_ids: set[str] = set()
    resume_sources: list[str] = []
    if args.resume:
        if not args.trajectory_output and not args.rollouts_output:
            raise SystemExit(
                "--resume requires at least one existing output source: --trajectory-output or --rollouts-output"
            )
        existing_rollouts, resume_sources = _load_existing_rollouts(
            args.trajectory_output,
            args.rollouts_output,
        )
        dataset_ids = {trajectory.trajectory_id for trajectory in all_target_trajectories}
        existing_rollouts = [rollout for rollout in existing_rollouts if rollout.trajectory_id in dataset_ids]
        existing_ids = {rollout.trajectory_id for rollout in existing_rollouts}
        trajectories = [
            trajectory for trajectory in all_target_trajectories if trajectory.trajectory_id not in existing_ids
        ]
    else:
        trajectories = all_target_trajectories

    rollouts = list(existing_rollouts)
    total_target = len(all_target_trajectories)
    newly_processed = 0

    if args.resume:
        print(
            f"Resume enabled: found {len(existing_rollouts)} completed trajectories from "
            + (", ".join(resume_sources) if resume_sources else "no existing files"),
            flush=True,
        )
        print(
            f"Skipping {len(existing_rollouts)} existing trajectories; {len(trajectories)} remaining",
            flush=True,
        )

    runtime = None
    environment = None
    agent = None
    if trajectories:
        runtime = build_tool_runtime(
            tool_backend=args.tool_backend,
            db_path=args.db_path,
            concepts=args.concepts,
            autoformalized_library=args.autoformalized_library,
        )

        events_sink = JsonlSink(args.events_output)
        trajectories_sink = JsonlSink(args.trajectory_output)
        environment = BenchmarkEnvironment(
            trajectories,
            runtime,
            event_callback=events_sink.write,
            tool_backend=args.tool_backend,
            task_mode=args.task_mode,
            protocol=args.protocol,
        )
        if args.agent == "heuristic":
            agent = HeuristicAgent(sofa_alert_threshold=args.sofa_alert_threshold)
        else:
            zeroshot_guideline_path = getattr(args, "zeroshot_guideline", None)
            if not zeroshot_guideline_path:
                zeroshot_guideline_path = _default_guideline_path_for_run(
                    task_name=trajectories[0].primary_task_name(),
                    tool_backend=args.tool_backend,
                )
            agent = QwenChatAgent(
                model=args.model,
                temperature=args.temperature,
                top_p=args.top_p,
                max_new_tokens=args.max_new_tokens,
                repair_max_new_tokens=args.repair_max_new_tokens,
                zeroshot_guideline_path=zeroshot_guideline_path,
                trace_callback=events_sink.write,
            )

        start_time = time.time()
        print(f"Starting run on {len(trajectories)} remaining trajectories", flush=True)
        for index, trajectory in enumerate(trajectories, start=1):
            processed_index = len(existing_rollouts) + index
            print(
                f"[{processed_index}/{total_target}] stay_id={trajectory.stay_id} "
                f"trajectory_id={trajectory.trajectory_id} task_mode={args.task_mode} "
                f"tool_backend={args.tool_backend} start",
                flush=True,
            )
            rollout = environment.run_trajectory(trajectory, agent)
            rollouts.append(rollout)
            trajectories_sink.write(rollout.to_dict())
            newly_processed += 1
            elapsed = time.time() - start_time
            if trajectory.is_multitask():
                print(
                    f"[{processed_index}/{total_target}] stay_id={trajectory.stay_id} done "
                    f"task_firsts={rollout.first_predicted_task_hours} "
                    f"elapsed_sec={elapsed:.1f}",
                    flush=True,
                )
            else:
                print(
                    f"[{processed_index}/{total_target}] stay_id={trajectory.stay_id} done "
                    f"first_infection={rollout.first_predicted_infection_hour} "
                    f"first_alert={rollout.first_predicted_alert_hour} "
                    f"elapsed_sec={elapsed:.1f}",
                    flush=True,
                )
    else:
        print("No remaining trajectories to process; using existing completed rollouts only", flush=True)

    if len(rollouts) != total_target:
        missing = sorted(
            trajectory.trajectory_id
            for trajectory in all_target_trajectories
            if trajectory.trajectory_id not in {rollout.trajectory_id for rollout in rollouts}
        )
        raise SystemExit(
            "Resume/evaluation mismatch: missing completed rollouts for "
            f"{len(missing)} trajectories. First missing IDs: {missing[:5]}"
        )

    evaluation = evaluate_rollouts(all_target_trajectories, rollouts, protocol=args.protocol)
    evaluation_summary = {
        "task_mode": args.task_mode,
        "protocol": args.protocol,
        "tool_backend": args.tool_backend,
        "dataset": args.dataset,
        "num_trajectories": total_target,
        "sample_size": args.sample_size,
        "agent": args.agent,
        "resume": args.resume,
        "existing_completed_trajectories": len(existing_rollouts),
        "newly_processed_trajectories": newly_processed,
        "metrics": evaluation,
    }

    if args.rollouts_output:
        Path(args.rollouts_output).write_text(json.dumps(rollout_to_dicts(rollouts), indent=2, default=_json_default))
    _write_canonical_trajectory_output(args.trajectory_output, rollouts)
    if args.evaluation_output:
        Path(args.evaluation_output).write_text(json.dumps(evaluation_summary, indent=2, default=_json_default))
    print(json.dumps(evaluation_summary, indent=2, default=_json_default))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rolling ICU surveillance benchmark pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-dataset", help="Build trajectory dataset from concept tables.")
    build_parser.add_argument("--concepts", help="Path to concept-table JSON.")
    build_parser.add_argument("--rolling-csv", help="Path to prebuilt rolling_sepsis.csv.")
    build_parser.add_argument("--output", required=True, help="Path to write trajectories JSON.")
    build_parser.add_argument(
        "--include-out-of-scope",
        action="store_true",
        help="Keep trajectories that fall outside the strict 3-action MVP contract.",
    )
    build_parser.add_argument("--step-hours", type=int, default=4)
    build_parser.add_argument("--horizon-hours", type=int, default=24)
    build_parser.add_argument("--sample-sepsis", type=int)
    build_parser.add_argument("--sample-non-sepsis", type=int)
    build_parser.add_argument("--sample-size", type=int, help="Keep only the first N trajectories.")
    build_parser.add_argument("--seed", type=int, default=7)
    build_parser.set_defaults(func=build_dataset_command)

    run_parser = subparsers.add_parser("run", help="Run rollouts and evaluate the agent.")
    run_parser.add_argument("--concepts", help="Path to concept-table JSON.")
    run_parser.add_argument("--db-path", help="Path to MIMIC DuckDB for live concept-tool queries.")
    run_parser.add_argument("--dataset", required=True, help="Path to trajectory dataset JSON.")
    run_parser.add_argument(
        "--task-mode",
        choices=["auto", "single", "multitask"],
        default="auto",
        help="Validate the dataset against a requested task mode, or infer automatically.",
    )
    run_parser.add_argument(
        "--tool-backend",
        choices=["official", "autoformalized", "zeroshot_python", "zeroshot_sql", "zeroshot_raw"],
        default="official",
        help=(
            "Choose whether visible tool outputs come from official derived concepts, generated functions, "
            "the new zero-shot Python session backend, or the legacy zero-shot SQL/raw backend."
        ),
    )
    run_parser.add_argument(
        "--protocol",
        choices=["rolling_no_history", "rolling_with_history", "rolling_toolbox_with_history"],
        default="rolling_no_history",
        help=(
            "Choose whether each checkpoint sees only current-step tool outputs, compact summaries from prior checkpoints, "
            "or the sepsis toolbox-with-history controller."
        ),
    )
    run_parser.add_argument(
        "--autoformalized-library",
        default="autoformalized_library",
        help="Path to the autoformalized function library root when using --tool-backend autoformalized.",
    )
    run_parser.add_argument(
        "--zeroshot-guideline",
        default=None,
        help="Optional path to the zero-shot guidance YAML. If omitted, a task-specific default is chosen.",
    )
    run_parser.add_argument(
        "--include-out-of-scope",
        action="store_true",
        help="Keep trajectories that fall outside the strict 3-action MVP contract when using CSV input.",
    )
    run_parser.add_argument("--agent", choices=["heuristic", "qwen"], default="heuristic")
    run_parser.add_argument("--model", default="Qwen/Qwen3.5-9B", help="Local HF model name/path for Qwen.")
    run_parser.add_argument("--temperature", type=float, default=0.0)
    run_parser.add_argument("--top-p", type=float, default=0.95)
    run_parser.add_argument("--max-new-tokens", type=int, default=250)
    run_parser.add_argument(
        "--repair-max-new-tokens",
        type=int,
        help="Optional override for repair generations. Defaults to an adaptive value based on --max-new-tokens.",
    )
    run_parser.add_argument("--sample-size", type=int, help="Run only the first N trajectories.")
    run_parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip trajectories already present in --trajectory-output or --rollouts-output and resume from the next unfinished trajectory.",
    )
    run_parser.add_argument("--sofa-alert-threshold", type=int, default=2)
    run_parser.add_argument("--rollouts-output", help="Optional path to save rollout logs.")
    run_parser.add_argument(
        "--evaluation-output",
        help="Optional path to save the final evaluation summary JSON.",
    )
    run_parser.add_argument("--events-output", help="Optional JSONL file for per-tool-call/per-step events.")
    run_parser.add_argument("--trajectory-output", help="Optional JSONL file for per-stay completed rollouts.")
    run_parser.set_defaults(func=run_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
