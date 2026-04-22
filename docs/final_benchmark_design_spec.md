# Final Benchmark Design Specification

## Purpose

This document defines the proposed final benchmark design for the rolling ICU monitoring benchmark.

This is a **planning spec**, not the implementation.
It records the agreed high-level decisions before generating SQL, CSV exports, or runner-facing packages.

The benchmark should be:

- clinically structured rather than prevalence-faithful
- deterministic and reproducible
- large enough for paper-quality evaluation
- aligned across single-task, multitask, and non-monotonic settings

## Design Principles

### 1. Sample across clinically meaningful clusters

We will not sample to match raw MIMIC prevalence.

Instead, we will sample across clinically relevant strata so the benchmark:

- contains enough positives and negatives
- contains enough hard negatives
- preserves intermediate states
- tests timing and longitudinal state tracking

### 2. Use one common source cohort definition

Unless otherwise noted, all benchmark datasets will be derived from the same base ICU cohort:

- source table: `mimiciv_icu.icustays`
- ICU `intime IS NOT NULL`
- ICU `outtime IS NOT NULL`
- ICU LOS `>= 24h`

This keeps the benchmark internally consistent across tasks.

### 2a. Define strata using benchmark-visible events

Unless explicitly stated otherwise, cluster membership should be defined using what is visible within the benchmark horizon:

- present by `t=0`
- or first visible during `(0, 24]`

Events that first occur after `t=24` should not define a positive or intermediate stratum for the 24-hour benchmark.

Reason:

- if a transition happens only after `t=24`, the trajectory is benchmark-negative during the actual task window
- using such stays to define positive strata would make the sampling logic and label semantics inconsistent

### 3. Split by `subject_id`, not by `stay_id`

All train/dev/test splits will be defined at the patient level:

- no patient may appear in more than one split
- all stays for a subject belong to one split only

This prevents information leakage across repeated ICU stays for the same patient.

### 4. Deterministic sampling

All selections should be deterministic:

- use stable subject-level split assignment
- use `ORDER BY hash(stay_id)` or equivalent stable ranking within stratum
- avoid `RANDOM()` in final benchmark generation

This is required for reproducibility.

### 5. Benchmark size target

Target benchmark scale:

- about `2,000` trajectories per single-task dataset
- about `2,048` trajectories for multitask
- about `2,000` trajectories for non-monotonic AKI

This is large enough to support paper evaluation while still being practical to run.

## Shared Structural Contract

All datasets will retain the current benchmark structure unless explicitly changed later:

- anchor: `icu_intime`
- checkpoint grid: `0, 4, 8, 12, 16, 20, 24`
- horizon: `24h`
- one row per stay per checkpoint in exported CSV

Current label-space contracts remain unchanged for now:

- sepsis escalation:
  - `keep_monitoring`
  - `infection_suspect`
  - `trigger_sepsis_alert`
- AKI escalation:
  - `keep_monitoring`
  - `suspect_aki`
  - `trigger_aki_alert`
- respiratory escalation:
  - `room_air_or_low_support`
  - `high_flow_or_noninvasive_support`
  - `invasive_vent_required`
- non-monotonic AKI state tracking:
  - `no_aki`
  - `aki_stage_1`
  - `aki_stage_2`
  - `aki_stage_3`

## Split Policy

Recommended split:

- train: `70%`
- dev: `15%`
- test: `15%`

Target counts for a 2,000-trajectory dataset:

- train: `1,400`
- dev: `300`
- test: `300`

Target counts for the 2,048 multitask dataset:

- train: `1,434`
- dev: `307`
- test: `307`

Implementation rule:

- assign each `subject_id` to a split deterministically using hash-based partitioning
- then sample each stratum separately within each split

This keeps split distributions stable and avoids post-hoc leakage fixes.

## Dataset 1: Single-Task Sepsis

### Goal

Create a sepsis benchmark that is balanced across clinically meaningful negative, ambiguous, and positive patterns rather than only “sepsis vs non-sepsis”.

### Source Concepts

