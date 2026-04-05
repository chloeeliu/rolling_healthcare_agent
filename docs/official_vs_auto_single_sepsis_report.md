# Official vs Autoformalized Single-Sepsis Report

## Scope

This report compares two single-task sepsis runs under `/Users/chloe/Documents/New project/result`:

- official visible concepts: [/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507](/Users/chloe/Documents/New%20project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507)
- autoformalized visible concepts: [/Users/chloe/Documents/New project/result/auto_single_sepsis_Qwen3-30B-A3B-Instruct-2507](/Users/chloe/Documents/New%20project/result/auto_single_sepsis_Qwen3-30B-A3B-Instruct-2507)

Both runs use the same model family, `Qwen3-30B-A3B-Instruct-2507`. The comparison focuses on:

1. how the two function types differ
2. how the agent behavior changes downstream
3. what the differences mean clinically and engineering-wise

Important context:

- the official run is complete with `98` trajectories
- the current autoformalized run is partial with `9` trajectories
- those `9` auto trajectories are all contained inside the official run

That means this report can make a **true matched comparison on 9 shared stays**, while still using the full official run as background context.

## Bottom Line

The official backend is still the stronger benchmark-aligned baseline for sepsis surveillance. It exposes infection earlier, gives more stable early SOFA evidence, and produces cleaner outputs for the agent. On the matched 9-stay subset, it gets slightly higher step accuracy than the current autoformalized backend.

The autoformalized backend is not simply worse. It changes the decision problem in a meaningful way:

- it uses a broader, raw-data-derived interpretation of infection suspicion
- it often delays or suppresses early infection visibility
- it sometimes produces stronger or different organ dysfunction signals than the official SOFA wrapper
- it encourages the agent to use `infection_suspect` more often, which is closer to the intended 3-state monitoring ladder

So the current picture is:

- official backend: cleaner and more stable, but tends to collapse into a near two-threshold policy
- autoformalized backend: more intermediate-state behavior, but less reliable early evidence and more output inconsistency

Because sepsis practice is nuanced and the benchmark prompt only gives high-level guidance, some clinical-definition drift is acceptable. The main requirement is not exact semantic identity with MIMIC’s derived tables. The requirement is that the visible concept layer stays internally coherent and reasonably aligned with Sepsis-3-style logic. That is where the current autoformalized backend still needs work.

## Comparison Setup

### Artifact status

Official folder:

- `qwen_events.jsonl`
- `qwen_rollouts.json`
- `qwen_trajectories.jsonl`

Autoformalized folder:

- `auto_qwen_multitask_events.jsonl`
- `auto_qwen_multitask_trajectories.jsonl`

The auto filenames still say `multitask`, but the contents are single-task sepsis trajectories.

### Matched partial subset

Current trajectory counts:

- official run: `98`
- autoformalized run: `9`
- overlap: `9`

Shared trajectory IDs:

- `mimiciv_stay_30058012`
- `mimiciv_stay_30135840`
- `mimiciv_stay_30192858`
- `mimiciv_stay_30246991`
- `mimiciv_stay_30366834`
- `mimiciv_stay_30382114`
- `mimiciv_stay_30634429`
- `mimiciv_stay_30924053`
- `mimiciv_stay_31054046`

So the cleanest current comparison is:

- official on those 9 stays
- autoformalized on those same 9 stays

### Run completeness

Official event log is complete:

- `trajectory_start`: `98`
- `step_start`: `686`
- `tool_call`: `1372`
- `tool_output`: `1372`
- `action`: `686`
- `trajectory_complete`: `98`

Autoformalized event log looks interrupted:

- `trajectory_start`: `10`
- `step_start`: `64`
- `model_output_raw`: `191`
- `tool_call`: `127`
- `tool_output`: `127`
- `action`: `63`
- `trajectory_complete`: `9`

That fits your note: the auto run is partial.

## Function-Level Comparison

This is the most important section, because the agent differences mostly come from the evidence layer.

### Official function type

The official backend in [/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py](/Users/chloe/Documents/New%20project/src/sepsis_mvp/tools.py) is a thin wrapper over MIMIC derived concepts:

- `query_suspicion_of_infection`
  - reads `mimiciv_derived.suspicion_of_infection`
  - filters `suspected_infection = 1`
  - filters `suspected_infection_time <= visible_until`
  - returns compact evidence and first visible hour
- `query_sofa`
  - reads `mimiciv_derived.sofa`
  - uses latest visible row with `hr <= t_hour`
  - also returns max SOFA so far

Engineering characteristics:

- very stable output contract
- explicit time gating
- no extra interpretation inside the wrapper
- low adapter complexity

Clinical characteristics:

- strongly tied to MIMIC’s Sepsis-3 implementation choices
- early infection visibility includes pre-ICU evidence when it is already visible by ICU start
- SOFA is genuinely hourly and rolling-window-based

### Autoformalized function type

The autoformalized backend in [/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New%20project/src/sepsis_mvp/autoformalized.py) does something different:

- it creates a checkpoint-truncated DuckDB context
- it executes generated raw-query functions from [/Users/chloe/Documents/New project/autoformalized_library/functions](/Users/chloe/Documents/New%20project/autoformalized_library/functions)
- it adapts their outputs back into the benchmark tool schema

For infection suspicion, the generated logic in [/Users/chloe/Documents/New project/autoformalized_library/functions/suspicion_of_infection.py](/Users/chloe/Documents/New%20project/autoformalized_library/functions/suspicion_of_infection.py):

- excludes screening cultures
- uses broad antibiotic name matching
- checks treatment-pattern heuristics and culture orders
- reasons from raw microbiology, prescriptions, ICU inputevents, and procedures

For SOFA, the generated logic in [/Users/chloe/Documents/New project/autoformalized_library/functions/sofa.py](/Users/chloe/Documents/New%20project/autoformalized_library/functions/sofa.py):

- recomputes SOFA components directly from raw chartevents, labevents, and inputevents
- uses the visible prefix of the stay
- returns a single prefix score and component breakdown

Engineering characteristics:

- much more flexible and generalizable
- much higher adapter complexity
- more room for mismatch between raw function output and benchmark-facing JSON

Clinical characteristics:

- closer to a free-form formalization of Sepsis-3 ideas than to the exact MIMIC derived SQL
- allows reasonable clinical nuance
- but does not yet maintain the same prefix-time behavior or internal consistency as the official layer

## Detailed Function Differences

### `query_suspicion_of_infection`

Official behavior:

- binary flag and evidence are tightly coupled
- if `has_suspected_infection = false`, evidence is empty
- first visible hour reflects MIMIC-derived `suspected_infection_time`

Autoformalized behavior:

- evidence is constructed from returned culture rows and antibiotic administrations
- flag is taken from generated field `has_suspicion_of_infection`
- first visible hour is reconstructed from earliest observed evidence time

This creates a key failure mode:

- evidence can be present
- first visible infection time can be non-null
- but `has_suspected_infection` can still be `false`

In the current partial auto run, that happened on `3 / 63` steps.

Examples from the saved trajectories:

- `mimiciv_stay_30246991`, `t=0`, first visible hour `-3.69`, evidence count `1`, but infection flag false
- `mimiciv_stay_30366834`, `t=0`, first visible hour `-18.64`, evidence count `3`, but infection flag false
- `mimiciv_stay_31054046`, `t=0`, first visible hour `-25.76`, evidence count `4`, but infection flag false

This is not a subtle semantic disagreement. It is an internal consistency problem in the current adapter/function combination.

### `query_sofa`

Official behavior:

- latest visible hourly SOFA row
- max SOFA so far
- 24-hour rolling component values

Autoformalized behavior:

- one total score for the visible prefix
- that total is exposed as both latest and max
- component attribution comes directly from generated raw-data logic

This means the autoformalized version is Sepsis-3-inspired, but not equivalent to the official hourly rolling concept. That is acceptable for a generalized pipeline if we are explicit about it. The real issue is not that it differs. The issue is whether it differs in a clinically coherent way.

## Direct Same-Stay Tool Comparisons

