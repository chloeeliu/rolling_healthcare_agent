# Autoformalized Dataset Curation Task Audit

Date: 2026-04-23

## Purpose

This note answers two dataset-curation questions for the general ICU monitoring benchmark:

1. can we stay fully inside the autoformalized function library and only add an adapter layer, without revising logic back against `derived_sql`?
2. which tasks and functions are the best fit for the benchmark if we want the benchmark to be genuinely autoformalized-native?

This audit is based on direct inspection of:

- [src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py)
- [autoformalized_library/functions/suspicion_of_infection.py](/Users/chloe/Documents/New project/autoformalized_library/functions/suspicion_of_infection.py)
- [autoformalized_library/functions/sofa.py](/Users/chloe/Documents/New project/autoformalized_library/functions/sofa.py)
- [autoformalized_library/functions/kdigo_stages.py](/Users/chloe/Documents/New project/autoformalized_library/functions/kdigo_stages.py)
- [autoformalized_library/functions/urine_output_rate.py](/Users/chloe/Documents/New project/autoformalized_library/functions/urine_output_rate.py)
- [autoformalized_library/functions/ventilation.py](/Users/chloe/Documents/New project/autoformalized_library/functions/ventilation.py)
- [autoformalized_library/functions/vasoactive_agent.py](/Users/chloe/Documents/New project/autoformalized_library/functions/vasoactive_agent.py)
- [autoformalized_library/functions/bg.py](/Users/chloe/Documents/New project/autoformalized_library/functions/bg.py)
- [autoformalized_library/functions/gcs.py](/Users/chloe/Documents/New project/autoformalized_library/functions/gcs.py)
- [autoformalized_library/functions/coagulation.py](/Users/chloe/Documents/New project/autoformalized_library/functions/coagulation.py)
- [autoformalized_library/functions/crrt.py](/Users/chloe/Documents/New project/autoformalized_library/functions/crrt.py)
- [autoformalized_library/functions/sepsis3.py](/Users/chloe/Documents/New project/autoformalized_library/functions/sepsis3.py)

## Executive Answer

## 1. Can this be fully autoformalized with only an adapter layer?

Short answer:

- for agent-facing evidence tools: mostly yes
- for dataset curation and gold labels: not quite

The important distinction is:

- `adapter-only` is enough to make many functions usable at checkpoint time
- `adapter-only` is not enough to make every function a safe benchmark task or gold-label source

What is still needed beyond a thin adapter:

- a frozen benchmark task contract per task
- stable mapping from raw function outputs to `keep_monitoring`, `suspect`, and `alert`
- one composed task definition for `sepsis`

What is *not* needed:

- a return to official `derived_sql`
- task logic rewritten to match the official MIMIC derived tables

So the right answer is:

- yes, the benchmark can remain fully autoformalized-native
- no, "adapter only and nothing else" is too optimistic for dataset curation

The extra logic should be benchmark contract logic on top of autoformalized outputs, not a derived-table rewrite.

## 2. Final task list and function list

If we allow:

- benchmark-facing adapters
- frozen task contracts on top of autoformalized outputs
- a composed `sepsis` task from autoformalized components

then the best benchmark task list is:

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

Optional task 11:

11. `crrt`

If the requirement is much stricter and we allow only:

- field renaming
- schema normalization
- no benchmark contract logic except direct flag passthrough

then the safer reduced set is:

1. `infection`
2. `aki`
3. `respiratory_support`
4. `vasoactive_support`
5. `neurologic_deterioration`
6. `hyperlactatemia`
7. `severe_acidemia`

That smaller set is cleaner, but it leaves too much clinical value on the table. I do not recommend using the stricter interpretation for the benchmark.

## What Counts As Acceptable Extra Logic

To avoid future confusion, these should count as acceptable benchmark logic:

- renaming heterogeneous function outputs into a common schema
- freezing thresholds such as `lactate >= 4` or `pH <= 7.20`
- mapping ordinal or numeric outputs into `keep_monitoring` / `suspect` / `alert`
- composing `sepsis` from `infection` plus `sofa`

These should *not* be required:

- rewriting the task against official `mimiciv_derived`
- re-implementing phenotype SQL because the autoformalized function is unusable
- hand-tuning disease-specific prompts to repair weak task definitions

## Task-By-Task Audit

## 1. Infection

Primary function:

- [suspicion_of_infection.py](/Users/chloe/Documents/New project/autoformalized_library/functions/suspicion_of_infection.py)

Current runtime exposure:

- [query_suspicion_of_infection](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:279)

What the function gives us:

- `has_suspicion_of_infection`
- culture orders
- antibiotic administrations
- treatment-pattern logic

Why it fits:

- the output is already a disease-level monitoring head
- the function includes real filtering logic for screening cultures and prophylaxis
- the runtime adapter already extracts evidence and first visible time

