# Autoformalized Longitudinal Pipeline

This note summarizes the current generalized pipeline after adding support for:

- single-task and multitask longitudinal monitoring
- official and autoformalized visible tool backends

## Main axes

The runner now has two explicit configuration axes:

- `task_mode`
  - `auto`
  - `single`
  - `multitask`
- `tool_backend`
  - `official`
  - `autoformalized`

These are orthogonal:

- `task_mode` controls prompt/controller behavior and dataset validation
- `tool_backend` controls how concept-layer tool outputs are produced

`single` does not select a task automatically. The single task comes from the dataset:

- sepsis CSV -> single-task sepsis
- AKI CSV -> single-task AKI
- respiratory support CSV -> single-task respiratory support

## Current execution model

The benchmark loop is still unchanged at a high level:

1. load trajectories
2. step through checkpoints
3. allow tool calls
4. capture final action(s)
5. evaluate against fixed labels

What changed is the way tasks and tools are resolved.

## Task resolution

Task metadata is now centralized in [schemas.py](/Users/chloe/Documents/New project/src/sepsis_mvp/schemas.py):

- label spaces
- task-specific tool lists
- baseline actions
- transition fields for timing evaluation

This allows:

- single-task sepsis
- single-task AKI
- single-task respiratory support
- multitask sepsis + AKI + respiratory support

without rewriting the environment or the Qwen agent.

## Tool backends

### Official backend

The official backend in [tools.py](/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py) uses:

- `mimiciv_derived.suspicion_of_infection`
- `mimiciv_derived.sofa`
- `mimiciv_derived.kdigo_stages`
- `mimiciv_derived.ventilation`

and returns compact benchmark-native JSON.

### Autoformalized backend

The autoformalized backend in [autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py) loads generated functions from:

- [/Users/chloe/Documents/New project/autoformalized_library/functions](/Users/chloe/Documents/New project/autoformalized_library/functions)

The backend:

1. loads `FINAL_FUNCTION` from the generated module
2. creates a checkpoint-scoped DuckDB context
3. injects `query_db(sql)` into the generated function namespace
4. runs the generated function using `stay_id`
5. adapts the returned dict into the benchmark tool schema

## Checkpoint scoping for generated functions

Generated functions are stay-level concept extractors, not rolling tool wrappers.

To make them usable for longitudinal monitoring, the runtime creates temporary filtered views:

- ICU stay is truncated at `visible_until`
- ICU event tables are filtered to the target stay and checkpoint
- hospital tables are filtered to the target subject/admission and checkpoint
- subject-level labs keep earlier history needed by functions like KDIGO baseline creatinine

This lets the generated function run against a prefix of the patient record instead of the full future stay.

## Prompt/controller changes

The Qwen controller in [agent.py](/Users/chloe/Documents/New project/src/sepsis_mvp/agent.py) now:

- builds separate single-task and multitask prompts
- derives required tool order from the monitored task set
- tracks `tool_backend` in step input for traceability
- forces the next required tool if the model skips tool use
- repairs invalid JSON outputs

Single-task mode is no longer hardcoded to sepsis.

## Evaluation changes

Single-task evaluation is now generic:

- step accuracy
- macro F1
- per-class metrics
- task-specific transition timing
- non-baseline grounding rate

Multitask evaluation remains joint step accuracy plus per-task metrics.

## Current verification status

Verified locally:

- unit tests pass
- compile checks pass
- CLI smoke test passes on the official single-task path
- CLI smoke tests also pass for:
  - official multitask
  - autoformalized single-task sepsis
  - autoformalized single-task AKI
  - autoformalized single-task respiratory support
  - autoformalized multitask

Not fully verified in this local environment:

- live execution of the autoformalized backend, because the local Python environment here does not include the `duckdb` and `pandas` packages required by generated functions

## Recommended next check

On the GPU/runtime machine, run:

1. heuristic + official backend
2. heuristic + autoformalized backend
3. Qwen + official backend
4. Qwen + autoformalized backend

with `--sample-size 3`, `--events-output`, and `--evaluation-output` enabled.
