from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent import HeuristicAgent, QwenChatAgent
from .dataset import (
    build_dataset,
    load_concept_tables,
    load_rolling_csv_dataset,
    load_trajectories,
    save_trajectories,
)
from .environment import BenchmarkEnvironment, evaluate_rollouts, rollout_to_dicts
from .tools import ConceptToolRuntime, DuckDBConceptToolRuntime


def build_dataset_command(args: argparse.Namespace) -> int:
    if args.rolling_csv:
        result = load_rolling_csv_dataset(args.rolling_csv, strict_mvp=not args.include_out_of_scope)
        trajectories = result.trajectories
        print(
            json.dumps(
                {
                    "included_trajectories": result.included_trajectories,
                    "skipped_trajectories": result.skipped_trajectories,
                    "skipped_reasons": result.skipped_reasons,
                },
                indent=2,
            )
        )
    else:
        if not args.concepts:
            raise SystemExit("build-dataset requires either --rolling-csv or --concepts")
        concept_tables = load_concept_tables(args.concepts)
        trajectories = build_dataset(
            concept_tables,
            step_hours=args.step_hours,
            horizon_hours=args.horizon_hours,
            sample_sepsis=args.sample_sepsis,
            sample_non_sepsis=args.sample_non_sepsis,
            seed=args.seed,
        )
    save_trajectories(trajectories, args.output)
    print(f"Wrote {len(trajectories)} trajectories to {args.output}")
    return 0


def run_command(args: argparse.Namespace) -> int:
    trajectories = load_trajectories(args.dataset)
    if args.db_path:
        runtime = DuckDBConceptToolRuntime(args.db_path)
    else:
        if not args.concepts:
            raise SystemExit("run requires either --db-path or --concepts")
        concept_tables = load_concept_tables(args.concepts)
        runtime = ConceptToolRuntime(concept_tables)
    environment = BenchmarkEnvironment(trajectories, runtime)
    if args.agent == "heuristic":
        agent = HeuristicAgent(sofa_alert_threshold=args.sofa_alert_threshold)
    else:
        agent = QwenChatAgent(
            model=args.model,
            temperature=args.temperature,
            top_p=args.top_p,
            max_new_tokens=args.max_new_tokens,
        )
    rollouts = environment.run_all(agent)
    evaluation = evaluate_rollouts(trajectories, rollouts)

    if args.rollouts_output:
        Path(args.rollouts_output).write_text(json.dumps(rollout_to_dicts(rollouts), indent=2))
    print(json.dumps(evaluation, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rolling sepsis surveillance MVP.")
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
    build_parser.add_argument("--seed", type=int, default=7)
    build_parser.set_defaults(func=build_dataset_command)

    run_parser = subparsers.add_parser("run", help="Run rollouts and evaluate the agent.")
    run_parser.add_argument("--concepts", help="Path to concept-table JSON.")
    run_parser.add_argument("--db-path", help="Path to MIMIC DuckDB for live concept-tool queries.")
    run_parser.add_argument("--dataset", required=True, help="Path to trajectory dataset JSON.")
    run_parser.add_argument("--agent", choices=["heuristic", "qwen"], default="heuristic")
    run_parser.add_argument("--model", default="Qwen/Qwen3.5-9B", help="Local HF model name/path for Qwen.")
    run_parser.add_argument("--temperature", type=float, default=0.0)
    run_parser.add_argument("--top-p", type=float, default=0.95)
    run_parser.add_argument("--max-new-tokens", type=int, default=250)
    run_parser.add_argument("--sofa-alert-threshold", type=int, default=2)
    run_parser.add_argument("--rollouts-output", help="Optional path to save rollout logs.")
    run_parser.set_defaults(func=run_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
