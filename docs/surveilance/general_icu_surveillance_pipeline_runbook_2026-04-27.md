# General ICU Surveillance Pipeline Runbook

Date: 2026-04-27

## Purpose

This runbook describes the concrete runnable pipeline for the general ICU surveillance benchmark.

The goal is to stay faithful to the benchmark design:

- ground truth comes from MIMIC-derived SQL
- the agent discovers guideline files and autoformalized functions at runtime
- the benchmark does not add disease-specific helper scripts to improve agent performance

## Current Pipeline Shape

The runnable path is:

1. load the finalized surveillance benchmark CSV
2. convert each ICU stay into a rolling trajectory
3. open a checkpoint-scoped DuckDB Python session for each checkpoint
4. expose only lightweight retrieval helpers and `query_db`
5. let the agent decide whether to search guidelines, inspect functions, load functions, or query tables
6. collect one final structured surveillance decision at each checkpoint
7. call a separate summarizer LLM to write one short checkpoint summary
8. append that summary into rolling history
9. score predictions against the checkpoint ground truth

## Inputs

### Benchmark dataset

The main runnable dataset input is:

- [benchmark_2k_checkpoint_truth.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_checkpoint_truth.csv)

This file already contains:

- the finalized `2,000`-stay benchmark subset
- split assignment
- all rolling checkpoints
- family-level `suspected_conditions`
- family-level `alerts`
- `global_action`
- `priority`

### DuckDB database

The runtime DuckDB database is:

- `/Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db`

### Guideline retrieval corpus

The lightweight filename-based guideline corpus is:

- [guidelines/general_icu_autoformalized/txt](/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/txt)

It now includes:

- `general_icu_surveillance.txt`
- `infection.txt`
- `sepsis.txt`
- `aki.txt`
- `oliguria.txt`
- `respiratory_support.txt`
- `hemodynamic_shock.txt`
- `neurologic_deterioration.txt`
- `hyperlactatemia.txt`
- `acidemia.txt`
- `coagulopathy.txt`

### Autoformalized function library

The runtime function-discovery directory is:

- [autoformalized_library/functions](/Users/chloe/Documents/New project/autoformalized_library/functions)

The agent is expected to use:

- `search_functions(keyword)`
- `get_function_info(name)`
- `load_function(name)`

instead of receiving a benchmark-curated shortlist.

## Runtime Contract

The surveillance path uses the `zeroshot_python` backend with the `surveillance` session profile.

Important clarification:

- the runnable surveillance benchmark does **not** use the older structured `autoformalized` backend as the primary agent interface
- instead, it uses `zeroshot_python` as the execution backend
- within that session, the model discovers and loads files from [autoformalized_library/functions](/Users/chloe/Documents/New project/autoformalized_library/functions)
- so the model is still using the autoformalized function library, but indirectly through search and load rather than through pre-wrapped benchmark tools

That profile gives the agent:

- checkpoint-scoped visible tables
- guideline search helpers
- function search helpers
- `query_db(sql, params=None)`

The decision-model output contract per checkpoint is:

```json
{
  "global_action": "continue_monitoring | escalate",
  "suspected_conditions": ["..."],
  "alerts": ["..."],
  "priority": "low | medium | high",
  "recommended_next_tools": ["..."],
  "rationale": "..."
}
```

Then the separate summarizer call writes:

```json
{
  "checkpoint_summary": "..."
}
```

The decision prompt should only briefly define the semantics of `suspected_conditions` and `alerts`; detailed disease criteria should come from retrieved guideline text and discovered functions.

## Key Prompt Shape

### Decision step

The decision model sees:

- current `stay_id`
- current `t_hour`
- session helpers:
  - `search_guidelines`
  - `get_guideline`
  - `search_functions`
  - `get_function_info`
  - `load_function`
  - `query_db`
- the most recent rolling summaries only
- within-checkpoint code/query history for the current checkpoint only

The key system instructions are:

- this is rolling monitoring, not forecasting
- use only data visible by the current checkpoint
- monitor these families explicitly:
  - infection and sepsis
  - renal injury and urine-output failure, including CRRT when relevant
  - respiratory support escalation and hypoxemia
  - hemodynamic instability, vasoactive support, and shock
  - neurologic deterioration
  - metabolic failure, including lactate elevation and acidemia
  - coagulation abnormality
- discover guideline text and functions yourself
- prefer this tool order:
  - search guideline files for definitions
  - search function files for reusable logic
  - inspect and load relevant functions
  - use `query_db` when direct checkpoint evidence inspection is needed