I reran both backends directly against the current DuckDB for the same `stay_id, t_hour` checkpoints.

### Example: `30135840` at `t=0`

Official:

- infection visible before ICU start
- `first_visible_suspected_infection_hour = -8.96`
- SOFA at `t=0` is already `4`

Autoformalized:

- infection not visible
- no evidence returned
- SOFA at `t=0` is `0`

Clinical meaning:

- official presents this case as already infected with organ dysfunction at ICU entry
- autoformalized presents it as clinically quiet at ICU entry

This single difference explains a large share of the downstream behavior on that stay.

### Example: `30246991` at `t=4`

Official:

- infection visible at hour `1.31`
- evidence linked to MRSA screen plus antibiotics
- SOFA is `1`

Autoformalized:

- infection visible earlier at hour `-3.69`
- evidence comes from antibiotics only
- SOFA is also `1`

Clinical meaning:

- the two backends agree that this patient is suspicious but not yet alert-level at `t=4`
- they disagree on *why* and *when* suspicion became visible

This is a clinically acceptable kind of nuance as long as the output is internally consistent and still supports Sepsis-3-style escalation.

### Example: `30382114` at `t=0`

Official:

- infection already visible before ICU start
- SOFA `1`

Autoformalized:

- infection still not visible
- SOFA `3`

Clinical meaning:

- official says “infection already suspected, low dysfunction”
- autoformalized says “no infection yet, but stronger neurological dysfunction”

That is not just nuance. It is a qualitatively different surveillance state.

### Example: `30382114` at `t=20`

Official:

- infection still anchored to pre-ICU blood culture
- SOFA `2`

Autoformalized:

- infection becomes visible much later at hour `3.08`
- evidence is antibiotic-heavy
- SOFA `3`

So even later in the stay, the backends tell different stories:

- official: infection was already present long ago, now SOFA has reached alert level
- autoformalized: infection emerges later and organ dysfunction looks stronger

## Agent Behavior On The Matched 9-Stay Subset

### Step-level metrics

Official on the same 9 shared stays:

- steps: `63`
- accuracy: `0.6825`
- macro F1: `0.5006`

Per class:

- `keep_monitoring`: F1 `0.7838`
- `infection_suspect`: F1 `0.0`
- `trigger_sepsis_alert`: F1 `0.7179`

Autoformalized on those 9 stays:

- steps: `63`
- accuracy: `0.6667`
- macro F1: `0.6196`

Per class:

- `keep_monitoring`: F1 `0.75`
- `infection_suspect`: F1 `0.5`
- `trigger_sepsis_alert`: F1 `0.6087`

Interpretation:

- official is slightly better on raw accuracy
- autoformalized is much better at using the intermediate state
- official effectively misses `infection_suspect` on this subset

### Transition timing

Official on the shared 9 stays:

- infection timing exact match: `0.5`
- infection MAE: `9.0` hours
- infection late rate: `0.5`
- alert exact match: `0.25`
- alert MAE: `3.0` hours
- alert early rate: `0.75`

Autoformalized on the shared 9 stays:

- infection timing exact match: `0.25`
- infection MAE: `4.0` hours
- infection late rate: `0.75`
- alert exact match: `0.5`
- alert MAE: `6.0` hours
- alert early rate: `0.25`
- alert late rate: `0.25`

Interpretation:

- official alerts earlier and more aggressively
- autoformalized delays infection recognition more often
- autoformalized is less aggressively early on alerting

### Prediction distributions

Ground truth on the shared 9 stays:

- `keep_monitoring`: `36`
- `infection_suspect`: `12`
- `trigger_sepsis_alert`: `15`

Official predictions:

- `keep_monitoring`: `38`
- `infection_suspect`: `1`
- `trigger_sepsis_alert`: `24`

Autoformalized predictions:

- `keep_monitoring`: `28`
- `infection_suspect`: `4`
- `trigger_sepsis_alert`: `31`

Both are alert-heavy. The difference is that autoformalized preserves the middle state more often.

## How The Agent Policy Changes

I grouped each step by visible evidence:

- `has_suspected_infection`
- `latest_sofa_24hours >= 2`

