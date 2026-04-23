# General ICU Surveillance Benchmark Feasibility Report

Date: 2026-04-22

## Purpose

This report revisits the idea of a harder rolling ICU surveillance benchmark with four constraints:

1. prefer tasks that are already available in `mimiciv_derived`
2. find about `10` benchmark tasks
3. analyze the actual local DuckDB cohort for feasibility
4. keep the design compatible with the current rolling benchmark stack where possible

Database audited:

- `/Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db`

Relevant current code:

- [src/sepsis_mvp/schemas.py](/Users/chloe/Documents/New project/src/sepsis_mvp/schemas.py)
- [src/sepsis_mvp/tools.py](/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py)
- [src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py)
- [docs/final_benchmark_design_spec.md](/Users/chloe/Documents/New project/docs/final_benchmark_design_spec.md)

## Executive Summary

The conclusion is yes: a derived-table-first general ICU surveillance benchmark is feasible.

The strongest version is not "10 discharge diagnoses." It is a rolling benchmark over about `10` acute ICU surveillance targets or syndrome heads whose first visible event time can be recovered from `mimiciv_derived`.

Recommended core 10-task set:

1. infection surveillance
2. sepsis alerting
3. severe AKI
4. oliguria
5. respiratory support escalation
6. vasoactive/hemodynamic support
7. neurologic deterioration
8. hyperlactatemia
9. severe acidemia
10. coagulopathy

Optional reserve task:

- CRRT initiation

Why this set works:

- every core task has a usable temporal definition
- every core task has large positive counts inside the ICU cohort
- most of the core tasks are already aligned with the existing benchmark tool surface
- the cohort is strongly multitask: on the 48h cohort, `65.03%` of stays already have `>= 3` of the 10 core tasks positive by 24h

Main caveat:

- `bg` and `coagulation` are `hadm_id`-linked rather than `stay_id`-linked, so they are usable, but need careful time-windowing and a documented caveat for admissions with multiple ICU stays

## Selection Criteria

I treated a task as benchmark-feasible only if it met most of the following:

- defined from `mimiciv_derived`, not a fresh raw-table phenotype
- has a clinically meaningful first visible time
- can be anchored to an ICU stay or at least hospital admission plus timestamp
- is common enough within `24h` or `48h` to support rebalanced train/dev/test splits
- has label semantics that can be translated into rolling surveillance actions or ordinal states

I did not require every task to be an independent disease entity. For ICU surveillance, the more realistic target family is acute syndromes, organ failures, and intervention-triggering deterioration states.

## Cohort Definitions

Two cohorts matter here:

### Current benchmark-compatible cohort

- ICU stays with `intime IS NOT NULL`
- ICU stays with `outtime IS NOT NULL`
- ICU LOS `>= 24h`

Size:

- `74,829` eligible ICU stays

### Harder surveillance cohort

- same filters
- ICU LOS `>= 48h`

Size:

- `46,337` eligible ICU stays

I recommend the `48h` cohort for the harder benchmark, because it creates room for later transitions, recovery paths, and true rolling monitoring.

### Suggested subject-level split on the 48h cohort

Using the same deterministic subject split rule style as the existing benchmark:

- `train`: `32,654`
- `dev`: `6,934`
- `test`: `6,749`

### Hadm-level caveat for some tasks

Some candidate tasks are only available at `hadm_id` level in `mimiciv_derived`:

- `bg`
- `coagulation`

On the 48h eligible cohort:

- stays in admissions with more than one eligible ICU stay: `6,538 / 46,337` = `14.11%`

This is not fatal, but it means hadm-linked tasks should be documented as "time-bounded admission-visible evidence," not purely stay-native evidence.

## Recommended Candidate Tasks