- return either one short Python snippet or one final surveillance decision
- do not write the memory summary in the decision response

### Summary step

The summarizer sees:

- the current checkpoint metadata
- the final surveillance decision
- a compact digest of the current checkpoint tool/code history

The key system instructions are:

- write one very short checkpoint summary
- under 20 words when possible
- mention only the key active state or change
- return exactly `{"checkpoint_summary":"..."}` and nothing else

## End-to-End Example

### Round 1: checkpoint input

Example checkpoint:

- `stay_id = 30004144`
- `t_hour = 24`
- rolling history:
  - `index = 0, summary = t=0 stable; no active alerts`
  - `index = 1, summary = t=4 monitor infection; action=continue_monitoring`
  - `index = 2, summary = t=8 renal concern emerging`

The decision model receives only:

- this checkpoint context
- the retrieval helpers
- the last few summaries

It does not receive the full prior trajectory transcript.

### Round 1: decision exploration

Possible decision-step actions:

1. `search_guidelines("sepsis")`
2. `get_guideline("sepsis")`
3. `search_functions("sofa")`
4. `get_function_info("sofa")`
5. `search_functions("infection")`
6. `load_function("sofa")`
7. `load_function("suspicion_of_infection")`
8. `query_db(...)` or call loaded functions to inspect current evidence

### Round 1: decision output

Example final decision:

```json
{
  "global_action": "escalate",
  "suspected_conditions": ["infection", "sepsis"],
  "alerts": ["sepsis_alert"],
  "priority": "high",
  "recommended_next_tools": ["search_functions('vasoactive')", "search_functions('bg')"],
  "rationale": "Current evidence supports infection plus organ dysfunction consistent with sepsis."
}
```

### Round 1: separate summary output

Then the summarizer gets the final decision and writes:

```json
{
  "checkpoint_summary": "Sepsis alert at 24h; escalate for infection plus organ dysfunction."
}
```

That summary, and not the full checkpoint trace, is what gets appended to rolling memory.

### Round 2: next checkpoint

At `t_hour = 28`, the decision model sees:

- the same patient stay
- the new checkpoint visibility window
- the same retrieval helpers
- the recent summaries, now including:
  - `index = 3, summary = Sepsis alert at 24h; escalate for infection plus organ dysfunction.`

The session is fresh for `t=28`, but the memory state carries forward through summaries.

## Minimal Run Command

The intended CLI entry point is:

```bash
python -m src.sepsis_mvp.cli run \
  --dataset dataset/surveilance/benchmark_2k_checkpoint_truth.csv \
  --db-path "/Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db" \
  --tool-backend zeroshot_python \
  --task-mode surveillance \
  --protocol rolling_with_history \
  --agent qwen \
  --guidelines-dir guidelines/general_icu_autoformalized/txt \
  --functions-dir autoformalized_library/functions \
  --zeroshot-session-profile surveillance \
  --sample-size 10 \
  --trajectory-output outputs/surveilance/trajectory_rollouts.jsonl \
  --events-output outputs/surveilance/events.jsonl \
  --evaluation-output outputs/surveilance/eval.json
```

Notes:

- `rolling_with_history` is the intended protocol because the benchmark uses short checkpoint summaries as memory.
- `sample-size 10` is a good smoke-test setting before larger runs.
- the `qwen` agent requirement comes from the current zero-shot Python backend path.

## Implemented Evaluation

The current surveillance evaluator measures:

- `global_action_accuracy`
- `priority_accuracy`
- exact match on `suspected_conditions`
- exact match on `alerts`
- set-based macro F1 for suspected conditions
- set-based macro precision, recall, and F1 for alerts
- first-alert timing error
- false-early-alert trajectories
- missed-alert trajectories

## Known Limitations

The pipeline is runnable, but a few benchmark-realistic limitations remain:

- function retrieval is filename-based, not semantic
- guideline retrieval is filename-based, not content search
- some autoformalized files are safer to use compositionally than directly
  - `sepsis3.py` remains the clearest example
- `CRRT` is included in the latent decision layer, but its current reconstruction is weaker than the strongest core heads
- the current runnable path is centered on `zeroshot_python`; structured-tool surveillance backends are not the primary benchmark path

## Recommended Next Execution Order

1. run a small smoke test on `10` trajectories
2. inspect `events.jsonl` and `trajectory_rollouts.jsonl`
3. check whether the agent is actually using guideline and function discovery
4. then scale to the full dev set
5. keep the test split untouched for final benchmark runs
