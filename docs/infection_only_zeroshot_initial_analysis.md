# Infection-Only Zero-Shot Initial Analysis

## Scope

This note summarizes the current infection-only zero-shot benchmark status for the longitudinal benchmark project.

It covers:

- the current completed SQL-based run for Qwen 3 4B
- the earlier Python-based zero-shot attempt
- the earlier Qwen 3.5 SQL trace
- pipeline and design observations, including leakage review
- bad-case matching against benchmark ground truth
- a brief dataset distribution summary

Primary artifacts reviewed:

- [Qwen3-4B-Instruct-2507 eval](/Users/chloe/Documents/New project/result/infection_only_zeroshot_qwen_python/Qwen3-4B-Instruct-2507/eval.json)
- [Qwen3-4B-Instruct-2507 events](/Users/chloe/Documents/New project/result/infection_only_zeroshot_qwen_python/Qwen3-4B-Instruct-2507/events.jsonl)
- [Qwen3-4B-Instruct-2507 rollouts](/Users/chloe/Documents/New project/result/infection_only_zeroshot_qwen_python/Qwen3-4B-Instruct-2507/rollouts.json)
- [Earlier Qwen3-4B Python trace](/Users/chloe/Documents/New project/result/infection_only_zeroshot_qwen_python/python_Qwen3-4B-Instruct-2507/events%20(2).jsonl)
- [Earlier Qwen3.5 SQL trace](/Users/chloe/Documents/New project/result/infection_only_zeroshot_qwen_python/Qwen3.5-9B/events%20(7).jsonl)
- [Infection-only dataset CSV](/Users/chloe/Documents/New project/rolling_monitor_dataset/infection_only/rolling_infection_only.csv)
- [Current infection-only guideline](/Users/chloe/Documents/New project/baseline/infection_only_guideline.yaml)

## Executive Summary

The current SQL-based infection-only zero-shot run is much more stable than the earlier Python-based and earlier Qwen 3.5 traces. The run completes, every step is grounded by a SQL tool call, and there are no SQL runtime errors in the finished 10-trajectory sample.

The remaining failures are mostly not parser failures or leakage failures. They are mostly semantic mismatches between:

- the raw zero-shot baseline query, which currently uses a very broad overlap rule over all visible `mimiciv_hosp.prescriptions` and all visible `mimiciv_hosp.microbiologyevents`
- the official benchmark labels, which come from the official MIMIC-style `suspicion_of_infection` concept and therefore reflect narrower row selection and concept-specific rules

The current state is therefore:

- pipeline stability: much better
- leakage risk in the observed run: not detected
- benchmark alignment of the raw SQL baseline: still imperfect

## Dataset Snapshot

From [rolling_infection_only.csv](/Users/chloe/Documents/New project/rolling_monitor_dataset/infection_only/rolling_infection_only.csv):

- `100` trajectories
- `700` total checkpoint rows
- `7` checkpoints per trajectory
- checkpoints at `0, 4, 8, 12, 16, 20, 24` hours
- `391` `keep_monitoring` rows
- `309` `infection_suspect` rows
- `47` trajectories become positive within the 24 hour benchmark horizon
- `53` trajectories remain negative within the 24 hour benchmark horizon

Important note: the dataset was intended as an approximately balanced infection-only benchmark slice, but the actual built file is not exactly `50/50` within the 24 hour horizon. In the materialized CSV, it is `47/53`.

For the completed Qwen 3 4B sample reviewed here:

- `10` trajectories total
- `4` positive trajectories within horizon
- `6` negative trajectories within horizon

## Why We Switched From Python To SQL

The earlier Python-based zero-shot path was too brittle for this task.

Observed in [events (2).jsonl](/Users/chloe/Documents/New project/result/infection_only_zeroshot_qwen_python/python_Qwen3-4B-Instruct-2507/events%20(2).jsonl):

- repeated `KeyError: 0` failures from pandas-style indexing assumptions
- one later `SyntaxError`
- long hand-written code trying to reconstruct antibiotics, routes, and cultures
- repeated attempts to manage dataframe objects and Python control flow instead of just querying the database

Why that happened:

- the model had to do schema interpretation, query construction, Python dataframe handling, and clinical temporal logic all at once
- it also started inventing engineering details like route filters and drug name patterns from memory
- even when the clinical idea was reasonable, the Python execution layer introduced many extra failure modes

SQL is a better fit for this infection-only raw baseline because the task is fundamentally:

- table lookup
- timestamp extraction
- pairwise overlap logic
- one-row decision output

In other words, infection-only is much closer to relational reasoning than to freeform Python synthesis.

## Why We Tightened The Guideline And Prompt

Detailed guidance matters more for zero-shot raw baselines than for tool-backed official baselines.

Without explicit guidance, the earlier traces showed the model drifting into:

- culture positivity requirements
- route heuristics
- ad hoc antibiotic name lists
- malformed SQL
- verbose reasoning instead of clean executable output

The revised infection-only guideline and prompt now explicitly anchor the model to:

- `mimiciv_hosp.prescriptions.starttime`
- `COALESCE(microbiologyevents.charttime, CAST(chartdate AS TIMESTAMP))`
- the asymmetric `24h / 72h` overlap rule
- the earlier-event suspicion time rule
- ignoring positivity, organism identity, susceptibilities, and SOFA

This guidance helped a lot with output shape control.

Evidence:

- in the current completed Qwen 3 4B run, all `70` tool calls use SQL
- there are `70` SQL calls and only `1` unique SQL query shape across the whole run
- there are no tool execution errors in the completed sample

That is a large improvement over both earlier paths.

## Earlier Qwen 3.5 SQL Trace

The available Qwen 3.5 artifact in the workspace is not a completed benchmark run. It is a partial trace in [events (7).jsonl](/Users/chloe/Documents/New project/result/infection_only_zeroshot_qwen_python/Qwen3.5-9B/events%20(7).jsonl).

Observed issues in that trace:

- verbose prose and reasoning before SQL
- repeated malformed SQL
- two `BinderException` failures from referencing `a.antibiotic_time` outside the `pairs` CTE
- additional `run_sql is read-only` errors caused by incomplete or malformed SQL fragments

So the Qwen 3.5 artifact is useful as a controller/prompt debugging trace, but it is not a scored benchmark result in the current workspace.

## Current Completed Qwen 3 4B SQL Run

From [eval.json](/Users/chloe/Documents/New project/result/infection_only_zeroshot_qwen_python/Qwen3-4B-Instruct-2507/eval.json):

- task: `infection_only`
- tool backend: `zeroshot_raw`
- sample size: `10`
- step accuracy: `0.6286`
- macro F1: `0.6282`
- infection transition exact match rate: `0.4`
- infection transition mean absolute error: `27.2` hours
- infection transition early rate: `0.5`
- infection transition late rate: `0.1`
- infection transition missed rate: `0.0`
- infection grounding rate: `1.0`

Operationally, this run is clean:

- `10` `trajectory_start`
- `10` `trajectory_complete`
- `70` `step_start`
- `70` `tool_call`
- `70` `tool_output`
- `70` `action`
- no tool errors

## Leakage Review

### What I checked

I looked for any evidence in the completed Qwen 3 4B run that the model accessed:

- `source.*`
- `mimiciv_derived.*`
- `information_schema`
- explicit `stay_id` or `hadm_id` filtering beyond the scoped views

In the observed event trace, none of those appeared.

### Current conclusion

No direct leakage was detected in this completed run.

Why:

- the model only queried `mimiciv_hosp.prescriptions` and `mimiciv_hosp.microbiologyevents`
- those are checkpoint-scoped views inside the runtime, already limited to the current admission and the current visibility window
- the runtime now blocks direct `source.*` access

### Important nuance

The model does not need to filter by stay or time itself in this setup. That is not leakage. That is the intended design of the checkpoint-scoped raw runtime.

Pre-ICU events from the same admission are also visible by design. That is not leakage either. It is part of the benchmark definition.

### Residual design issue

The main design gap is not leakage. It is concept mismatch:

- the raw SQL baseline currently uses a very broad overlap rule over visible prescriptions and microbiology rows
- the benchmark labels come from the official derived infection suspicion concept

That mismatch explains many of the remaining errors.

## Bad-Case Review

### Overall pattern

Out of the `10` sampled trajectories:

- exact per-trajectory match: `4`
- mismatched per-trajectory behavior: `6`

Correct cases:

- `mimiciv_stay_30380250`
- `mimiciv_stay_30524752`
- `mimiciv_stay_30571652`
- `mimiciv_stay_30640740`

Incorrect cases:

- `mimiciv_stay_30104258`
- `mimiciv_stay_30310155`
- `mimiciv_stay_30318909`
- `mimiciv_stay_30459440`
- `mimiciv_stay_30737111`
- `mimiciv_stay_30789431`