| Task | Primary derived source | First visible event definition | Linkage | Status |
|---|---|---|---|---|
| `infection` | `mimiciv_derived.suspicion_of_infection` | earliest `suspected_infection_time` | `stay_id` | strong |
| `sepsis3` | `mimiciv_derived.sepsis3` | earliest `GREATEST(suspected_infection_time, sofa_time)` | `stay_id` | strong |
| `aki_stage23` | `mimiciv_derived.kdigo_stages` | earliest `charttime` with `aki_stage_smoothed >= 2` | `stay_id` | strong |
| `oliguria_6h_lt_0_5` | `mimiciv_derived.urine_output_rate` | earliest `charttime` with `uo_tm_6hr >= 6` and `uo_mlkghr_6hr < 0.5` | `stay_id` | strong |
| `resp_support` | `mimiciv_derived.ventilation` | earliest `starttime` with medium-or-higher support; invasive is a subclass | `stay_id` | strong |
| `vasoactive_support` | `mimiciv_derived.vasoactive_agent` | earliest `starttime` with any non-null vasoactive/inotropic infusion | `stay_id` | strong |
| `gcs_le_8` | `mimiciv_derived.gcs` | earliest `charttime` with `gcs <= 8` | `stay_id` | strong |
| `lactate_ge_4` | `mimiciv_derived.bg` | earliest `charttime` with `lactate >= 4` | `hadm_id` | usable with caveat |
| `ph_lt_7_20` | `mimiciv_derived.bg` | earliest `charttime` with `pH < 7.20` | `hadm_id` | usable with caveat |
| `inr_ge_2` | `mimiciv_derived.coagulation` | earliest `charttime` with `INR >= 2` | `hadm_id` | usable with caveat |
| `crrt` | `mimiciv_derived.crrt` | earliest `charttime` with `crrt_mode IS NOT NULL` | `stay_id` | feasible but rarer |

## Recommended Core 10

If we want an exact 10-task benchmark, I recommend this core set:

1. `infection`
2. `sepsis3`
3. `aki_stage23`
4. `oliguria_6h_lt_0_5`
5. `resp_support`
6. `vasoactive_support`
7. `gcs_le_8`
8. `lactate_ge_4`
9. `ph_lt_7_20`
10. `inr_ge_2`

Why `crrt` is not in the default core 10:

- it is feasible
- it is clinically meaningful
- but it is much rarer than the others
- it behaves more like a rescue-intervention head than a broad surveillance head

So I would keep `crrt` as:

- an optional task 11
- or a high-value auxiliary label nested under the AKI family

## Feasibility on the 48h Cohort

The table below is the most relevant one for the harder benchmark.

Definitions:

- `positive_by_24h`: first visible event occurs by `icu_intime + 24h`
- `positive_by_48h`: first visible event occurs by `icu_intime + 48h`
- `present_by_t0`: first visible event is already visible at ICU admission
- `onset_0_24h`: first visible event occurs during `(0, 24]`
- `onset_24_48h`: first visible event occurs during `(24, 48]`

48h cohort denominator: `46,337`

| Task | Ever positive | Positive by 24h | Positive by 48h | Present by t0 | Onset 0-24h | Onset 24-48h | After 48h | % by 24h | % by 48h |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `infection` | 32,369 | 29,890 | 30,597 | 20,215 | 9,675 | 707 | 1,772 | 64.51 | 66.03 |
| `oliguria_6h_lt_0_5` | 37,621 | 24,674 | 32,568 | 31 | 24,643 | 7,894 | 5,053 | 53.25 | 70.29 |
| `sepsis3` | 27,321 | 23,739 | 24,905 | 186 | 23,553 | 1,166 | 2,416 | 51.23 | 53.75 |
| `resp_support_medium_plus` | 26,566 | 23,417 | 24,971 | 3,365 | 20,052 | 1,554 | 1,595 | 50.54 | 53.89 |
| `aki_stage23` | 34,891 | 22,437 | 29,985 | 3,456 | 18,981 | 7,548 | 4,906 | 48.42 | 64.71 |
| `resp_support_invasive` | 24,527 | 21,658 | 22,998 | 3,213 | 18,445 | 1,340 | 1,529 | 46.74 | 49.63 |
| `vasoactive_support` | 18,770 | 15,781 | 17,017 | 707 | 15,074 | 1,236 | 1,753 | 34.06 | 36.72 |
| `inr_ge_2` | 12,953 | 7,924 | 8,646 | 3,927 | 3,997 | 722 | 4,307 | 17.10 | 18.66 |
| `lactate_ge_4` | 8,566 | 6,519 | 6,932 | 2,170 | 4,349 | 413 | 1,634 | 14.07 | 14.96 |
| `ph_lt_7_20` | 6,683 | 4,362 | 4,843 | 1,460 | 2,902 | 481 | 1,840 | 9.41 | 10.45 |
| `gcs_le_8` | 9,550 | 4,046 | 5,417 | 140 | 3,906 | 1,371 | 4,133 | 8.73 | 11.69 |
| `crrt` | 2,617 | 887 | 1,385 | 18 | 869 | 498 | 1,232 | 1.91 | 2.99 |

