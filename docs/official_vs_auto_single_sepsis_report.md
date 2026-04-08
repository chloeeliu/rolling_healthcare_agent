# Official vs Autoformalized Single-Sepsis Report

## Scope

This report compares two saved single-task sepsis runs under [/Users/chloe/Documents/New project/result](/Users/chloe/Documents/New%20project/result):

- official visible concepts: [/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507](/Users/chloe/Documents/New%20project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507)
- autoformalized visible concepts: [/Users/chloe/Documents/New project/result/auto_single_sepsis_Qwen3-30B-A3B-Instruct-2507](/Users/chloe/Documents/New%20project/result/auto_single_sepsis_Qwen3-30B-A3B-Instruct-2507)

Both runs use the same model family, `Qwen3-30B-A3B-Instruct-2507`, and both now cover the same saved cohort:

- official trajectories: `98`
- auto trajectories: `98`
- overlap: `98`

So this is a true matched run-to-run comparison on the saved result set.

One caveat: this 98-stay saved cohort appears older than the latest revised sepsis CSV currently in the repo. To avoid mixing cohorts, this report uses the saved rollout artifacts themselves as the comparison source of truth.

## Executive Summary

The official backend is still the stronger single-sepsis baseline.

Why:

- better step accuracy: `0.8003` vs `0.6589`
- better macro F1: `0.6152` vs `0.5463`
- much stronger early infection visibility
- no internal contradiction between infection flag and evidence payload

The autoformalized backend is still valuable, but the refreshed full comparison makes its current weakness very specific:

- it often suppresses or delays infection visibility
- it changes the early surveillance state much more than the official backend
- it still returns many steps with evidence present but `has_suspected_infection = false`

So the main conclusion is not “autoformalized is clinically invalid.” It is:

- some clinical nuance is acceptable under Sepsis-3-style monitoring
- but the current autoformalized visible concept layer is not yet internally coherent enough to support a clean replacement of the official one

## 1. Function Logic Comparison

This is the most important difference. The two agents are using the same model family and the same tool loop. The main thing that changes is the visible concept layer.

### Official functions

The official backend in [/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py](/Users/chloe/Documents/New%20project/src/sepsis_mvp/tools.py) is a thin wrapper over MIMIC derived concepts.

`query_suspicion_of_infection`

- source: `mimiciv_derived.suspicion_of_infection`
- time gating:
  - look up ICU `intime`
  - compute `visible_until = intime + t_hour`
  - keep rows with `suspected_infection_time <= visible_until`
- logic:
  - only rows with `suspected_infection = 1`
  - first visible suspicion time comes directly from the derived concept
- output:
  - `has_suspected_infection`
  - first visible hour/time
  - paired antibiotic-culture evidence

`query_sofa`

- source: `mimiciv_derived.sofa`
- time gating:
  - keep rows with `hr <= t_hour`
  - select the latest visible row
- logic:
  - uses the hourly rolling 24-hour SOFA concept
  - returns both latest visible SOFA and max SOFA so far
- output:
  - `latest_sofa_24hours`
  - `max_sofa_24hours_so_far`
  - latest component-level 24-hour values

Engineering characteristics:

- simple wrappers
- low adapter risk
- stable JSON contract
- boolean flags and evidence are coupled

Clinical characteristics:

- strongly aligned with MIMIC’s Sepsis-3 operationalization
- supports pre-ICU visible infection evidence at `t=0`
- treats SOFA as a rolling hourly surveillance concept

### Autoformalized functions

The autoformalized backend in [/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New%20project/src/sepsis_mvp/autoformalized.py) is different in kind, not just degree.

It does not wrap an already-derived concept table. It:

1. builds checkpoint-scoped DuckDB views for the current `stay_id, t_hour`
2. truncates raw tables to the visible prefix
3. loads generated `FINAL_FUNCTION`s from [/Users/chloe/Documents/New project/autoformalized_library/functions](/Users/chloe/Documents/New%20project/autoformalized_library/functions)
4. runs them inside that truncated DB context
5. adapts their outputs back into the benchmark tool schema