Gaps:

- the function gives an overall suspicion flag, not a benchmark-native `suspect` versus `alert` state
- the benchmark still needs to freeze how weak evidence versus established evidence is mapped

Verdict:

- good benchmark task
- adapter plus thin task contract
- no derived-table rewrite needed

## 2. Sepsis

Candidate direct function:

- [sepsis3.py](/Users/chloe/Documents/New project/autoformalized_library/functions/sepsis3.py)

Current runtime exposure:

- no `query_sepsis3` in [AUTOFORM_TOOL_TO_FUNCTION](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:11)

Why direct use is not safe:

- the file calls `get_suspicion_of_infection`, `first_day_sofa`, and `compute_sofa_score` directly at [sepsis3.py](/Users/chloe/Documents/New project/autoformalized_library/functions/sepsis3.py:51), [sepsis3.py](/Users/chloe/Documents/New project/autoformalized_library/functions/sepsis3.py:55), and [sepsis3.py](/Users/chloe/Documents/New project/autoformalized_library/functions/sepsis3.py:59)
- those helpers are not defined in the file itself
- the runtime executes one generated file at a time, so this is not benchmark-safe as a standalone function
- the semantics are also not ideal for rolling monitoring because they rely on baseline-versus-worst logic rather than a frozen checkpoint contract

Best replacement:

- compose `sepsis` from:
  - [query_suspicion_of_infection](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:279)
  - [query_sofa](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:332)

Verdict:

- keep `sepsis` in the benchmark
- do not use direct `sepsis3.py`
- requires composed task contract

## 3. AKI

Primary function:

- [kdigo_stages.py](/Users/chloe/Documents/New project/autoformalized_library/functions/kdigo_stages.py)

Current runtime exposure:

- [query_kdigo_stage](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:352)

What the function gives us:

- creatinine-based KDIGO stage
- urine-output-based KDIGO stage
- overall KDIGO stage
- stage 2+ and stage 3+ flags

Why it fits:

- it already returns a clean stage-like output
- the runtime adapter already maps it into benchmark AKI state fields
- it is one of the closest functions to a benchmark-ready task

Gaps:

- baseline creatinine strategy is autoformalized-specific, not official-derived
- that is acceptable for this benchmark, but must be frozen and documented

Verdict:

- strong benchmark task
- adapter is almost enough by itself
- thin contract for stage-to-action mapping

## 4. Oliguria

Primary function:

- [urine_output_rate.py](/Users/chloe/Documents/New project/autoformalized_library/functions/urine_output_rate.py)

Current runtime exposure:

- [query_urine_output_rate](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:398)

What the function gives us:

- `min_6hr_rate_mL_kg_hr`
- `has_oliguria`
- `has_severe_oliguria`

Why it is promising:

- it is explicitly designed around urine-output-rate monitoring
- it returns the exact kinds of summary fields a benchmark can use

Main gap:

- the boolean flags are based on `valid_rates` from time differences between output records, while the 6-hour rolling rate is a separate summary
- so "oliguria" here is not automatically the same as a strict KDIGO 6-hour or 12-hour duration contract

Best benchmark approach:

- keep oliguria as its own head
- freeze the benchmark contract around the returned summaries, especially `min_6hr_rate_mL_kg_hr`
- do not pretend it is the same thing as official urine-output derived SQL

Verdict:

- keep in benchmark
- not pure adapter-only for gold labels
- still fully viable without derived-table rewrite

## 5. Respiratory Support

Primary function:

- [ventilation.py](/Users/chloe/Documents/New project/autoformalized_library/functions/ventilation.py)

Current runtime exposure:

- [query_ventilation_status](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:377)

What the function gives us:

- invasive ventilation flag
- non-invasive ventilation flag
- HFNC flag
- oxygen-delivery-device details

Why it fits:

- the monitoring head is naturally intervention-based
- the runtime already converts outputs into:
  - low support
  - high-flow or NIV
  - invasive ventilation

Main gap:

- the function is best for support-state categorization, not etiology
- that is fine because this benchmark should monitor support escalation, not ARDS as a diagnosis

Verdict:

- strong benchmark task
- adapter plus frozen support-level contract

## 6. Vasoactive Support

Primary function:

- [vasoactive_agent.py](/Users/chloe/Documents/New project/autoformalized_library/functions/vasoactive_agent.py)

Current runtime exposure:

- [query_vasoactive_agent](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:413)

What the function gives us:

- whether any vasoactive agent was received
- which agents were given
- timing summaries

Why it fits:

- it is already a clinically meaningful ICU support head
- the function is simple and stable

Main gap:

- the raw output is closer to "ever exposed by this checkpoint" than a richly modeled current hemodynamic state
- if we want precise "active shock" semantics, we would need more than this function alone

Best benchmark framing:

- use it as `vasoactive_support`, not as `shock`

Verdict:

- strong benchmark task
- adapter plus thin task contract

## 7. Neurologic Deterioration

Primary function:

- [gcs.py](/Users/chloe/Documents/New project/autoformalized_library/functions/gcs.py)

Current runtime exposure:

- [query_gcs](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:473)

What the function gives us:

- `min_gcs`
- `min_gcs_all`
- severe impairment flag
- verbal-unresponsive flag

Why it fits:

- this is already a monitoring-oriented neurologic summary
- the function explicitly tries to separate non-intubated and all-period minima

Main gap:

- sedation and intubation still make the head noisier than AKI or ventilation

Best benchmark framing:

- keep it as `neurologic_deterioration`
- document the sedation/intubation caveat
- do not oversell it as a perfect coma phenotype

Verdict:

- keep in benchmark
- adapter plus thin task contract

## 8. Hyperlactatemia

Primary function:

- [bg.py](/Users/chloe/Documents/New project/autoformalized_library/functions/bg.py)

Current runtime exposure:

- [query_bg](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:452)

What the function gives us:

- `peak_lactate`
- elevated-lactate flag
- all measurements

Why it fits:

- lactate is naturally threshold-based
- the output already exposes the needed summary

Main gap:

- the function mixes ICU chart events and hospital lab events, so this is not a purely stay-native head
- for this benchmark that is acceptable if documented

Verdict:

- strong benchmark task
- adapter plus frozen threshold contract

## 9. Severe Acidemia

Primary function:

- [bg.py](/Users/chloe/Documents/New project/autoformalized_library/functions/bg.py)

Current runtime exposure:

- [query_bg](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:452)

What the function gives us:

- `min_pH`
- acidosis and severe-acidosis flags

Why it fits:

- it is a clean threshold task
- it is already naturally rolling and checkpoint-compatible

Main gap:

- the same admission-level caveat as blood-gas and lactate tasks

Verdict:

- strong benchmark task
- adapter plus frozen threshold contract

## 10. Coagulopathy

Primary function:

- [coagulation.py](/Users/chloe/Documents/New project/autoformalized_library/functions/coagulation.py)

Current runtime exposure:

- not exposed yet in [AUTOFORM_TOOL_TO_FUNCTION](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:11)

What the function gives us:

- INR summary
- PTT summary
- all coagulation values

Why it fits:

- INR/PTT are clean lab-based monitoring outputs
- the function is simple enough that an adapter layer should be straightforward

Main gap:

- the benchmark runtime does not expose it yet
- the function uses ICU `chartevents`, so its coverage and semantics are not identical to the earlier derived-table feasibility report that looked at hospital-level coagulation measurements

Verdict:

- keep as task 10
- add `query_coagulation`
- document that this is an autoformalized coagulation head, not the official derived-table coagulation label

## 11. CRRT

Primary function:

- [crrt.py](/Users/chloe/Documents/New project/autoformalized_library/functions/crrt.py)

Current runtime exposure:

- not exposed yet in [AUTOFORM_TOOL_TO_FUNCTION](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py:11)

What the function gives us:

- whether CRRT was received
- whether it was active
- clotting and filter details

Why it fits:

- it is clinically meaningful
- the function output is surprisingly well structured

Main gap:

- prevalence is low
- CRRT behaves more like a rescue or advanced-support head than a general surveillance head

Verdict:

- useful optional task
- not recommended for the core 10

## Final Recommendations

## Final benchmark task list

Recommended core 10:

1. `infection`
2. `sepsis` using infection + SOFA composition
3. `aki`
4. `oliguria`
5. `respiratory_support`
6. `vasoactive_support`
7. `neurologic_deterioration`
8. `hyperlactatemia`
9. `severe_acidemia`
10. `coagulopathy`

Optional task 11:

11. `crrt`

## Final function list

Trajectory-level retrieval candidates:

- `suspicion_of_infection`
- `sofa`
- `kdigo_stages`
- `urine_output_rate`
- `ventilation`
- `vasoactive_agent`
- `bg`
- `gcs`
- `coagulation`
- `crrt`

Step-level evidence tools:

- `query_suspicion_of_infection`
- `query_sofa`
- `query_kdigo_stage`
- `query_urine_output_rate`
- `query_ventilation_status`
- `query_vasoactive_agent`
- `query_bg`
- `query_gcs`
- `query_coagulation` to add
- `query_crrt` optional to add

## Bottom line on dataset curation

The benchmark can be fully autoformalized-native.

But the stable dataset design is:

- autoformalized functions as the concept source
- benchmark adapters as the evidence interface
- frozen benchmark contracts as the gold-label layer

That is the right compromise.

It keeps the benchmark faithful to the toolbox without forcing us to trust every raw generated function as a complete benchmark definition by itself.
