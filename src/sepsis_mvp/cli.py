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
from .tools import build_tool_runtime


class JsonlSink:
    def __init__(self, path: str | None):
        self.path = Path(path) if path else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, payload: dict) -> None:
        if self.path is None:
            return
        with self.path.open("a") as handle:
            handle.write(json.dumps(payload) + "\n")
            handle.flush()


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
    trajectories = load_dataset_auto(args.dataset, strict_mvp=not args.include_out_of_scope)
    if args.sample_size is not None:
        trajectories = trajectories[: args.sample_size]
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
    )
    if args.agent == "heuristic":
        agent = HeuristicAgent(sofa_alert_threshold=args.sofa_alert_threshold)
    else:
        agent = QwenChatAgent(
            model=args.model,
            temperature=args.temperature,
            top_p=args.top_p,
            max_new_tokens=args.max_new_tokens,
            trace_callback=events_sink.write,
        )

    total = len(trajectories)
    rollouts = []
    start_time = time.time()
    print(f"Starting run on {total} trajectories", flush=True)
    for index, trajectory in enumerate(trajectories, start=1):
        print(
            f"[{index}/{total}] stay_id={trajectory.stay_id} trajectory_id={trajectory.trajectory_id} "
            f"task_mode={args.task_mode} tool_backend={args.tool_backend} start",
            flush=True,
        )
        rollout = environment.run_trajectory(trajectory, agent)
        rollouts.append(rollout)
        trajectories_sink.write(rollout.to_dict())
        elapsed = time.time() - start_time
        if trajectory.is_multitask():
            print(
                f"[{index}/{total}] stay_id={trajectory.stay_id} done "
                f"task_firsts={rollout.first_predicted_task_hours} "
                f"elapsed_sec={elapsed:.1f}",
                flush=True,
            )
        else:
            print(
                f"[{index}/{total}] stay_id={trajectory.stay_id} done "
                f"first_infection={rollout.first_predicted_infection_hour} "
                f"first_alert={rollout.first_predicted_alert_hour} "
                f"elapsed_sec={elapsed:.1f}",
                flush=True,
            )

    evaluation = evaluate_rollouts(trajectories, rollouts)
    evaluation_summary = {
        "task_mode": args.task_mode,
        "tool_backend": args.tool_backend,
        "dataset": args.dataset,
        "num_trajectories": len(trajectories),
        "sample_size": args.sample_size,
        "agent": args.agent,
        "metrics": evaluation,
    }

    if args.rollouts_output:
        Path(args.rollouts_output).write_text(json.dumps(rollout_to_dicts(rollouts), indent=2))
    if args.evaluation_output:
        Path(args.evaluation_output).write_text(json.dumps(evaluation_summary, indent=2))
    print(json.dumps(evaluation_summary, indent=2))
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
        choices=["official", "autoformalized"],
        default="official",
        help="Choose whether visible tool outputs come from official derived concepts or generated functions.",
    )
    run_parser.add_argument(
        "--autoformalized-library",
        default="autoformalized_library",
        help="Path to the autoformalized function library root when using --tool-backend autoformalized.",
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
    run_parser.add_argument("--sample-size", type=int, help="Run only the first N trajectories.")
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