### Official on the matched 9 stays

When infection is visible but SOFA is still below 2:

- observed steps: `9`
- predicted `infection_suspect`: `0`
- predicted `keep_monitoring`: `9`
- ground truth `infection_suspect`: `9`

This is the clearest behavioral failure of the official setup. The agent does not really use the intermediate surveillance state when only infection is visible.

When infection and SOFA are both positive:

- observed steps: `25`
- predicted `trigger_sepsis_alert`: `24`
- predicted `infection_suspect`: `1`

So official behaves like:

- no strong dysfunction yet -> keep monitoring
- infection + SOFA burden -> alert

That is clinically understandable, but it compresses the intended ladder.

### Autoformalized on the matched 9 stays

When infection is visible but SOFA is still below 2:

- observed steps: `4`
- predicted `infection_suspect`: `4`
- ground truth `infection_suspect`: `4`

This is much better ladder behavior.

When infection and SOFA are both positive:

- observed steps: `31`
- predicted `trigger_sepsis_alert`: `31`

So the autoformalized backend yields a cleaner decision rule:

- infection only -> suspicion
- infection plus SOFA elevation -> alert

But it gets there with a different evidence surface, and that surface often delays infection onset or changes early SOFA burden.

## Clinical Interpretation

### What differences are acceptable

It is reasonable that the two function families do not match exactly.

Sepsis-3 gives a framework:

- suspicion of infection
- organ dysfunction, often operationalized with SOFA increase

But there is still real practice-level flexibility in:

- which cultures count
- how prophylaxis is excluded
- how antibiotic treatment patterns are interpreted
- how early ICU-prefix SOFA is operationalized

So a generated function is allowed to interpret these details differently, as long as it still behaves like a coherent Sepsis-3-style concept layer.

### What differences are not yet acceptable

The current autoformalized backend still has several issues that are not just “clinical nuance”:

1. infection flag inconsistency

- evidence can exist while `has_suspected_infection = false`

2. weak early-prefix stability

- some cases that are clearly infected and dysfunctional at `t=0` under the official layer become `no infection, SOFA 0` under autoformalized

3. explanation drift

- even when total SOFA is similar, component attribution can be very different

Those issues make it harder to interpret agent behavior as a clinically meaningful alternative formalization rather than just a noisier one.

## Engineering Interpretation

### Official backend strengths

- simpler runtime
- lower adapter burden
- stable outputs
- complete saved artifacts

### Autoformalized backend strengths

- more general architecture
- easier to extend to new concept functions
- closer to the “autoformalization + longitudinal task” research goal

### Autoformalized backend current weaknesses

- partial run artifacts
- lingering filename mismatch
- adapter-level inconsistency in suspicion outputs
- less stable early-prefix behavior

## Practical Conclusions

### Current baseline recommendation

Use the official backend as the current benchmark-facing sepsis baseline.

Reasons:

- stronger early evidence
- cleaner outputs
- slightly better matched-subset accuracy
- more reliable infection timing

### Current research recommendation

Keep the autoformalized backend as the main research path for visible concepts.

Reasons:

- it already changes agent behavior in a meaningful way
- it is closer to the long-term goal of a generalized concept library
- it exposes exactly the kinds of issues that matter for autoformalization quality

### Most important next step

When you provide a complete auto run later, rerun this report on:

- the same full cohort
- the same prompt version
- the same model
- cleanly completed output files

That will let us answer the real question much more cleanly:

Is the performance gap mainly due to:

- partial run artifacts
- current adapter bugs
- or genuinely weaker clinical formalization?

## Summary

On the current matched 9-stay subset:

- official backend is slightly better on step accuracy
- autoformalized backend is much better at preserving `infection_suspect`
- official backend is more aggressive and early-alerting
- autoformalized backend is more conservative on infection visibility, but not always more clinically faithful

The important message is not “official good, auto bad.” It is:

- official gives a stronger benchmark-aligned baseline
- autoformalized gives a plausible alternative Sepsis-3 interpretation, but it still needs tighter internal coherence before it can be judged mainly on clinical nuance rather than engineering noise