This means the auto backend is a concept generator plus adapter, not just a concept wrapper.

### How `query_suspicion_of_infection` differs

Generated logic in [/Users/chloe/Documents/New project/autoformalized_library/functions/suspicion_of_infection.py](/Users/chloe/Documents/New%20project/autoformalized_library/functions/suspicion_of_infection.py):

- reads raw microbiology events
- excludes screening cultures such as `MRSA SCREEN`
- reads ICU antibiotic administrations and hospital prescriptions
- matches broad antibiotic names
- excludes likely prophylaxis patterns:
  - cefazolin-like prophylaxis
  - some vancomycin-only cardiac surgery cases
- defines suspicion using a broader heuristic:
  - any non-screening diagnostic culture, or
  - an antibiotic treatment pattern such as repeated doses or multiple distinct antibiotics

Adapter logic in [/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New%20project/src/sepsis_mvp/autoformalized.py):

- pulls `culture_orders` and `antibiotic_administrations` from the generated function output
- reconstructs `evidence`
- reconstructs `first_visible_suspected_infection_time` from the earliest evidence timestamp
- takes `has_suspected_infection` from the generated boolean `has_suspicion_of_infection`

That last split is the current problem:

- evidence time is reconstructed one way
- boolean suspicion is taken from another field

So the auto backend can emit:

- evidence present
- first visible suspicion time present
- but `has_suspected_infection = false`

The official backend never does that.

### How `query_sofa` differs

Generated logic in [/Users/chloe/Documents/New project/autoformalized_library/functions/sofa.py](/Users/chloe/Documents/New%20project/autoformalized_library/functions/sofa.py):

- computes component scores directly from raw events in the visible prefix
- respiration:
  - PaO2/FiO2 matching within a time window
  - ventilation inferred from vent mode or PEEP
- coagulation:
  - minimum platelets
- liver:
  - maximum bilirubin
- cardiovascular:
  - minimum MAP
  - maximum vasopressor rates
- CNS:
  - minimum eye, verbal, and motor subscores combined into a worst GCS-like score
- renal:
  - maximum creatinine

Adapter logic:

- maps the generated `total_score` into:
  - `latest_sofa_24hours`
  - `max_sofa_24hours_so_far`
- maps the component scores into the benchmark response fields

So the auto SOFA tool is not truly returning an hourly rolling SOFA row. It is returning a visible-prefix SOFA-like summary and exposing it in the old schema.

### Logic difference summary

Official:

- derived concept wrapper
- narrow and stable
- concept timestamp is authoritative
- rolling hourly SOFA is preserved

Autoformalized:

- raw-data concept generator plus adapter
- broader infection suspicion heuristic
- visible-prefix SOFA summary rather than official hourly rolling SOFA
- more clinically flexible, but much more sensitive to adapter quality

Clinical nuance is acceptable here. Exact identity is not required. But internal coherence is required, and the current auto suspicion wrapper still violates that.

## 2. Statistic Results Comparison

To keep the comparison apples-to-apples, the statistics below are derived from the saved trajectory files for both runs.

### Step-level performance

Official:

- step accuracy: `0.8003`
- macro F1: `0.6152`

Per class:

- `keep_monitoring`: precision `0.8834`, recall `0.8256`, F1 `0.8535`
- `infection_suspect`: precision `0.3889`, recall `0.1014`, F1 `0.1609`
- `trigger_sepsis_alert`: precision `0.7354`, recall `0.9560`, F1 `0.8313`

Autoformalized:

- step accuracy: `0.6589`
- macro F1: `0.5463`

Per class:

- `keep_monitoring`: precision `0.7484`, recall `0.6322`, F1 `0.6854`
- `infection_suspect`: precision `0.2174`, recall `0.2174`, F1 `0.2174`
- `trigger_sepsis_alert`: precision `0.6678`, recall `0.8200`, F1 `0.7361`

