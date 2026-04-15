# Autoformalized Non-Monotonic AKI Handoff

## Purpose

This note packages the current non-monotonic AKI benchmark setup for the autoformalization owner.

It answers four questions:

1. What task is the agent actually solving?
2. What prompt/instruction does the agent receive?
3. Why does the official concept layer work while the autoformalized one fails?
4. Which concrete trajectory cases best illustrate the mismatch?

## Current Benchmark Task

Dataset:

- [/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/rolling_aki_non_monotonic.csv](/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/rolling_aki_non_monotonic.csv)

Task type:

- single-task AKI
- non-monotonic current-state tracking

Checkpoint grid:

- `t = 0, 4, 8, 12, 16, 20, 24`

Label space:

- `no_aki`
- `aki_stage_1`
- `aki_stage_2`
- `aki_stage_3`

Ground-truth source:

- official `mimiciv_derived.kdigo_stages`
- latest visible `aki_stage_smoothed` at each checkpoint

What the model must do:

- predict the **current visible AKI state**
- not the first AKI onset
- not the worst AKI seen so far

This means the model must support both:

- worsening
- recovery / de-escalation

## Agent Prompt Used For This Task

The prompt logic lives in:

- [/Users/chloe/Documents/New project/src/sepsis_mvp/agent.py](/Users/chloe/Documents/New project/src/sepsis_mvp/agent.py)

Relevant AKI non-monotonic guidance:

```text
Predict the current visible AKI state at this checkpoint rather than the first AKI onset.
Use current_aki_state_label from query_kdigo_stage as the primary benchmark-facing state field.
If current_aki_state_label is missing, then fall back to latest_aki_stage_smoothed.
Do not assume AKI states are permanent. If the visible stage decreases, de-escalate to the current lower stage.
Do not use latest_aki_stage when it conflicts with latest_aki_stage_smoothed.
Use the latest visible KDIGO stage summary for the checkpoint, not the historical maximum alone.
```

The tool description shown to the agent is:

```text
query_kdigo_stage: current visible AKI stage summary up to this checkpoint; for non-monotonic AKI, use current_aki_state_label as the primary decision field
```

So the agent side is now explicit:

- use the AKI tool
- read `current_aki_state_label`
- de-escalate when the current state drops

## What The Official Wrapper Returns

Official wrapper file:

- [/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py](/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py)

Official `query_kdigo_stage(stay_id, t_hour)` behavior:

- resolves `visible_until = icu_intime + t_hour`
- filters `mimiciv_derived.kdigo_stages` to `charttime <= visible_until`
- selects the **latest visible row**
- exposes:
  - `latest_aki_stage`
  - `latest_aki_stage_smoothed`
  - `current_aki_state_label`
  - `current_aki_state_stage`
  - component contributors

Important detail:

- `current_aki_state_label` is derived directly from the **latest visible `aki_stage_smoothed`**
- this matches the dataset’s hidden-state definition

In other words:

- official wrapper = time-gated access + row selection + JSON formatting
- the clinical logic still comes from the official MIMIC derived concept

## What The Autoformalized Wrapper Returns

Auto wrapper file:

- [/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py)

Generated function file:

- [/Users/chloe/Documents/New project/autoformalized_library/functions/kdigo_stages.py](/Users/chloe/Documents/New project/autoformalized_library/functions/kdigo_stages.py)

Autoformalized `query_kdigo_stage(stay_id, t_hour)` currently:

- runs the generated `kdigo_stages.py` inside a checkpoint-scoped raw-table database view
- gets one generated stay-prefix output dict
- maps `kdigo_stage` to:
  - `latest_aki_stage`
  - `latest_aki_stage_smoothed`
  - `current_aki_state_label`

That is the key issue:

- the wrapper calls the generated output “current state”
- but the generated function is **not** computing current state

## Why The Autoformalized KDIGO Logic Mismatches The Benchmark

The generated function in `kdigo_stages.py` does not mirror the official checkpoint-state concept.

It does three stay-prefix style operations:

### 1. Creatinine branch

`kdigo_creatinine(stay_id)`:

- finds a baseline creatinine
- scans all visible creatinine values in the prefix
- takes the **maximum ratio / maximum absolute increase**
- returns one prefix-level creatinine stage

### 2. Urine-output branch

`kdigo_uo(stay_id)`:

- reconstructs hourly urine output across the visible prefix
- finds the **longest consecutive run** below KDIGO thresholds
- returns one prefix-level urine-output stage

### 3. Final combination

`kdigo_stages(stay_id)`:

- returns `max(creatinine_stage, urine_output_stage)`

So the generated function is closer to:

- “worst KDIGO severity observed anywhere in the visible prefix so far”

not:

- “latest visible current AKI stage at this checkpoint”

That distinction is exactly why it struggles on non-monotonic AKI.

## Why This Problem Is Much Bigger For Non-Monotonic AKI

For a monotonic alert task, a worst-so-far signal may still be usable:

- once the patient crosses an AKI threshold, a sticky summary still supports first-alert detection

For the current-state non-monotonic task, this is the wrong target:

- stage can rise and fall
- recovery matters
- the latest visible checkpoint state matters more than the historical maximum

So the generated KDIGO function is not just a little noisy. It is solving a different task.

## Comparison On The Three Sample Trajectories

Below, “official” means the benchmark-aligned current-state concept and “auto” means the generated KDIGO function wrapped into the same JSON schema.

### Stay 30104258

Official current-state path:

- `0: aki_stage_1`
- `4: no_aki`
- `8: aki_stage_1`
- `12: aki_stage_1`
- `16: no_aki`
- `20: no_aki`
- `24: aki_stage_2`

Auto path:

- `0: no_aki`
- `4: no_aki`
- `8: no_aki`
- `12: no_aki`
- `16: no_aki`
- `20: aki_stage_1`
- `24: aki_stage_1`

Interpretation:

- misses early stage-1 activity
- turns positive late
- undercalls the final stage-2 severity

### Stay 30380250

Official current-state path:

- `0: aki_stage_1`
- `4: aki_stage_2`
- `8: no_aki`
- `12: no_aki`
- `16: no_aki`
- `20: no_aki`
- `24: no_aki`

Auto path:

- `0: no_aki`
- `4: no_aki`
- `8: aki_stage_1`
- `12: aki_stage_1`
- `16: aki_stage_2`
- `20: aki_stage_2`
- `24: aki_stage_2`

Interpretation:

- official shows early AKI followed by recovery
- auto shows delayed onset followed by persistent worsening
- this is the clearest example of the wrong task abstraction

This stay is especially helpful to discuss with the autoformalization owner because it contains a long true `no_aki` suffix that the generated function fails to recover to.

### Stay 30521718

Official current-state path:

- `0: no_aki`
- `4: no_aki`
- `8: no_aki`
- `12: no_aki`
- `16: aki_stage_2`
- `20: aki_stage_2`
- `24: aki_stage_1`

Auto path:

- `0: no_aki`
- `4: no_aki`
- `8: no_aki`
- `12: no_aki`
- `16: no_aki`
- `20: no_aki`
- `24: no_aki`

Interpretation:

- complete undercall of a later AKI event
- not just a recovery issue
- also a sensitivity / threshold issue

## “Non-AKI” Cases To Highlight

If the goal is to show where the generated concept is clinically misleading for a current-state monitor, the cleanest cases are:

### Recovery-to-no-AKI case

Stay `30380250`

Why it matters:

- official says the patient is `no_aki` from `t=8` onward
- auto keeps escalating after that point

This is the most useful “non-AKI case” because it shows false persistent AKI after recovery.

### Late undercall case

Stay `30521718`

Why it matters:

- official says stage 2 appears late and then de-escalates to stage 1
- auto stays `no_aki` throughout

This is useful because it shows that the generated function is not only sticky; it can also miss later events completely.

### Mixed fluctuation case

Stay `30104258`

Why it matters:

- official alternates between stage 1 and no AKI before ending at stage 2
- auto misses early fluctuation and only turns positive late

This is useful because it shows the generated concept is weak on both recovery and timing.

## What This Says About Sepsis

The same high-level issue already exists for sepsis SOFA.

Official SOFA wrapper:

- reads `mimiciv_derived.sofa`
- returns the latest visible hourly rolling row

Autoformalized SOFA:

- computes worst organ dysfunction values over the visible prefix
- wraps that as both `latest_sofa_24hours` and `max_sofa_24hours_so_far`

So the sepsis autoformalized concept also behaves more like:

- prefix worst burden so far

rather than:

- current hourly rolling state

This is more tolerable for a monotonic alert task than for a current-state stage-report task.

## Current Metrics Snapshot

Official heuristic smoke test on the non-monotonic AKI task:

- [/Users/chloe/Documents/New project/data/aki_non_monotonic_eval.json](/Users/chloe/Documents/New project/data/aki_non_monotonic_eval.json)
- step accuracy on the 3-stay smoke slice: `1.0`

Autoformalized heuristic smoke test:

- [/Users/chloe/Documents/New project/data/aki_non_monotonic_auto_eval.json](/Users/chloe/Documents/New project/data/aki_non_monotonic_auto_eval.json)
- step accuracy on the 1-stay smoke slice: `0.2857`

Your Qwen autoformalized run on 3 trajectories shows the same pattern:

- step accuracy: `0.2857`
- worsening F1: `0.0`
- recovery F1: `0.0`
- exact path match rate: `0.0`

This strongly suggests the problem is in the concept layer itself, not in the tool-use protocol.

## What The Autoformalization Owner Likely Needs To Know

The request is not “please make the function closer to official MIMIC semantics in every detail.”

The narrower request is:

- the benchmark now needs a **checkpoint-level current-state AKI concept**
- the generated function currently returns a **visible-prefix severity summary**
- that is acceptable for monotonic first-alert tasks, but not for non-monotonic state tracking

So the practical handoff question is:

### Can the generated AKI function be reformulated to output a current checkpoint state rather than a prefix-level max severity?

A better target for this benchmark would be something like:

- latest visible AKI stage at the checkpoint
- optionally with:
  - creatinine contributor
  - urine output contributor
  - CRRT contributor
  - age of latest evidence

## Suggested Deliverable For The Autoformalization Owner

If they are willing to revise the function, the ideal generated output for this task would be:

```json
{
  "current_aki_state_label": "aki_stage_1",
  "current_aki_state_stage": 1,
  "current_aki_state_time": "2118-10-24T17:00:00",
  "state_source": "latest_visible_checkpoint_state",
  "latest_components": {
    "aki_stage_creat": 0,
    "aki_stage_uo": 1,
    "aki_stage_crrt": 0
  },
  "max_aki_stage_so_far": 1
}
```

The key difference is:

- `current_aki_state_label` should come from the latest visible state logic
- `max_aki_stage_so_far` can still be included as a separate summary

## Bottom Line

The current non-monotonic AKI benchmark is working as designed.

The main blocker is not:

- agent prompting
- tool-calling
- JSON contract

The main blocker is:

- the autoformalized KDIGO function computes a prefix-level worst-severity concept
- while the benchmark requires a checkpoint-level current-state concept

That is why the same autoformalized concept can be tolerable in monotonic alert settings but fails badly in this 4-state current-report setting.