- suspected infection: `mimiciv_derived.suspicion_of_infection`
- SOFA: `mimiciv_derived.sofa`
- Sepsis-3: `mimiciv_derived.sepsis3`

### Macro-Clusters

Use four top-level clinical clusters:

1. `no_infection_no_sofa`
   - no suspected infection
   - no SOFA-2+ event

2. `infection_only_no_sofa2`
   - suspected infection
   - no SOFA-2+ event

3. `sofa2_only_no_infection`
   - SOFA-2+ event
   - no suspected infection

4. `infection_and_sofa`
   - both infection and SOFA are present during the stay

### Sepsis Internal Refinement

The `infection_and_sofa` group is too broad for direct use.
It should be split internally into:

- `infection_and_sofa_but_not_sepsis3`
- `infection_and_sepsis3`

And the Sepsis-3-positive group should be balanced by onset severity:

- onset SOFA `2-3`
- onset SOFA `4+`

And when feasible, we should also balance timing:

- evidence already visible by `t=0`
- first clinically relevant transition appears during `0-24h`

### Proposed Quotas

Top-level target:

- `500` `no_infection_no_sofa`
- `500` `infection_only_no_sofa2`
- `500` `sofa2_only_no_infection`
- `500` `infection_and_sofa`

Internal target for `infection_and_sofa`:

- `250` `infection_and_sofa_but_not_sepsis3`
- `250` `infection_and_sepsis3`

Internal target for `infection_and_sepsis3`:

- about `125` onset SOFA `2-3`
- about `125` onset SOFA `4+`

### Why This Design

This prevents the sepsis benchmark from collapsing into:

- mostly easy negatives
- mostly broad low-threshold positives

It explicitly preserves:

- clean negatives
- hard physiologic negatives
- infection-only surveillance cases
- coarse but still clinically meaningful Sepsis-3 positives

## Dataset 2: Single-Task AKI Escalation

### Goal

Create an AKI onset/escalation dataset that preserves clean negatives, stage-1-only trajectories, and both early and late severe escalation.

### Source Concept

- `mimiciv_derived.kdigo_stages`
- hidden severity source: `aki_stage_smoothed`

### Strata

Use four strata:

1. `no_aki`
   - no stage 1+ event

2. `stage1_only`
   - reaches stage 1+
   - never reaches stage 2+

3. `stage23_early`
   - first visible stage 2/3 by `t=12`

4. `stage23_late`
   - first visible stage 2/3 in `(12, 24]`

### Proposed Quotas

- `500` `no_aki`
- `500` `stage1_only`
- `500` `stage23_early`
- `500` `stage23_late`

### Why This Design

This preserves the main clinically relevant escalation patterns:

- no AKI
- mild-only AKI
- early severe AKI
- late severe AKI

It also keeps the single-task dataset aligned with the benchmark’s 24-hour monitoring horizon.

## Dataset 3: Single-Task Respiratory Support

### Goal

Create a respiratory benchmark that preserves the intermediate support state while also separating early versus delayed invasive escalation within the 24-hour benchmark window.

### Source Concept

- `mimiciv_derived.ventilation`

### Strata

Use four strata:

1. `low_only`
   - never reaches benchmark medium support
   - never reaches invasive support

2. `medium_only`
   - reaches benchmark medium support
   - never reaches invasive support

3. `invasive_early`
   - reaches invasive support by `t=12`

4. `invasive_late`
   - reaches invasive support in `(12, 24]`

### Proposed Quotas

- `500` `low_only`
- `500` `medium_only`
- `500` `invasive_early`
- `500` `invasive_late`

### Why This Design

The source cohort shows that benchmark-visible medium support is rare.
The original path-based fourth stratum (`medium_then_invasive`) was too sparse inside the actual `0-24h` task window.

The timing-based invasive split keeps the benchmark:

- horizon-consistent
- large enough to reach about `2,000` trajectories
- still clinically meaningful

Without deliberate over-sampling, the middle label would still be too sparse for serious evaluation.

This design protects:

- the intermediate respiratory state
- early invasive escalation
- delayed invasive escalation

## Dataset 4: Multitask Shared Cohort

### Goal

Create a shared multitask cohort that is easy to explain, balanced across co-occurrence patterns, and directly comparable across multitask systems.

### Binary Positive Definitions

Use the current benchmark definitions:

- sepsis positive: any Sepsis-3 event
- AKI positive: any stage 2/3 event
- respiratory positive: any invasive support event

### Cells

Use the full `2 x 2 x 2` combination design:

- `sepsis +/-`
- `AKI +/-`
- `respiratory +/-`

Total cells:

- `8`

### Proposed Quotas

- `256` stays per cell
- total: `2,048`

### Soft Internal Balancing

Within each cell, balance opportunistically when feasible:

- sepsis timing: early vs late
- AKI timing: early vs late
- respiratory path: direct invasive vs prior medium when relevant

This is a soft objective, not a hard requirement.

### Why This Design

This preserves the strongest feature of the current multitask benchmark:

- easy-to-explain co-occurrence balancing

At the same time, it scales the cohort to paper-ready size.

## Dataset 5: Non-Monotonic AKI State Tracking

### Goal

Create a large current-state AKI tracking dataset that preserves worsening, recovery, and fluctuation patterns across checkpoint paths.

### Eligibility

Use the current fully observed checkpoint-path design:

- LOS `>= 24h`
- a visible KDIGO state at every checkpoint `0:4:24`

### Path Families

Use the current seven-family taxonomy:

1. `stable_no_aki`
2. `stage1_progressive_or_persistent`
3. `stage1_recovery_or_fluctuating`
4. `stage2_progressive_or_persistent`
5. `stage2_recovery_or_fluctuating`
6. `stage3_progressive_or_persistent`
7. `stage3_recovery_or_fluctuating`

### Proposed Quotas

Recommended final allocation:

- `250` `stable_no_aki`
- `250` `stage1_progressive_or_persistent`
- `300` `stage1_recovery_or_fluctuating`
- `300` `stage2_progressive_or_persistent`
- `300` `stage2_recovery_or_fluctuating`
- `300` `stage3_progressive_or_persistent`
- `300` `stage3_recovery_or_fluctuating`

Total:

- `2,000`

### Why This Design

This keeps:

- a negative anchor
- mild progressive trajectories
- recovery and fluctuation patterns
- severe and clinically awkward trajectories

It slightly upweights the harder state-tracking families without making the cohort unnatural.

## Benchmark Generation Workflow

Implementation should proceed in this order:

1. Build deterministic subject-level split assignments.
2. Compute source-cluster membership for every eligible stay.
3. Check per-split feasibility for every target quota.
4. Sample within split and stratum using deterministic ranking.
5. Export split-specific CSV datasets.
6. Export summary tables for:
   - source counts
   - sampled counts
   - per-split counts
   - timing/severity summaries where relevant

## Expected Output Structure

For each dataset, generate:

- dataset SQL used for export
- CSV package
- trajectory schema
- summary stats CSV or Markdown report

Expected benchmark package families:

- `rolling_monitor_dataset/sepsis_final`
- `rolling_monitor_dataset/aki_final`
- `rolling_monitor_dataset/respiratory_support_final`
- `rolling_monitor_dataset/multitask_final`
- `rolling_monitor_dataset/aki_non_monotonic_final`

Exact folder names can be adjusted later, but the generation logic should be versioned and separated from the current 100-sample packages.

## Confirmation Points

The following decisions are now treated as the default proposed design:

- use LOS `>= 24h` as the common source cohort
- split by `subject_id`
- deterministic sampling only
- target about `2,000` trajectories per single-task dataset
- target `2,048` for multitask
- use clinically relevant strata rather than prevalence sampling
- keep current label spaces unchanged for this benchmark iteration

## Next Step

After review of this document, the next step is to implement:

- split assignment logic
- feasibility audits for each proposed stratum and split
- dataset SQL for each final benchmark package

That implementation should happen only after this design spec is confirmed.
