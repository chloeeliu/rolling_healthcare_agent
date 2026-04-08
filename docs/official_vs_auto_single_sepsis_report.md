# Official vs Autoformalized Single-Sepsis Report

## Scope

This report compares two saved single-task sepsis runs under [/Users/chloe/Documents/New project/result](/Users/chloe/Documents/New%20project/result):

- official visible concepts: [/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507](/Users/chloe/Documents/New%20project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507)
- autoformalized visible concepts: [/Users/chloe/Documents/New project/result/auto_single_sepsis_Qwen3-30B-A3B-Instruct-2507](/Users/chloe/Documents/New%20project/result/auto_single_sepsis_Qwen3-30B-A3B-Instruct-2507)

Both runs use the same model family, `Qwen3-30B-A3B-Instruct-2507`.

This version supersedes the earlier partial-run comparison. The updated auto result folder now contains a full run, so this is a true matched-cohort A/B:

- official trajectories: `98`
- auto trajectories: `98`
- overlap: `98`

One caveat remains: this saved 98-stay result cohort appears to predate the latest revised sepsis CSV currently in the repo, so this report is intentionally centered on the saved run artifacts themselves.

## Executive Summary

The official backend remains the stronger benchmark-facing baseline for single-task sepsis surveillance.

Its strengths are:

- higher step accuracy: `0.8003` vs `0.6589`
- stronger macro F1: `0.6152` vs `0.5463`
- cleaner early infection visibility
- more stable, internally coherent tool outputs

The autoformalized backend is still scientifically valuable, but the refreshed full run makes its current weaknesses much clearer:

- it suppresses early infection visibility much more aggressively
- it delays infection transitions in many trajectories
- it still produces many steps where infection evidence exists while the boolean infection flag remains false
- it uses `infection_suspect` more often than the official backend, but not enough to offset the evidence-quality gap

The practical read is:

- official backend is the better current baseline
- autoformalized backend is a meaningful alternative visible concept layer, but still not robust enough to replace the official one for sepsis

## Comparison Setup

### Artifact completeness

Official folder:

- `qwen_events.jsonl`
- `qwen_rollouts.json`
- `qwen_trajectories.jsonl`

Autoformalized folder:

- `auto_qwen_multitask_events.jsonl`
- `auto_qwen_multitask_rollouts.json`
- `auto_qwen_multitask_trajectories.jsonl`
- `auto_qwen_multitask_qwen_eval.json`

The auto filenames still say `multitask`, but the contents are single-task sepsis trajectories.

Both event logs are now complete.

Official event counts:

- `trajectory_start`: `98`
- `step_start`: `686`
- `tool_call`: `1372`
- `tool_output`: `1372`
- `action`: `686`
- `trajectory_complete`: `98`

Autoformalized event counts:

- `trajectory_start`: `98`
- `step_start`: `686`
- `model_output_raw`: `2058`
- `tool_call`: `1372`
- `tool_output`: `1372`
- `action`: `686`
- `trajectory_complete`: `98`

Both runs are fully tool-grounded. The difference is not that one run failed to call tools. The difference is the evidence returned by those tools.

## Function Logic Comparison

This is the core difference between the two systems.

### Official backend

The official runtime in [/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py](/Users/chloe/Documents/New%20project/src/sepsis_mvp/tools.py) is a thin wrapper over MIMIC derived concepts.

`query_suspicion_of_infection`:

- reads `mimiciv_derived.suspicion_of_infection`
- filters to rows where:
  - `suspected_infection = 1`
  - `suspected_infection_time IS NOT NULL`
  - `suspected_infection_time <= visible_until`
- takes the first visible derived concept timestamp as authoritative
- returns compact paired evidence:
  - antibiotic
  - antibiotic time
  - culture time
  - specimen
  - positive culture

`query_sofa`:

- reads `mimiciv_derived.sofa`
- filters to `hr <= t_hour`
- returns the latest visible hourly row
- also returns `max_sofa_24hours_so_far`
- uses the concept table’s rolling 24-hour component logic

Engineering properties:

- simple
- stable
- low adapter burden
- boolean flags and evidence are internally coherent

Clinical properties:

- closely aligned to MIMIC’s Sepsis-3 operationalization
- pre-ICU infection evidence can already be visible at `t=0`
- SOFA is genuinely hourly and rolling-window-based

### Autoformalized backend

The autoformalized runtime in [/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New%20project/src/sepsis_mvp/autoformalized.py):

- creates checkpoint-scoped DuckDB views
- truncates raw tables to the visible prefix
- executes generated functions from [/Users/chloe/Documents/New project/autoformalized_library/functions](/Users/chloe/Documents/New%20project/autoformalized_library/functions)
- adapts the returned dicts into the benchmark tool schema

`query_suspicion_of_infection` comes from [/Users/chloe/Documents/New project/autoformalized_library/functions/suspicion_of_infection.py](/Users/chloe/Documents/New%20project/autoformalized_library/functions/suspicion_of_infection.py).

Its logic is broader than the official derived concept:

- uses raw microbiology and raw antibiotic administrations
- excludes screening cultures such as `MRSA SCREEN`
- excludes likely prophylaxis patterns such as cefazolin
- has a special carveout for vancomycin-only cardiac surgery prophylaxis
- treats suspicion as:
  - any non-screening diagnostic culture, or
  - an antibiotic treatment pattern such as repeated doses or multiple distinct antibiotics

`query_sofa` comes from [/Users/chloe/Documents/New project/autoformalized_library/functions/sofa.py](/Users/chloe/Documents/New%20project/autoformalized_library/functions/sofa.py).

Its logic is raw-data recomputation rather than concept wrapping:

- respiration from PaO2/FiO2 matching within a time window
- cardiovascular from minimum MAP and vasopressor rates
- coagulation from minimum platelets
- liver from maximum bilirubin
- CNS from worst eye/verbal/motor combination
- renal from maximum creatinine

Important difference:

- official SOFA returns an hourly rolling concept row
- autoformalized SOFA returns a visible-prefix score and exposes it as both “latest” and “max so far”

Engineering properties:

- more general and extensible
- more sensitive to raw-table assumptions
- higher adapter complexity

Clinical properties:

- closer to a free-form Sepsis-3-style formalization than an exact MIMIC replica
- allows clinically plausible nuance
- but currently behaves differently enough that it often changes the effective surveillance state

## Most Important Logic Differences

### Infection suspicion

Official:

- suspicion is a formal derived event
- flag and evidence are tightly coupled
- if `has_suspected_infection = false`, evidence is empty

Autoformalized:

- suspicion is inferred from broader raw evidence
- flag comes from the generated function’s boolean
- evidence and first visible time are reconstructed separately by the adapter

That separation causes the main autoformalized consistency problem:

- evidence can exist
- first visible suspicion time can be non-null
- but `has_suspected_infection` can still be `false`

In the full saved auto run, this happened on `125 / 686` steps.

Official had `0 / 686` such steps.

This is the biggest logic-quality issue in the current autoformalized sepsis backend.

### SOFA

Official:

- hourly rolling concept
- includes urine-output-aware renal logic through the concept table
- designed for time-localized surveillance

Autoformalized:

- visible-prefix recomputation
- not truly hourly in the returned schema
- currently does not expose urine-output-based renal logic in the benchmark response
- more likely to differ in both timing and organ attribution

This is not necessarily wrong clinically, but it is a different operationalization.

## Direct Same-Stay Tool Comparison

I reran both backends directly against the current DuckDB for the same `stay_id, t_hour` checkpoints.

### `30135840` at `t=0`

Official:

- infection visible before ICU start
- `first_visible_suspected_infection_hour = -8.96`
- SOFA at entry is `4`

Autoformalized:

- infection not visible
- no evidence returned
- SOFA at entry is `0`

Clinical meaning:

- official: already infected and organ dysfunctional at ICU entry
- autoformalized: clinically quiet at ICU entry

This is a large state change, not a small nuance.

### `30246991` at `t=4`

Official:

- infection visible at hour `1.31`
- evidence is linked to MRSA-screen-related culture timing plus antibiotics
- SOFA is `1`

Autoformalized:

- infection visible earlier at hour `-3.69`
- evidence is antibiotic-driven
- SOFA is also `1`

This is the kind of difference that is clinically acceptable:

- same broad surveillance state
- different interpretation of what counted as suspicion and when it began