Main insight:

- official is clearly better overall
- official is especially stronger on `keep_monitoring` and `trigger_sepsis_alert`
- autoformalized is only modestly better on the intermediate state, and that gain is not enough to close the larger accuracy gap

### Transition timing

Official infection timing:

- exact match `0.6875`
- mean absolute error `3.17` hours
- late rate `0.3125`
- missed rate `0.0`

Autoformalized infection timing:

- exact match `0.1667`
- mean absolute error `6.0` hours
- late rate `0.8333`
- missed rate `0.0`

Official alert timing:

- exact match `0.3958`
- mean absolute error `2.92` hours
- early rate `0.4792`
- late rate `0.1250`
- missed rate `0.0`

Autoformalized alert timing:

- exact match `0.5000`
- mean absolute error `3.74` hours
- early rate `0.0833`
- late rate `0.3750`
- missed rate `0.0417`

Main insight:

- official is substantially better at infection timing
- autoformalized is much later on infection in most positive cases
- official is more aggressive and earlier on alerting
- autoformalized is less aggressively early, but more often late and occasionally misses alerts

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

Main insight:

- official underpredicts `infection_suspect` very heavily
- autoformalized predicts `infection_suspect` as often as it appears in the labels, but mostly not at the right times
- so auto is not truly “solving” the middle state; it is redistributing predictions more evenly over a noisier evidence surface

### Early-checkpoint evidence contrast

At `t=0` across the 98 stays:

Official:

- infection visible in `44 / 98`
- SOFA >= 2 in `43 / 98`
- both present in `22 / 98`

Autoformalized:

- infection visible in `0 / 98`
- SOFA >= 2 in `3 / 98`
- both present in `0 / 98`

This is the single strongest statistical signal in the comparison.

Main insight:

- the official backend lets many stays start as “already infected” at ICU entry
- the current autoformalized backend almost completely suppresses that early state
- this explains a large share of its lower infection accuracy and later infection transitions

### Evidence consistency statistic

Official:

- steps with evidence present but `has_suspected_infection = false`: `0 / 686`

Autoformalized:

- steps with evidence present but `has_suspected_infection = false`: `125 / 686`

Main insight:

- this is not a small statistical quirk
- it is the clearest engineering-quality issue in the current auto suspicion wrapper

## 3. Case Analysis

These cases show how the function-layer differences change downstream agent behavior.

### Case A: pre-ICU infected patient missed early by auto

Trajectory: `mimiciv_stay_30135840`

Ground truth:

- `t=0`: `infection_suspect`
- `t=4+`: `trigger_sepsis_alert`

Official behavior:

- `t=0`: infection visible at `-8.96h`, SOFA `4`
- predicts alert immediately

Autoformalized behavior:

- `t=0`: no infection visible, SOFA `0`
- `t=4`: still no infection visible
- `t=8`: infection finally appears at `5.59h`, SOFA `4`, then alert

What it shows:

- official and auto are not just choosing different labels
- they are starting from a very different clinical state at ICU entry
- this is a backend evidence issue first, not a prompt issue

### Case B: official collapses the intermediate state, auto handles it better

Trajectory: `mimiciv_stay_30246991`

Ground truth:

- `t=0`: `keep_monitoring`
- `t=4-16`: `infection_suspect`
- `t=20+`: `trigger_sepsis_alert`

Official behavior:

- infection visible from `t=4`
- SOFA stays `1`
- still predicts `keep_monitoring` through `t=16`
- jumps to alert at `t=20`

Autoformalized behavior:

- evidence appears even earlier
- from `t=4-16`, predicts `infection_suspect`
- alerts at `t=20`

What it shows:

- official backend plus agent policy tends to ignore “infection only” states
- autoformalized can sometimes produce cleaner ladder behavior when the evidence surface happens to align well

