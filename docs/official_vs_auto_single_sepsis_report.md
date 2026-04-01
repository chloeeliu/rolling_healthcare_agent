# Official vs Autoformalized Single-Sepsis Agent Report

## Scope

This report compares two saved single-task sepsis runs using the same model family, `Qwen3-30B-A3B-Instruct-2507`, but different visible concept backends:

- Official backend: `/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507`
- Autoformalized backend: `/Users/chloe/Documents/New project/result/auto_single_sepsis_Qwen3-30B-A3B-Instruct-2507`

The focus here is not just benchmark metrics. The main goal is to understand how the two visible concept functions change longitudinal agent behavior from both:

- an engineering perspective
- a clinical decision-support perspective

## Executive Summary

The official backend is currently the stronger and cleaner single-sepsis baseline for this benchmark. It produces higher step accuracy, better infection transition timing, and cleaner artifacts. Its main weakness is that the agent often collapses the three-state ladder into a near two-threshold policy: `keep_monitoring` until infection plus SOFA evidence is strong, then `trigger_sepsis_alert`, with very limited use of `infection_suspect`.

The autoformalized backend is more interesting than its lower accuracy suggests. It pushes the agent to use `infection_suspect` more often, which is closer to the intended surveillance ladder. But it does so on top of a concept layer that is visibly less stable and less internally consistent. In practice, that leads to delayed infection recognition, some missed or late alerts, and several steps where the tool returns evidence while still reporting `has_suspected_infection = false`.

So the current tradeoff is:

- official backend: better benchmark alignment, cleaner engineering, more aggressive alerting
- autoformalized backend: more intermediate-state behavior, but weaker and noisier visible evidence

## Important Comparison Caveat

This is not a matched-cohort A/B comparison.

The saved result folders do **not** contain the same set of trajectories:

- official saved trajectories: `98`
- autoformalized saved trajectories: `56`
- overlapping `trajectory_id`s: `0`

Example IDs:

- official-only: `mimiciv_stay_30058012`, `mimiciv_stay_30135840`, `mimiciv_stay_30192858`
- auto-only: `mimiciv_stay_30104258`, `mimiciv_stay_30157290`, `mimiciv_stay_30310155`

That means all cross-backend conclusions should be treated as **directional**, not causal. The saved artifacts are still useful, but they are not a strict paired experiment.

## Artifact Quality And Engineering Reliability

### Official backend artifacts

The official run folder is clean and complete:

- `qwen_events.jsonl`
- `qwen_rollouts.json`
- `qwen_trajectories.jsonl`

Event counts are internally consistent:

- `trajectory_start`: `98`
- `step_start`: `686`
- `tool_call`: `1372`
- `tool_output`: `1372`
- `action`: `686`
- `trajectory_complete`: `98`

This is exactly what we want from a longitudinal agent trace: every step has tool calls, tool outputs, and a final action.

### Autoformalized backend artifacts

The autoformalized folder is usable, but noticeably messier:

- `Copy of auto_qwen_multitask_events.jsonl`
- `Copy of auto_qwen_multitask_trajectories.jsonl`

Despite the filenames, the contents are single-task sepsis. The naming suggests these files were copied or repurposed from a previous run setup. The event log is also incomplete relative to the trajectory JSONL:

- `trajectory_start`: `45`
- `step_start`: `309`
- `model_output_raw`: `926`
- `tool_call`: `617`
- `tool_output`: `617`
- `action`: `308`
- `trajectory_complete`: `44`

But the trajectory JSONL contains `56` completed trajectories. That mismatch strongly suggests at least some combination of:

- copied files
- appended partial runs
- interrupted or restarted execution

This matters because engineering cleanliness is part of benchmark credibility. The official backend currently has a clear advantage here.

### Tool-protocol reliability

Both backends are clearly tool-grounded in the saved runs. This is important because it means the observed differences are not caused by “the model forgot to use tools.”

The saved trajectories show:

- official average tool calls per step: `2.0`
- autoformalized average tool calls per step: `2.0`
- infection prediction grounding rate: `1.0` for both
- alert prediction grounding rate: `1.0` for both

So the main difference is not agent protocol compliance. It is the evidence surface exposed by the backend.

## Step-Level Outcome Comparison

### Official backend

- trajectories: `98`
- steps: `686`
- step accuracy: `0.8003`
- macro F1: `0.6152`

Per-class performance:

- `keep_monitoring`: precision `0.8834`, recall `0.8256`, F1 `0.8535`
- `infection_suspect`: precision `0.3889`, recall `0.1014`, F1 `0.1609`
- `trigger_sepsis_alert`: precision `0.7354`, recall `0.9560`, F1 `0.8313`

### Autoformalized backend

- trajectories: `56`
- steps: `392`
- step accuracy: `0.6684`
- macro F1: `0.6244`

Per-class performance:

- `keep_monitoring`: precision `0.5602`, recall `0.8425`, F1 `0.6730`
- `infection_suspect`: precision `0.6596`, recall `0.3163`, F1 `0.4276`
- `trigger_sepsis_alert`: precision `0.8052`, recall `0.7425`, F1 `0.7726`

