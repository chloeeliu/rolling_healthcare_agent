# Rolling ICU Surveillance MVP

This repo contains a rolling monitoring benchmark pipeline on MIMIC-IV concept-layer data.

Implemented task modes:

- single-task sepsis escalation
- multi-task escalation for:
  - sepsis
  - AKI
  - respiratory support

The agent never sees raw vitals, labs, meds, or procedures directly. It only interacts with derived concept tools.

## Current datasets

Packaged datasets live under [/Users/chloe/Documents/New project/rolling_monitor_dataset](/Users/chloe/Documents/New project/rolling_monitor_dataset):

- [/Users/chloe/Documents/New project/rolling_monitor_dataset/sepsis](/Users/chloe/Documents/New project/rolling_monitor_dataset/sepsis)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/aki](/Users/chloe/Documents/New project/rolling_monitor_dataset/aki)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/respiratory_support](/Users/chloe/Documents/New project/rolling_monitor_dataset/respiratory_support)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask](/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask)

The main shared multi-task cohort is:

- [/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask/rolling_multitask.csv](/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask/rolling_multitask.csv)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask/trajectory_schema.json](/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask/trajectory_schema.json)

## Tool layer

The live DuckDB runtime queries these derived concepts:

- `query_suspicion_of_infection`
- `query_sofa`
- `query_kdigo_stage`
- `query_ventilation_status`

These are backed by:

- `mimiciv_derived.suspicion_of_infection`
- `mimiciv_derived.sofa`
- `mimiciv_derived.kdigo_stages`
- `mimiciv_derived.ventilation`

## Agent contract

Single-task sepsis mode returns:

```json
{"action":"infection_suspect"}
```

Multi-task mode returns:

```json
{
  "task_actions": {
    "sepsis": "infection_suspect",
    "aki": "suspect_aki",
    "respiratory_support": "room_air_or_low_support"
  }
}
```

Tool calls always use:

```json
{"tool_name":"query_kdigo_stage","arguments":{"stay_id":123,"t_hour":8}}
```

## Quick start

### 1. Build trajectories from a CSV package

Single-task sepsis:

```bash
PYTHONPATH=src python3 -m sepsis_mvp.cli build-dataset \
  --rolling-csv /Users/chloe/Documents/New\ project/rolling_monitor_dataset/sepsis/rolling_sepsis.csv \
  --output data/rolling_sepsis_trajectories.json
```

Shared multi-task:

```bash
PYTHONPATH=src python3 -m sepsis_mvp.cli build-dataset \
  --rolling-csv /Users/chloe/Documents/New\ project/rolling_monitor_dataset/multitask/rolling_multitask.csv \
  --output data/rolling_multitask_trajectories.json
```

### 2. Smoke test with the heuristic agent

This is the recommended pre-GPU check.

```bash
PYTHONPATH=src python3 -m sepsis_mvp.cli run \
  --db-path /Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db \
  --dataset /Users/chloe/Documents/New\ project/rolling_monitor_dataset/multitask/rolling_multitask.csv \
  --agent heuristic \
  --sample-size 5 \
  --events-output data/multitask_events.jsonl \
  --trajectory-output data/multitask_trajectories.jsonl \
  --rollouts-output data/multitask_rollouts.json
```

### 3. Run the local Qwen model

```bash
export QWEN_MODEL="Qwen/Qwen3.5-9B"
export QWEN_OFFLINE=0

PYTHONPATH=src python3 -m sepsis_mvp.cli run \
  --db-path /Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db \
  --dataset /Users/chloe/Documents/New\ project/rolling_monitor_dataset/multitask/rolling_multitask.csv \
  --agent qwen \
  --model Qwen/Qwen3.5-9B \
  --temperature 0.0 \
  --top-p 0.95 \
  --max-new-tokens 250 \
  --sample-size 10 \
  --events-output data/qwen_multitask_events.jsonl \
  --trajectory-output data/qwen_multitask_trajectories.jsonl \
  --rollouts-output data/qwen_multitask_rollouts.json
```

## Debug outputs

Useful flags:

- `--sample-size N`: run only the first `N` trajectories
- `--events-output path.jsonl`: append every step start, tool call, tool output, action, and trajectory completion
- `--events-output path.jsonl` also captures raw Qwen outputs, repair outputs, and any controller-forced tool corrections
- `--trajectory-output path.jsonl`: append each completed stay rollout immediately
- `--rollouts-output path.json`: write the final full in-memory rollout list at the end

This means partial progress survives long runs and crashes.

## Prompting notes

The local Qwen path is prompt-tuned for strict JSON output:

- no free-text reasoning
- no `<think>` tags
- fixed-key `task_actions` object in multitask mode
- one-shot repair retry if the first generation is not valid JSON
- deterministic tool-order guard in multitask mode:
  `query_suspicion_of_infection` -> `query_sofa` -> `query_kdigo_stage` -> `query_ventilation_status`
- if Qwen skips a required tool, repeats a previous tool, or keeps calling tools after all four are done, the controller repairs or corrects the step instead of silently falling back to baseline labels

## Query checks

Live query checks were run successfully against the DuckDB for:

- one stay positive for all three tasks: `30294009`
- one stay negative for all three tasks: `30009797`

Observed behavior matched expectations:

- pre-ICU infection can already be visible at `t_hour=0`
- SOFA, KDIGO, and ventilation are properly time-gated by checkpoint
- the respiratory wrapper reports both current and highest support seen so far

## Verification

Local verification completed with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

and a real DuckDB-backed multitask smoke run using the heuristic agent.