### Per-trajectory table

| Trajectory | GT first infection hour | Predicted first infection hour | Match | Likely explanation |
| --- | ---: | ---: | --- | --- |
| `mimiciv_stay_30104258` | `4` | `0` | No | Raw SQL finds an earlier visible overlap pair than the official benchmark concept. This looks like broad-row early firing. |
| `mimiciv_stay_30310155` | `0` | `12` | No | Raw SQL misses the official early pair and only finds a later pair. Most likely row-selection mismatch; visibility semantics may also contribute. |
| `mimiciv_stay_30318909` | `240` outside benchmark horizon | `4` | No | Raw SQL finds an early overlap pair, but the benchmark does not mark infection within the 24 hour horizon. Clear concept mismatch. |
| `mimiciv_stay_30459440` | `NULL` | `8` | No | False positive from broad raw overlap query. |
| `mimiciv_stay_30737111` | `NULL` | `8` | No | False positive from broad raw overlap query. |
| `mimiciv_stay_30789431` | `NULL` | `4` | No | False positive from broad raw overlap query. |

### Match against ground truth

For the finished Qwen 3 4B run, the rollouts do match the benchmark ground-truth labels structurally. The issue is not a labeling bug inside the rollout serializer. The issue is disagreement between:

- the model’s raw-query-based decision
- the benchmark’s official label sequence

Examples:

- `mimiciv_stay_30524752`: GT flips at `4`, model flips at `4`
- `mimiciv_stay_30640740`: GT positive from `0`, model positive from `0`
- `mimiciv_stay_30380250`: GT negative throughout, model negative throughout

So the rollout files look internally consistent.

### Why the bad cases happen

There are two main categories.

#### 1. Broad-row false positives

This is the dominant failure mode.

The current SQL query is:

- all visible prescriptions with non-null `starttime`
- all visible microbiology rows with non-null `charttime/chartdate`
- overlap window check

It does not apply the narrower row-selection logic that the official concept effectively represents.

This likely explains:

- `30104258`
- `30318909`
- `30459440`
- `30737111`
- `30789431`

#### 2. Raw/official mismatch on the earliest qualifying pair

`30310155` is the clearest example.

Benchmark label sequence:

- positive from `t=0`
- official infection start time: `2137-11-21 21:00:00`

Raw SQL sequence:

- negative through `t=8`
- positive from `t=12`
- first found pair anchored at `2137-11-22 02:00:00`

This means the raw SQL baseline is not reproducing the official earliest pair. The most likely reason is still concept mismatch in row selection. A secondary possible contributor is checkpoint visibility semantics, because the benchmark labels are snapped from the official suspicion time, which may be the earlier event in a pair.

I would treat that second explanation as an inference, not a confirmed root cause.

## Pipeline And Artifact Notes

There are two smaller engineering notes worth tracking.

### 1. Stale result directory naming

The completed run lives under:

- `result/infection_only_zeroshot_qwen_python/Qwen3-4B-Instruct-2507`

but the current run is SQL-based, not Python-based. The folder name is now stale and can easily confuse later result aggregation.

### 2. `NaT` serialization

Negative SQL results currently serialize missing timestamps as the string `"NaT"` rather than JSON `null` in the event trace. That does not break the current no-history run, but it could pollute future history-conditioned prompting.

## Interpretation

The current infection-only zero-shot work has made real progress.

What improved:

- moving from Python to SQL removed a large class of execution failures
- tightening the prompt/guideline reduced schema drift and output-shape drift
- the model now consistently emits executable SQL and grounded final actions

What still limits benchmark quality:

- the raw SQL baseline is still too broad relative to the official infection suspicion concept
- this creates early positives and occasional late positives even when there is no leakage

So the next issue is not “Can the model execute the pipeline?”  
The next issue is “How closely should the raw zero-shot baseline be allowed to approximate the official concept?”

## Recommended Next Step

For the next iteration, I would keep the SQL-based controller and prompt, but tighten the raw infection-only SQL semantics one step closer to the official concept.

That could mean one of two paths:

1. Keep the model-writing-SQL design, but provide a slightly more specific row-selection guideline.
2. Keep zero-shot decision-making, but expose a more structured raw infection helper query so the model does not need to reconstruct candidate row selection itself.

For benchmark fairness and stability, the second option is likely cleaner.