### Case C: auto over-alerts because its state story is different

Trajectory: `mimiciv_stay_30382114`

Ground truth:

- `t=0-20`: `infection_suspect`
- `t=24`: `trigger_sepsis_alert`

Official behavior:

- infection already visible before ICU start
- SOFA stays low early
- delays until `t=20`, then alerts slightly early

Autoformalized behavior:

- `t=0`: no infection visible, SOFA `3`
- `t=4`: infection appears, SOFA still `3`
- predicts `trigger_sepsis_alert` from `t=4` onward

What it shows:

- autoformalized can combine delayed infection with higher dysfunction
- that can yield a qualitatively different surveillance state from the official backend

### Case D: non-sepsis false alert under auto

Trajectory: `mimiciv_stay_30192858`

Ground truth:

- all checkpoints: `keep_monitoring`

Official behavior:

- no infection evidence
- SOFA `0`
- stays `keep_monitoring`

Autoformalized behavior:

- `t=4`: infection appears at `0.77h`, SOFA `2`
- predicts `trigger_sepsis_alert` from `t=4` onward

What it shows:

- autoformalized can create a complete false sepsis path on a non-sepsis trajectory
- the issue here is not just “different nuance”; it is an overly permissive visible concept layer

### Case E: hidden evidence appears before the flag flips

Trajectory: `mimiciv_stay_31585193`

Ground truth:

- all checkpoints: `keep_monitoring`

Official behavior:

- no infection evidence throughout
- SOFA elevated but no infection signal
- correctly stays `keep_monitoring`

Autoformalized behavior:

- `t=4`: evidence exists and `first_visible_suspected_infection_hour = 0.08`, but `has_suspected_infection = false`
- `t=12+`: infection flag turns true and the agent alerts

What it shows:

- the flag/evidence inconsistency is not theoretical
- it can directly create false downstream escalation

## 4. Next Steps And Useful Insights

### Highest-priority fix

Tighten the autoformalized `query_suspicion_of_infection` adapter.

Right now the wrapper derives:

- boolean suspicion
- earliest visible suspicion time
- evidence payload

from partially different signals.

Those three should be made consistent.

### Second-priority fix

Decide whether the autoformalized SOFA tool should stay as:

- a visible-prefix summary

or whether it should be upgraded toward:

- a truly hourly rolling response closer to the benchmark contract

Exact semantic identity is not required, but the current “latest equals max equals prefix total” mapping is a large departure from the official surveillance shape.

### Third-priority experiment

After fixing the suspicion adapter, rerun the same 98-stay cohort and compare:

- early infection visibility at `t=0`
- false-with-evidence count
- infection timing exact match
- non-sepsis false alert count

Those four numbers should move quickly if the adapter fix is working.

### Main research insight

The current results suggest the biggest bottleneck is not the LLM itself.

The same Qwen model family can do reasonably coherent tool use under both backends. What changes most is:

- which evidence becomes visible
- when it becomes visible
- whether the evidence surface is internally coherent

So for this project, the concept layer really is the main lever.

### Main benchmark insight

The official baseline is not perfect either.

Its clearest weakness is:

- when infection is visible but SOFA is still below 2, it almost always stays at `keep_monitoring`

So the official backend is better overall, but it still behaves more like:

- no strong dysfunction -> monitor
- infection + elevated SOFA -> alert

than like a well-calibrated 3-state surveillance monitor.

That means there are two different next-step opportunities:

1. improve autoformalized concept quality
2. improve policy-level use of the intermediate `infection_suspect` state even for the official backend

## Bottom Line

The full matched 98-stay comparison makes the picture much clearer than the earlier partial run:

- official backend is the stronger current sepsis baseline
- autoformalized backend is a promising research direction, but its current infection concept layer is too delayed and too inconsistent
- some clinical nuance is fine under Sepsis-3-style monitoring
- the main current gap is not acceptable nuance, but inconsistent and weakened longitudinal infection visibility