### `30382114` at `t=0`

Official:

- infection already visible before ICU start
- SOFA `1`

Autoformalized:

- infection still not visible
- SOFA `3`

This is not just a timing tweak. It flips the surveillance story:

- official: infection already known, mild dysfunction
- autoformalized: no infection yet, stronger organ dysfunction

## Full-Cohort Behavior Comparison

### Step-level performance

Official:

- accuracy: `0.8003`
- macro F1: `0.6152`

Per class:

- `keep_monitoring`: F1 `0.8535`
- `infection_suspect`: F1 `0.1609`
- `trigger_sepsis_alert`: F1 `0.8313`

Autoformalized:

- accuracy: `0.6589`
- macro F1: `0.5463`

Per class:

- `keep_monitoring`: F1 `0.6854`
- `infection_suspect`: F1 `0.2174`
- `trigger_sepsis_alert`: F1 `0.7361`

Interpretation:

- official is clearly stronger overall
- autoformalized is still weak overall
- autoformalized does somewhat better on the intermediate state than official, but only modestly
- official remains much stronger on `keep_monitoring` and `trigger_sepsis_alert`

### Transition timing

From the saved trajectories:

Official infection timing:

- exact match `0.6875`
- MAE `3.17` hours
- late rate `0.3125`
- missed rate `0.0`

Autoformalized infection timing:

- exact match `0.1667`
- MAE `6.0` hours
- late rate `0.8333`
- missed rate `0.0`

Official alert timing:

- exact match `0.3958`
- MAE `2.92` hours
- early rate `0.4792`
- missed rate `0.0`

Autoformalized alert timing:

- exact match `0.5`
- MAE `3.74` hours
- early rate `0.0833`
- late rate `0.375`
- missed rate `0.0417`

Interpretation:

- official detects infection substantially earlier and more accurately
- autoformalized is much more delayed on infection transition
- official is more aggressive and early on sepsis alerts
- autoformalized is less aggressively early, but more often late and occasionally misses the alert entirely

### Prediction distributions

Ground truth:

- `keep_monitoring`: `367`
- `infection_suspect`: `69`
- `trigger_sepsis_alert`: `250`

Official predictions:

- `keep_monitoring`: `343`
- `infection_suspect`: `18`
- `trigger_sepsis_alert`: `325`

Autoformalized predictions:

- `keep_monitoring`: `310`
- `infection_suspect`: `69`
- `trigger_sepsis_alert`: `307`

This is an important pattern.

Official underuses `infection_suspect` dramatically.

Autoformalized predicts `infection_suspect` exactly as often as it appears in the labels, but that does **not** mean it places it correctly. Its recall and precision for that class are both only `0.2174`.

So the auto backend is not really solving the intermediate state. It is redistributing predictions more evenly, but often at the wrong times.

## Evidence-State Analysis

I grouped each step by two visible tool conditions:

- `has_suspected_infection`
- `latest_sofa_24hours >= 2`

### Official backend pattern

When infection is visible but SOFA is still below 2:

- observed steps: `79`
- predicted `keep_monitoring`: `79`
- ground-truth `infection_suspect`: `37`

This is the clearest official failure mode. The agent almost never uses `infection_suspect` when only infection is visible.

When infection and SOFA are both positive:

- observed steps: `346`
- predicted `trigger_sepsis_alert`: `323`
- predicted `infection_suspect`: `18`

So official behaves like a near two-threshold policy:

- infection only -> still often `keep_monitoring`
- infection plus elevated SOFA -> alert

### Autoformalized backend pattern

When infection is visible but SOFA is still below 2:

- observed steps: `69`
- predicted `infection_suspect`: `69`

This looks good at first glance, but the ground truth for those same steps is:

- `infection_suspect`: `15`
- `keep_monitoring`: `43`
- `trigger_sepsis_alert`: `11`

So the autoformalized backend is not simply “better at the middle state.” It often makes infection visible in places where the benchmark labels still say:

- no infection suspicion yet, or
- already alert-level

When infection and SOFA are both positive:

- observed steps: `256`
- predicted `trigger_sepsis_alert`: `256`

So autoformalized uses a cleaner decision rule than official:

- infection only -> suspicion
- infection plus elevated SOFA -> alert

But it applies that rule to a much noisier evidence surface.

## Early-Checkpoint Behavior

This is where the two backends diverge most sharply.

At `t=0` across the 98 stays:

Official:

- suspected infection visible in `44 / 98`
- SOFA >= 2 in `43 / 98`
- both present in `22 / 98`

Autoformalized:

- suspected infection visible in `0 / 98`
- SOFA >= 2 in `3 / 98`
- both present in `0 / 98`

That is a major structural difference.

The official backend allows many stays to begin the ICU trajectory with already-visible infection evidence, which is clinically consistent with the benchmark design.

The current autoformalized backend effectively suppresses that early state almost completely.

This single pattern explains a large portion of:

- lower infection accuracy
- later infection transitions
- lower overall step accuracy

## Trajectory-Level Divergence

Comparing first predicted transition times across the same 98 stays:

Infection prediction comparison:

- same as official: `33`
- auto later than official: `36`
- auto earlier than official: `10`
- auto predicts infection when official never does: `17`
- official predicts infection when auto never does: `2`

Alert prediction comparison:

- same as official: `42`
- auto later than official: `31`
- auto earlier than official: `11`
- auto predicts alert when official never does: `9`
- official predicts alert when auto never does: `5`

So the dominant pattern is:

- autoformalized tends to move infection later
- autoformalized also shifts many alerts later, though less uniformly

## Clinical Interpretation

### What differences are acceptable

It is reasonable for the autoformalized functions to differ from the official MIMIC concepts.

Sepsis-3 gives a clinical framework, not a single universally mandated SQL implementation. Reasonable differences include:

- which cultures count as infection suspicion
- how prophylaxis is filtered
- how suspicion is inferred from treatment patterns
- how early organ dysfunction is summarized from raw ICU signals

That kind of clinical nuance is acceptable.

### What is still not acceptable

The current autoformalized backend still has issues that are bigger than clinical nuance:

1. output inconsistency

- `125` steps have evidence and a timestamp but `has_suspected_infection = false`

2. early-prefix suppression

- `0 / 98` infection-positive steps at `t=0`, compared with `44 / 98` in the official backend

3. large state shifts

- some stays move from “infected with dysfunction at ICU entry” to “no infection and SOFA 0”

Those are engineering-quality and longitudinal-behavior issues, not just alternate clinical interpretation.

## Engineering Interpretation

Official backend strengths:

- simpler wrapper logic
- more stable JSON contract
- concept rows and timestamps already aligned
- clean run artifacts

Autoformalized backend strengths:

- more general architecture
- closer to the long-term autoformalization goal
- richer raw-data reasoning

Autoformalized backend current weaknesses:

- adapter mismatch between boolean flag and evidence payload
- greater sensitivity to raw-table timing assumptions
- weaker early-prefix behavior for infection and SOFA
- current result filenames still carry old `multitask` naming

## Practical Conclusions

### Baseline recommendation

Use the official backend as the primary single-sepsis benchmark baseline.

Reasons:

- better accuracy
- better infection timing
- more coherent outputs
- stronger early surveillance signal

### Research recommendation

Keep the autoformalized backend as the main experimental path for visible concept replacement.

Reasons:

- it is already fully runnable end to end
- it exposes clinically meaningful behavior changes
- it is much closer to the long-term “autoformalization + longitudinal agent” objective

### Highest-value next fix

The first thing to tighten is not prompt tuning. It is the autoformalized suspicion adapter.

Specifically:

- boolean suspicion flag
- earliest visible suspicion time
- emitted evidence rows

should all be derived from one internally consistent criterion.

Once that is fixed, the next comparison will tell us much more cleanly whether the remaining gap is:

- true clinical-definition drift
- SOFA formalization drift
- or mostly adapter inconsistency

## Summary

The full matched 98-stay comparison now makes the picture clear:

- official backend is the stronger and cleaner sepsis baseline
- autoformalized backend changes the agent’s behavior in meaningful ways, but currently degrades the visible infection signal too much
- some clinical nuance is acceptable under Sepsis-3-style monitoring
- the main current blocker is not acceptable nuance, but inconsistent and delayed infection visibility in the autoformalized concept layer
