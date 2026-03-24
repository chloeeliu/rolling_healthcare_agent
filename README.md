# Rolling Sepsis Surveillance MVP

This repo contains a minimal end-to-end benchmark pipeline for the design doc:

- offline trajectory loading/building
- time-gated concept-layer tools
- a rolling surveillance environment
- a local Qwen 3.5 agent adapter
- a heuristic smoke-test baseline and sample data

## What is implemented

The benchmark uses one ICU stay per trajectory and evaluates actions at fixed 4-hour checkpoints:

- `keep_monitoring`
- `infection_suspect`
- `trigger_sepsis_alert`

The agent can only call concept-layer tools:

- `query_suspicion_of_infection`
- `query_sofa`

Ground truth is built offline from:

- `suspicion_of_infection` for infection transition
- `sepsis3` for sepsis transition
- `sofa` for agent-visible evidence

## Input formats

The repo supports both:

- a prebuilt rolling checkpoint CSV, such as `/Users/chloe/Desktop/healthcare/dataset/rolling_sepsis/rolling_sepsis.csv`
- a concept-table JSON file for toy or synthetic experiments

The sample JSON format uses four top-level arrays:

```json
{
  "icustays": [],
  "suspicion_of_infection": [],
  "sepsis3": [],
  "sofa": []
}
```

Important fields:

- `icustays`: `stay_id`, `subject_id`, `hadm_id`, `icu_intime`
- `suspicion_of_infection`: `stay_id`, `suspected_infection_time`, plus optional evidence fields
- `sepsis3`: `stay_id`, `sepsis_time`
- `sofa`: `stay_id`, `hr`, `sofa_24hours`, optional component fields

## Quick start

Main path: build trajectories from the real rolling CSV:

```bash
PYTHONPATH=src python3 -m sepsis_mvp.cli build-dataset \
  --rolling-csv /Users/chloe/Desktop/healthcare/dataset/rolling_sepsis/rolling_sepsis.csv \
  --output data/rolling_sepsis_trajectories.json
```

By default, `build-dataset` stays strict to the 3-action MVP contract and drops out-of-scope trajectories such as rows with `organ_dysfunction_suspect`.

Run this once before evaluation:

```bash
PYTHONPATH=src python3 -m sepsis_mvp.cli build-dataset \
  --rolling-csv /Users/chloe/Desktop/healthcare/dataset/rolling_sepsis/rolling_sepsis.csv \
  --output data/rolling_sepsis_trajectories.json
```

Run the local Qwen model:

```bash
export QWEN_MODEL="Qwen/Qwen3.5-9B"
export QWEN_OFFLINE=0

PYTHONPATH=src python3 -m sepsis_mvp.cli run \
  --db-path /Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db \
  --dataset data/rolling_sepsis_trajectories.json \
  --agent qwen \
  --model Qwen/Qwen3.5-9B \
  --temperature 0.0 \
  --max-new-tokens 250 \
  --rollouts-output data/qwen_rollouts.json
```

Optional smoke test without loading the model:

```bash
PYTHONPATH=src python3 -m sepsis_mvp.cli run \
  --db-path /Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db \
  --dataset data/rolling_sepsis_trajectories.json \
  --agent heuristic
```

Or install the package once and then use the `sepsis-mvp` console command:

```bash
python3 -m pip install -e .
```

The local Qwen adapter expects the model to return either:

```json
{"tool_name":"query_sofa","arguments":{"stay_id":300001,"t_hour":12}}
```

or:

```json
{"action":"infection_suspect"}
```

## Notes

- The environment time-gates tool access using `icu_intime + t_hour`.
- `sepsis3` is never exposed to the agent.
- Transition labels are snapped to the first checkpoint at or after the hidden event time.
- Early SOFA hours are exposed as-is; no leakage beyond the current checkpoint is allowed.
- If your DuckDB already contains `mimiciv_derived.sofa` and `mimiciv_derived.suspicion_of_infection`, the runtime queries those directly.
- `--agent qwen` is the real experiment path.
- `--agent heuristic` is only there for fast CPU-only smoke tests and regression checks.