### Interpretation

Very strong tasks:

- `infection`
- `sepsis3`
- `aki_stage23`
- `oliguria_6h_lt_0_5`
- `resp_support`
- `vasoactive_support`

Still clearly feasible:

- `gcs_le_8`
- `lactate_ge_4`
- `ph_lt_7_20`
- `inr_ge_2`

Feasible but meaningfully rarer:

- `crrt`

The timing shape is also good:

- `infection` has a lot of `t=0` positives, which is clinically realistic and good for "already infected on arrival" monitoring
- `sepsis3`, `oliguria`, `AKI`, `resp_support`, and `vasoactive_support` all still have substantial `(0, 24]` transitions
- `AKI` and `oliguria` also continue to accumulate enough transitions in `(24, 48]` to justify a 48h benchmark
- `gcs_le_8`, `lactate_ge_4`, `ph_lt_7_20`, and `inr_ge_2` are less common, but still large enough for rebalanced sampling

## Context on the 24h-Compatible Cohort

For comparison, on the current `LOS >= 24h` cohort (`74,829` stays), positive-by-24h counts are:

| Task | Positive by 24h | Present by t0 | Onset 0-24h | After 24h | % by 24h |
|---|---:|---:|---:|---:|---:|
| `infection` | 44,035 | 30,141 | 13,894 | 2,506 | 58.85 |
| `oliguria_6h_lt_0_5` | 37,489 | 39 | 37,450 | 15,534 | 50.10 |
| `sepsis3` | 33,509 | 230 | 33,279 | 3,634 | 44.78 |
| `aki_stage23` | 33,034 | 4,912 | 28,122 | 14,760 | 44.15 |
| `resp_support_medium_plus` | 31,953 | 4,329 | 27,624 | 3,243 | 42.70 |
| `resp_support_invasive` | 29,532 | 4,136 | 25,396 | 2,923 | 39.47 |
| `vasoactive_support` | 22,177 | 946 | 21,231 | 3,033 | 29.64 |
| `inr_ge_2` | 11,107 | 5,323 | 5,784 | 6,784 | 14.84 |
| `lactate_ge_4` | 8,596 | 2,953 | 5,643 | 2,435 | 11.49 |
| `gcs_le_8` | 5,707 | 178 | 5,529 | 5,673 | 7.63 |
| `ph_lt_7_20` | 5,582 | 1,935 | 3,647 | 2,694 | 7.46 |
| `crrt` | 1,047 | 20 | 1,027 | 1,764 | 1.40 |

This means the benchmark is feasible even if we stayed with the current 24h horizon, but the 48h cohort is more natural for a harder longitudinal benchmark.

## Split-Level Safety Margins on the 48h Cohort

Positive-by-24h counts by deterministic subject split:

| Task | Train | Dev | Test |
|---|---:|---:|---:|
| `infection` | 21,069 | 4,416 | 4,405 |
| `sepsis3` | 16,677 | 3,541 | 3,521 |
| `aki_stage23` | 15,842 | 3,346 | 3,249 |
| `oliguria_6h_lt_0_5` | 17,348 | 3,717 | 3,609 |
| `resp_support_medium_plus` | 16,420 | 3,558 | 3,439 |
| `vasoactive_support` | 11,175 | 2,289 | 2,317 |
| `gcs_le_8` | 2,830 | 621 | 595 |
| `lactate_ge_4` | 4,627 | 950 | 942 |
| `ph_lt_7_20` | 3,098 | 638 | 626 |
| `inr_ge_2` | 5,642 | 1,177 | 1,105 |
| `crrt` | 633 | 140 | 114 |

Interpretation:

- every core 10 task has comfortable split-level margins
- even the rarer heads like `gcs_le_8`, `ph_lt_7_20`, and `inr_ge_2` remain workable
- `crrt` is still feasible if rebalanced aggressively, but it is the only task that feels genuinely small

## Multitask Complexity

Using the 10 recommended core tasks on the 48h cohort, the number of tasks already positive by 24h per stay is:

| Positive task count by 24h | Stays |
|---|---:|
| `0` | 3,954 |
| `1` | 5,356 |
| `2` | 6,893 |
| `3` | 7,424 |
| `4` | 7,416 |
| `5` | 6,470 |
| `6` | 4,664 |
| `7` | 2,488 |
| `8` | 1,137 |
| `9` | 485 |
| `10` | 50 |