### Interpretation

The official backend wins on overall step accuracy, but it does so partly by almost skipping the intended intermediate state:

- official `infection_suspect` recall is only `0.1014`
- official `trigger_sepsis_alert` recall is very high at `0.9560`

The autoformalized backend does something clinically interesting:

- much better `infection_suspect` precision and recall
- lower alert recall
- lower overall accuracy

In other words, the official backend behaves more like an aggressive alerting detector, while the autoformalized backend behaves more like a noisier but more explicit staged monitor.

## Transition Timing Comparison

### Official backend

Infection transition:

- exact match rate: `0.7143`
- mean absolute error: `2.57` hours
- early rate: `0.1327`
- late rate: `0.1531`
- missed rate: `0.0`

Sepsis-alert transition:

- exact match rate: `0.5714`
- mean absolute error: `2.65` hours
- early rate: `0.3673`
- late rate: `0.0612`
- missed rate: `0.0`

### Autoformalized backend

Infection transition:

- exact match rate: `0.2857`
- mean absolute error: `5.69` hours
- early rate: `0.1071`
- late rate: `0.5357`
- missed rate: `0.0714`

Sepsis-alert transition:

- exact match rate: `0.5893`
- mean absolute error: `3.61` hours
- early rate: `0.1429`
- late rate: `0.1786`
- missed rate: `0.0893`

### Interpretation

The official backend is much better at placing the infection transition. The autoformalized backend is substantially later:

- lower exact match
- more late infection predictions
- nonzero missed infection transitions

The alert timing comparison is more mixed:

- official is more aggressive and earlier
- autoformalized is less early, but also misses some alerts

This pattern fits what we see in the raw tool outputs: the autoformalized visible concept layer often delays or suppresses infection visibility, so the downstream agent does not get a clean early “infection is now visible” signal.

## Decision Logic Patterns From Saved Traces

To understand the agent behavior better, I grouped steps by the visible tool state:

- `has_suspected_infection`
- `latest_sofa_24hours >= 2`

### Official backend pattern

Observed step counts:

- no infection, SOFA < 2: `117`
- no infection, SOFA >= 2: `144`
- infection, SOFA < 2: `79`
- infection, SOFA >= 2: `346`

Predicted actions:

- no infection, SOFA < 2 -> `keep_monitoring` on all `117` steps
- no infection, SOFA >= 2 -> almost always `keep_monitoring` (`142/144`)
- infection, SOFA < 2 -> `keep_monitoring` on all `79` steps
- infection, SOFA >= 2 -> mostly `trigger_sepsis_alert` (`323/346`)

This is close to a simple threshold policy:

- suspicion alone is usually not enough
- infection plus SOFA elevation triggers alert

That explains the low `infection_suspect` recall.

### Autoformalized backend pattern

Observed step counts:

- no infection, SOFA < 2: `117`
- no infection, SOFA >= 2: `103`
- infection, SOFA < 2: `47`
- infection, SOFA >= 2: `125`

Predicted actions:

- no infection, SOFA < 2 -> `keep_monitoring` on all `117` steps
- no infection, SOFA >= 2 -> split: `keep_monitoring` `74`, alert `29`
- infection, SOFA < 2 -> `infection_suspect` on all `47` steps
- infection, SOFA >= 2 -> `trigger_sepsis_alert` on all `125` steps

This is much more aligned with the intended 3-state ladder:

- infection without strong dysfunction -> `infection_suspect`
- infection with stronger dysfunction -> alert

But that cleaner policy is only as good as the visible evidence layer feeding it. Right now that visible layer is much less reliable than the official one.

## Direct Same-Stay Tool Comparison

To separate agent policy from backend evidence, I ran both current tool backends directly on the same DuckDB for the same `stay_id, t_hour` checkpoints.

### Example 1: stay `30294009`, `t=0`

Official `query_suspicion_of_infection`:

- `has_suspected_infection = true`
- first visible hour `-4.92`
- supporting blood culture visible before ICU start

Autoformalized `query_suspicion_of_infection`:

- `has_suspected_infection = false`
- first visible hour `-0.33`
- antibiotic evidence present

Official `query_sofa`:

- `latest_sofa_24hours = 3`

Autoformalized `query_sofa`:

- `latest_sofa_24hours = 0`

Engineering insight:

- same patient
- same checkpoint
- same pipeline contract
- very different visible evidence

Clinical implication:

- official backend would support immediate escalation awareness
- autoformalized backend makes the same case look clinically quieter at ICU entry

### Example 2: stay `30294009`, `t=4`

Official infection remains positive with early blood-culture evidence.

Autoformalized infection becomes positive only by `t=4`, and its evidence mix is different:

- urine and sputum cultures
- antibiotic administrations
- first visible hour closer to ICU start than official

SOFA total becomes `5` for both backends, but component attribution differs:

- official: heavy cardiovascular contribution, no CNS contribution
- autoformalized: cardiovascular plus CNS contribution

Clinical implication:

- even when totals agree, the explanatory story differs
- that matters if future prompts or clinician review depend on component-level rationale

### Example 3: stay `30157290`, `t=4`

Official infection:

- `has_suspected_infection = true`
- first visible hour `3.27`
- urine culture linked to levofloxacin timing

Autoformalized infection:

- `has_suspected_infection = false`
- same first visible hour `3.27`
- antibiotic evidence present

Official SOFA:

- total `1`

Autoformalized SOFA:

- total `3`
- driven by CNS rather than cardiovascular contribution

This is a particularly important example because it shows two different failure modes at once:

- infection flag suppression despite visible evidence
- higher organ dysfunction burden than official at the same checkpoint

That combination can distort both the intermediate state and the alert transition.

## Internal Consistency Of The Visible Concept Layer

The official backend is internally consistent in the saved traces:

- `has_suspected_infection = false` never co-occurs with populated infection evidence in the saved official trajectories

The autoformalized backend is not yet as clean:

- `101 / 392` saved steps had `has_suspected_infection = false` **and** non-empty evidence

Example saved steps:

- `mimiciv_stay_30104258`, `t=0`
- `mimiciv_stay_30104258`, `t=4`
- `mimiciv_stay_30157290`, `t=4`

This is an engineering issue before it is a clinical one. Even if we intentionally allow broader clinical semantics, the returned JSON should still be self-consistent. Right now, the autoformalized adapter can expose:

- non-null `first_visible_suspected_infection_time`
- non-empty antibiotic or culture evidence
- `has_suspected_infection = false`

That makes the tool harder for any agent to reason over reliably.

## Clinical Interpretation

### What the official backend is doing well

- Captures early infection visibility more often, including pre-ICU evidence
- Produces stronger infection timing alignment with the benchmark labels
- Supports high alert recall once infection and SOFA evidence accumulate

### What the official backend is doing poorly

- Underuses `infection_suspect`
- Often jumps from monitoring directly to alert-like behavior
- Functions more like a sepsis-alert trigger than a full staged surveillance agent

### What the autoformalized backend is doing well

- Encourages a cleaner 3-state decision ladder
- Produces substantially better `infection_suspect` performance
- Appears less reflexively over-alerting than the official backend

### What the autoformalized backend is doing poorly

- Suppresses or delays infection visibility
- Sometimes misses infection or alert transitions entirely
- Produces clinically different SOFA burden at the same checkpoint
- Exposes internally inconsistent infection outputs

In practical clinical-monitoring terms, the official backend is currently more useful for reliable onset detection, while the autoformalized backend is more useful as a proof of concept for agent-facing staged monitoring behavior.

## Engineering Recommendations

### 1. Run a true matched-cohort A/B next

This is the most important next step. Both backends should be run on the **same exact stay list** with clean fresh outputs:

- same dataset file
- same sample size
- same trajectory IDs
- same model
- same prompt version

Without that, backend comparisons remain suggestive rather than definitive.

### 2. Clean up autoformalized result packaging

The saved autoformalized folder should use standard filenames:

- `qwen_events.jsonl`
- `qwen_trajectories.jsonl`
- `qwen_rollouts.json`
- `qwen_eval.json`

This will make downstream analysis much less error-prone.

### 3. Enforce internal consistency in the autoformalized adapter

For `query_suspicion_of_infection`, the adapter should resolve contradictions like:

- `has_suspected_infection = false`
- but evidence exists and first visible time is non-null

Even if the clinical definition stays broad, the emitted JSON should be logically coherent.

### 4. Save evaluation summaries for all runs

Some of the saved results here had to be reconstructed from trajectories because the result folders were not uniform. Standardizing `--evaluation-output` for every run will make future comparisons much easier.

## Clinical Recommendations

### 1. Keep official backend as the benchmark-aligned sepsis baseline

For the current longitudinal benchmark, the official visible concept layer is still the more dependable baseline.

### 2. Use autoformalized backend as a visible-concept stress test

The autoformalized backend is valuable because it tests whether the agent can still behave sensibly when the concept layer is:

- broader
- less standardized
- less benchmark-aligned

That is exactly the kind of stress test that matters for a generalized healthcare longitudinal agent.

### 3. Consider explicit prompt guidance to preserve the intermediate state

The official backend does not naturally produce strong `infection_suspect` behavior. That likely deserves further prompt or policy support, because clinically the surveillance value of the 3-state ladder depends on not collapsing suspicion into immediate alerting.

## Bottom Line

The official backend currently wins as the production-quality baseline for single-task sepsis surveillance:

- better engineering hygiene
- better timing alignment
- higher overall accuracy

The autoformalized backend is already good enough to be scientifically interesting, but not yet good enough to replace the official baseline:

- it better supports the intended staged-monitoring policy
- but it does so with a weaker and sometimes internally inconsistent visible concept layer

The most valuable next experiment is a **matched-cohort official vs autoformalized rerun** with clean output packaging and saved evaluation summaries. That will tell us whether the current gap is mainly:

- concept quality
- adapter logic
- or genuine clinical-definition drift.