Compressed view:

- `91.47%` have `>= 1` positive task by 24h
- `79.91%` have `>= 2`
- `65.03%` have `>= 3`
- `49.01%` have `>= 4`
- `33.01%` have `>= 5`

This is a strong argument for a general surveillance benchmark:

- the cohort is truly multitask
- tasks overlap heavily
- the hard part is evidence management and prioritization, not single-label rarity

## Runtime and Tooling Readiness

Current shared benchmark tool surface already covers most of the recommended tasks.

Already exposed in both official and autoformalized runtimes:

- `query_suspicion_of_infection`
- `query_sofa`
- `query_kdigo_stage`
- `query_ventilation_status`
- `query_urine_output_rate`
- `query_vasoactive_agent`
- `query_vitalsign`
- `query_bg`
- `query_gcs`

This means the following tasks are already close to runnable:

- infection
- sepsis via infection + SOFA composition
- AKI
- oliguria
- respiratory support
- vasoactive/hemodynamic support
- neurologic deterioration
- hyperlactatemia
- severe acidemia

Missing as explicit benchmark-facing tools today:

- coagulopathy from `mimiciv_derived.coagulation`
- CRRT from `mimiciv_derived.crrt`

So from an implementation perspective:

- `8` to `9` of the recommended heads are already mostly aligned with the current stack
- only `coagulopathy` and optional `crrt` clearly require new benchmark-facing adapters

## Autoformalized Library Support Audit

This section answers a different question from the cohort feasibility sections above.

The previous sections asked:

- does the local database support these tasks?

This section asks:

- does the current autoformalized function library support these tasks well enough to be benchmark-facing?

That distinction matters because the autoformalized runtime does not expose every generated function, and some generated functions only partially match the preferred `mimiciv_derived` gold definition.

### Current autoformalized runtime exposure

The current autoformalized runtime maps only the following benchmark-facing tool names:

- `query_suspicion_of_infection`
- `query_sofa`
- `query_kdigo_stage`
- `query_ventilation_status`
- `query_urine_output_rate`
- `query_vasoactive_agent`
- `query_vitalsign`
- `query_bg`
- `query_gcs`
- `query_antibiotic`
- `query_invasive_line`

Source:

- [src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py)

Notably absent from the current runtime mapping:

- no `query_sepsis3`
- no `query_coagulation`
- no `query_crrt`

So even before semantic quality, those three tasks are not benchmark-callable through the current autoformalized runtime.

### Summary matrix

| Benchmark task | Autoformalized function | Runtime-exposed today | Derived-gold alignment | Assessment |
|---|---|---|---|---|
| `infection` | `suspicion_of_infection.py` | yes | medium | usable now |
| `sepsis3` | `sepsis3.py` | no | low-to-medium | not benchmark-ready as-is |
| `aki_stage23` | `kdigo_stages.py` | yes | medium | usable with caution |
| `oliguria_6h_lt_0_5` | `urine_output_rate.py` | yes | medium | usable with caution |
| `resp_support` | `ventilation.py` | yes | medium | usable for escalation, weak for exact current-state semantics |
| `vasoactive_support` | `vasoactive_agent.py` | yes | medium | usable now |
| `gcs_le_8` | `gcs.py` | yes | high | strong |
| `lactate_ge_4` | `bg.py` | yes | medium | usable now |
| `ph_lt_7_20` | `bg.py` | yes | medium | usable now |
| `inr_ge_2` | `coagulation.py` | no | low-to-medium | needs adapter and semantic cleanup |
| `crrt` | `crrt.py` | no | medium | needs adapter |

### Detailed per-task analysis

#### 1. Infection surveillance

Autoformalized support:

- function: [autoformalized_library/functions/suspicion_of_infection.py](/Users/chloe/Documents/New project/autoformalized_library/functions/suspicion_of_infection.py)
- runtime adapter: `query_suspicion_of_infection`

What is strong:

- explicitly models cultures plus antibiotic treatment pattern
- excludes common screening cultures
- excludes common prophylaxis patterns
- includes a useful cardiac-surgery prophylaxis guardrail
- works naturally with the checkpoint-scoped autoformalized runtime

What is not perfectly aligned with `mimiciv_derived`:

- it is a hand-built heuristic over raw microbiology and antibiotic records, not a direct wrapper over `mimiciv_derived.suspicion_of_infection`
- the adapter reconstructs earliest visible evidence from culture and antibiotic timestamps rather than returning the official derived `suspected_infection_time`

Assessment:

- strong enough to support the benchmark today
- but not an exact implementation of the preferred derived-table gold label

#### 2. Sepsis-3

Autoformalized support:

- function file exists: [autoformalized_library/functions/sepsis3.py](/Users/chloe/Documents/New project/autoformalized_library/functions/sepsis3.py)
- no runtime adapter today

What is strong:

- conceptually targets sepsis and septic shock

What is problematic:

- it is not exposed in the runtime mapping in [src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py)
- the function references `get_suspicion_of_infection`, `first_day_sofa`, and `compute_sofa_score` directly, but those helpers are defined in other files and are not imported in `sepsis3.py`
- under the current runtime design, each function file is executed in its own namespace, so this file is not safely benchmark-runnable as-is
- semantically, it uses:
  - suspicion heuristic from the autoformalized infection function
  - first-day SOFA as baseline
  - worst SOFA delta over the stay
- that is not the same as the preferred official `mimiciv_derived.sepsis3` onset definition

Assessment:

- do not treat `sepsis3.py` as ready support for a benchmark task
- for the benchmark, sepsis should continue to be implemented by composing:
  - `query_suspicion_of_infection`
  - `query_sofa`
- if we want a dedicated autoformalized sepsis tool later, it should be rebuilt as a proper standalone function and explicitly mapped into the runtime

#### 3. Severe AKI

Autoformalized support:

- function: [autoformalized_library/functions/kdigo_stages.py](/Users/chloe/Documents/New project/autoformalized_library/functions/kdigo_stages.py)
- runtime adapter: `query_kdigo_stage`

What is strong:

- explicitly computes creatinine-based and urine-output-based KDIGO logic
- returns ordinal stage information
- works naturally inside checkpoint-scoped views, so the visible data is time-bounded

What diverges from preferred derived gold:

- it is not a direct wrapper around `mimiciv_derived.kdigo_stages`
- creatinine baseline logic differs from the official derived table:
  - uses prior 3 months if available
  - otherwise first ICU creatinine
- it does not implement the exact official smoothing behavior used by `aki_stage_smoothed`
- CRRT is not explicitly included in the overall stage calculation inside this autoformalized function

Adapter limitation:

- the adapter returns a simplified stage view and treats the returned stage as both current and max-so-far
- it does not expose first onset times directly

Assessment:

- good enough for benchmark-facing AKI evidence and stage tracking
- but should be treated as an approximate KDIGO implementation, not a perfect match to `mimiciv_derived.kdigo_stages`

#### 4. Oliguria

Autoformalized support:

- function: [autoformalized_library/functions/urine_output_rate.py](/Users/chloe/Documents/New project/autoformalized_library/functions/urine_output_rate.py)
- runtime adapter: `query_urine_output_rate`

What is strong:

- explicitly focuses on urine output rate
- returns `min_6hr_rate_mL_kg_hr`
- returns `has_oliguria` and `has_severe_oliguria`

What needs caution:

- the function’s boolean flags are derived from instantaneous or interval-based hourly rates, while the benchmark gold definition I used in the feasibility study was closer to a sustained 6-hour criterion
- the function uses the first available weight in kg and can fail or simplify if weight data are sparse
- it is not a direct wrapper over `mimiciv_derived.urine_output_rate`

Assessment:

- usable as a benchmark tool for oliguria evidence
- but if oliguria becomes a gold task, the benchmark definition should be explicit about whether the gold target is:
  - sustained 6-hour oliguria from derived tables
  - or autoformalized minimum-rate detection
- I would prefer derived-table gold labels and keep the autoformalized function as evidence, not gold truth

#### 5. Respiratory support escalation

Autoformalized support:

- function: [autoformalized_library/functions/ventilation.py](/Users/chloe/Documents/New project/autoformalized_library/functions/ventilation.py)
- runtime adapter: `query_ventilation_status`

What is strong:

- distinguishes invasive ventilation, non-invasive ventilation, and HFNC
- returns human-readable device details
- useful for surveillance and escalation reasoning

What is weaker than `mimiciv_derived.ventilation`:

- it does not produce intervalized support segments like the official derived table
- it works from raw device and mode evidence rather than the derived ventilation event table
- it does not return explicit first transition times itself

Important benchmark nuance:

- within the checkpoint-scoped runtime, the function effectively answers "has this support type been seen up to now?"
- the adapter then maps that to support levels
- this is good for escalation detection
- it is weaker for exact current-state labeling after support changes

Assessment:

- strong enough for an escalation-style respiratory task
- weaker if we wanted precise contemporaneous support status at every checkpoint

#### 6. Vasoactive/hemodynamic support

Autoformalized support:

- function: [autoformalized_library/functions/vasoactive_agent.py](/Users/chloe/Documents/New project/autoformalized_library/functions/vasoactive_agent.py)
- runtime adapter: `query_vasoactive_agent`

What is strong:

- directly identifies whether vasoactive agents were used
- returns agent names and timing summaries
- includes both vasopressors and inotropes

What is missing for a richer shock task:

- not based on `mimiciv_derived.vasoactive_agent`
- no explicit norepinephrine-equivalent normalization
- no blood-pressure or MAP requirement
- no direct severity staging

Assessment:

- strong enough for a "vasoactive support present" benchmark head
- not enough by itself for a richer septic-shock or hemodynamic-instability phenotype

#### 7. Neurologic deterioration

Autoformalized support:

- function: [autoformalized_library/functions/gcs.py](/Users/chloe/Documents/New project/autoformalized_library/functions/gcs.py)
- runtime adapter: `query_gcs`

What is strong:

- directly computes total GCS from components
- returns both `min_gcs` and `min_gcs_all`
- explicitly flags severe impairment
- very close to the intended benchmark task

Minor nuance:

- `min_gcs` excludes intubated periods, while `has_severe_impairment` uses `min_gcs_all`
- that is clinically reasonable, but the benchmark should document which quantity is authoritative

Assessment:

- this is one of the strongest autoformalized task supports in the library

#### 8. Hyperlactatemia

Autoformalized support:

- function: [autoformalized_library/functions/bg.py](/Users/chloe/Documents/New project/autoformalized_library/functions/bg.py)
- runtime adapter: `query_bg`

What is strong:

- returns `peak_lactate`
- combines ICU and hospital blood gas/lab evidence within the ICU stay interval
- works well for threshold-based surveillance

What diverges from preferred gold:

- it is not a direct wrapper around `mimiciv_derived.bg`
- its built-in boolean threshold is `lactate >= 2`, while the recommended benchmark head in this report is `lactate >= 4`

Important positive:

- the adapter returns the numeric `peak_lactate`, so the benchmark can apply the stricter threshold externally

Assessment:

- good benchmark support
- use the numeric output, not only the built-in boolean flag

#### 9. Severe acidemia

Autoformalized support:

- function: [autoformalized_library/functions/bg.py](/Users/chloe/Documents/New project/autoformalized_library/functions/bg.py)
- runtime adapter: `query_bg`

What is strong:

- returns `min_pH`
- returns `has_severe_acidosis`
- the severe acidemia threshold in the function already uses `pH <= 7.20`, which is well aligned with the benchmark proposal

What needs caution:

- same general caveat as the lactate task: this is a raw-query implementation, not a direct wrapper over `mimiciv_derived.bg`

Assessment:

- strong support

#### 10. Coagulopathy

Autoformalized support:

- function file exists: [autoformalized_library/functions/coagulation.py](/Users/chloe/Documents/New project/autoformalized_library/functions/coagulation.py)
- no runtime adapter today

What is strong:

- returns max/min/mean INR and PTT
- provides exactly the kind of summary a coagulopathy evidence tool would need

What is problematic:

- it queries `mimiciv_icu.chartevents`, not the hospital lab path that underlies the preferred `mimiciv_derived.coagulation` gold table
- the benchmark feasibility analysis in this report used the official derived coagulation concept, which is admission-level lab evidence
- the built-in elevated INR flag uses `> 1.5`, while the proposed benchmark head used `INR >= 2`

Assessment:

- the library has enough raw material to support a coagulopathy tool
- but it is not currently benchmark-ready
- before using it, I would:
  - add a runtime adapter
  - review whether it should be rewritten against the admission-visible lab pathway instead of ICU chartevents
  - expose the raw max INR so the benchmark can use its own threshold

#### 11. CRRT

Autoformalized support:

- function file exists: [autoformalized_library/functions/crrt.py](/Users/chloe/Documents/New project/autoformalized_library/functions/crrt.py)
- no runtime adapter today

What is strong:

- directly identifies whether CRRT was used
- returns modes, timing, and clotting-related details
- conceptually maps well to a CRRT rescue/intervention head

What is weaker than preferred gold:

- it is not a wrapper over `mimiciv_derived.crrt`
- it is built from raw chartevent itemids and system-integrity states

Assessment:

- this is supportable with a new adapter
- but because the task is also much rarer, I would still keep CRRT as optional task 11 or an AKI auxiliary head

### Autoformalized support tiers

#### Tier A: strong today

- `infection`
- `gcs_le_8`
- `lactate_ge_4`
- `ph_lt_7_20`
- `vasoactive_support`

#### Tier B: usable today, but semantically approximate

- `aki_stage23`
- `oliguria_6h_lt_0_5`
- `resp_support`

#### Tier C: function exists, but not benchmark-exposed yet

- `coagulopathy`
- `crrt`

#### Tier D: do not rely on as-is

- `sepsis3`

The reason `sepsis3` lands in Tier D is not that the library lacks useful sepsis evidence. It is that:

- the actual evidence tools are already there
- but the dedicated `sepsis3.py` function is not mapped into the runtime
- and the file is not safely standalone under the current autoformalized execution model

### What this means for the benchmark

If the benchmark is built now on top of the current autoformalized stack, the most robust path is:

1. keep sepsis as a composed task from infection plus SOFA tools, not from `sepsis3.py`
2. use the current autoformalized tools directly for:
   - infection
   - AKI
   - oliguria
   - respiratory support
   - vasoactive support
   - GCS
   - blood gas tasks
3. add explicit runtime adapters for:
   - `query_coagulation`
   - `query_crrt`
4. if we want a dedicated autoformalized sepsis tool later, rebuild `sepsis3.py` as a true standalone function with clear checkpoint-safe semantics

## Recommended Benchmark Shape

### Recommended cohort

- use ICU LOS `>= 48h`

### Recommended checkpoints

- `0, 2, 4, 8, 12, 18, 24, 36, 48`

### Recommended task structure

Use one state vector per checkpoint rather than one single task label.

Suggested 10-task heads:

1. `infection`
2. `sepsis`
3. `aki`
4. `oliguria`
5. `respiratory_support`
6. `vasoactive_support`
7. `neurologic_deterioration`
8. `hyperlactatemia`
9. `severe_acidemia`
10. `coagulopathy`

Optional:

11. `crrt`

### Recommended label style

Not every head needs the same label space.

A practical v1 shape is:

- binary onset heads:
  - infection
  - sepsis
  - lactate
  - acidemia
  - coagulopathy
  - CRRT
- ordinal heads:
  - AKI
  - respiratory support
  - neurologic deterioration
  - shock/hemodynamic support

### Recommended sampling strategy

Do not sample prevalence-faithfully.

Instead, rebalance on:

- early vs late onset
- present at `t=0` vs develops after admission
- isolated task positives vs overlapping multitask positives
- hard negatives:
  - infection without sepsis
  - oliguria without severe AKI
  - respiratory support without vasoactives
  - lactate/acidemia without sepsis

## Tasks I Would Not Prioritize for v1

I would not prioritize the following as top-level benchmark heads in the first build:

- `sofa` as its own task
  - useful as hidden severity metadata
  - but too overlapping with sepsis plus organ-failure heads
- `sirs`
  - available, but too coarse and not obviously a better benchmark target than infection or shock
- `rhythm`
  - derived table exists, but it is weaker for stay-level rolling labeling and not yet aligned with the current benchmark tool surface
- `invasive_line`
  - useful context feature, not a disease/surveillance head

## Final Recommendation

The safest derived-table-first plan is:

1. build the harder benchmark on the `48h` cohort
2. use the 10 recommended core tasks above
3. keep `crrt` as optional task 11 or an AKI auxiliary head
4. reuse the current tool surface for the first `8` to `9` tasks
5. add new benchmark-facing adapters only for:
   - `query_coagulation`
   - optionally `query_crrt`

In short:

- the data is there
- the cohort is large enough
- the multitask overlap is real
- a derived-first 10-task ICU surveillance benchmark is feasible without inventing fragile raw-table phenotypes from scratch
