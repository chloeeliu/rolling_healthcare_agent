# Benchmark Source-Cohort Statistics

## Scope

This note summarizes the **full source-cohort distributions** behind the current rolling benchmark tasks, before any 100-stay or 96-stay benchmark sampling.

The goal is to answer:

- how common each task state or cluster is in MIMIC-IV
- how skewed the underlying source cohort is
- which intermediate states are naturally rare
- which cluster structure should drive final benchmark sampling

All counts below are **stay-level** unless otherwise noted.

## Cohort Definition

Base eligible cohort:

- source DB: `mimic4_dk.db`
- unit: ICU stay
- inclusion:
  - `mimiciv_icu.icustays.intime IS NOT NULL`
  - `mimiciv_icu.icustays.outtime IS NOT NULL`
  - ICU LOS `>= 24h`

Base eligible cohort size:

- eligible ICU stays: `74,829`

This is the denominator for the sepsis, AKI, respiratory, and multitask summaries below.

For the non-monotonic AKI checkpoint-path analysis, there is one additional filter:

- a visible KDIGO stage must be available at every checkpoint `t = 0, 4, 8, 12, 16, 20, 24`

That fully observed non-monotonic AKI cohort has:

- fully observed stays: `63,728`

## Current Benchmark Package Sizes

For reference, the current packaged benchmark cohorts are much smaller and intentionally rebalanced:

| Dataset | Trajectories |
|---|---:|
| single-task sepsis | 100 |
| single-task AKI | 100 |
| single-task respiratory support | 100 |
| multitask | 96 |
| non-monotonic AKI | 100 |

So the tables below should be read as **source distributions**, not current benchmark distributions.

## Sepsis Source Statistics

### Definitions

Sepsis-related clusters were defined from:

- suspected infection onset: `mimiciv_derived.suspicion_of_infection`
- any SOFA-2+ event: earliest `mimiciv_derived.sofa.endtime` with `sofa_24hours >= 2`
- Sepsis-3 onset: `mimiciv_derived.sepsis3`

Cluster definitions:

- `neither_infection_nor_sofa2`: no suspected infection and no SOFA-2+ event
- `infection_only`: suspected infection, but never any SOFA-2+ event
- `sofa2_only_no_infection`: SOFA-2+ event, but no suspected infection
- `infection_and_sofa2_but_not_sepsis3`: both components appear during the stay, but not in the Sepsis-3 temporal window
- `infection_and_sepsis3`: Sepsis-3 positive

### Audit of `mimiciv_derived.sepsis3`

The high sepsis prevalence is coming from the official derived table itself, not from us accidentally labeling any SOFA-2+ stay as sepsis.

Direct audit of the official table:

- all ICU stays in `mimiciv_icu.icustays`: `94,458`
- ICU stays with LOS `>= 24h`: `74,829`
- rows in `mimiciv_derived.sepsis3`: `41,296`
- distinct stays in `mimiciv_derived.sepsis3`: `41,296`
- distinct positive stays in `mimiciv_derived.sepsis3`: `41,296`

So the derived table is effectively one positive Sepsis-3 row per qualifying stay.

Sepsis-3 prevalence from the official derived concept:

- all ICU stays: `41,296 / 94,458` = `43.72%`
- ICU stays with LOS `>= 24h`: `37,143 / 74,829` = `49.64%`

This is high, but it is the official MIMIC derived concept as implemented in [MIMIC_concepts/sepsis/sepsis3.sql](/Users/chloe/Documents/New project/MIMIC_concepts/sepsis/sepsis3.sql).

That SQL does **not** define sepsis as “SOFA >= 2 only”.
It requires:

- suspected infection from `mimiciv_derived.suspicion_of_infection`
- an ICU SOFA row with `sofa_24hours >= 2`
- temporal overlap within the Sepsis-3 suspicion window
- one earliest qualifying row per stay

In other words, the official concept is:

- infection evidence
- plus SOFA increase threshold operationalized as ICU SOFA `>= 2`
- with the common MIMIC assumption that baseline SOFA before ICU is `0`

That last assumption is important. It is one reason this concept can be broad in ICU cohorts.

### Severity at Sepsis-3 Onset

For all positive rows in `mimiciv_derived.sepsis3`, onset SOFA score distribution is:

| Onset SOFA score | Stays |
|---|---:|
| `2` | 15,104 |
| `3` | 8,998 |
| `4-5` | 10,805 |
| `6-7` | 3,907 |
| `8+` | 2,482 |

Two useful summary views:

- onset SOFA exactly `2`: `15,104 / 41,296` = `36.58%`
- onset SOFA `2` or `3`: `24,102 / 41,296` = `58.36%`

So yes, the current sepsis-positive definition is fairly coarse for a benchmark.
Most official Sepsis-3 positives enter at low onset SOFA values.

### Cluster Frequencies

| Sepsis cluster | Stays | Percent |
|---|---:|---:|
| `infection_and_sepsis3` | 37,143 | 49.64% |
| `sofa2_only_no_infection` | 21,838 | 29.18% |
| `infection_and_sofa2_but_not_sepsis3` | 6,557 | 8.76% |
| `neither_infection_nor_sofa2` | 6,450 | 8.62% |
| `infection_only` | 2,841 | 3.80% |
| `sepsis3_without_infection` | 0 | 0.00% |

Headline prevalences:

- any suspected infection: `46,541 / 74,829` = `62.20%`
- any SOFA-2+ event: `65,538 / 74,829` = `87.58%`
- any Sepsis-3 event: `37,143 / 74,829` = `49.64%`

### Timing Within the First 24 Hours

| Metric | Present by `t=0` | `0-24h` | After `24h` | Never |
|---|---:|---:|---:|---:|
| infection start | 30,141 | 13,894 | 2,506 | 28,288 |
| sepsis3 start | 338 | 34,558 | 2,247 | 37,686 |

As percentages of the full eligible cohort:

- infection visible by `t=0`: `40.28%`
- infection first appears during `0-24h`: `18.57%`
- sepsis3 already present by `t=0`: `0.45%`
- sepsis3 first appears during `0-24h`: `46.18%`

### Interpretation

- The source cohort is **not** dominated by classic clean negatives.
- The nearly 50% prevalence in the LOS `>= 24h` cohort is coming from the official `mimiciv_derived.sepsis3` table itself.
- The current benchmark sepsis-positive flag is therefore not “SOFA-only”, but it is still a relatively broad and coarse operationalization for ICU benchmarking.
- The most common non-sepsis cluster is actually `sofa2_only_no_infection`, not `neither_infection_nor_sofa2`.
- `infection_only` is genuinely rare in the raw source cohort.
- The most benchmark-relevant ambiguous sepsis negatives are:
  - `sofa2_only_no_infection`
  - `infection_and_sofa2_but_not_sepsis3`

Those are the hard negatives we should preserve in the final cohort rather than just sampling “all non-sepsis” uniformly.

For the final benchmark, this suggests we should probably not treat all Sepsis-3 positives as one homogeneous positive bucket. A better sepsis sampling design would at least separate:

- infection only
- infection + SOFA without Sepsis-3 window match
- Sepsis-3 with onset SOFA `2-3`
- Sepsis-3 with onset SOFA `4+`
- early versus late Sepsis-3 onset within the 24h benchmark window

## AKI Source Statistics

### Definitions

AKI escalation statistics use `mimiciv_derived.kdigo_stages.aki_stage_smoothed`.

Stay-level buckets:

- `no_aki`: never reaches stage 1+
- `stage1_only`: reaches stage 1+, never reaches stage 2+
- `stage23`: reaches stage 2 or 3 at any point

### Bucket Frequencies

| AKI bucket | Stays | Percent |
|---|---:|---:|
| `stage23` | 47,794 | 63.87% |
| `no_aki` | 14,321 | 19.14% |
| `stage1_only` | 12,714 | 16.99% |

Headline prevalences:

- any stage 1+: `60,508 / 74,829` = `80.86%`
- any stage 2/3: `47,794 / 74,829` = `63.87%`

### Timing Within the First 24 Hours

| Metric | Present by `t=0` | `0-24h` | After `24h` | Never |
|---|---:|---:|---:|---:|
| stage 1 start | 12,616 | 36,834 | 11,058 | 14,321 |
| stage 2/3 start | 4,912 | 28,122 | 14,760 | 27,035 |

As percentages of the full eligible cohort:

- stage 1+ visible by `t=0`: `16.86%`
- stage 1+ first appears during `0-24h`: `49.22%`
- stage 2/3 visible by `t=0`: `6.56%`
- stage 2/3 first appears during `0-24h`: `37.58%`

### Interpretation

- In the raw ICU source cohort, severe AKI is common enough that a prevalence-faithful sample would be heavily positive.
- The main benchmark design problem for AKI is not “too few positives.” It is making sure the cohort still contains enough:
  - clean negatives
  - stage-1-only trajectories
  - early versus late stage-2/3 escalation

That supports keeping a stratified AKI design rather than sampling by prevalence alone.

## Respiratory Support Source Statistics

### Definitions

Respiratory escalation statistics use `mimiciv_derived.ventilation`.

Benchmark-facing buckets:

- `low_only`: never reaches benchmark medium support and never reaches invasive support
- `medium_only`: reaches benchmark medium support, never reaches invasive support
- `high_support`: reaches invasive support at any point

For invasive stays, I also split high-support trajectories into:

- `direct_invasive_no_prior_medium`
- `medium_then_invasive`
- `direct_invasive_or_same_time`

### Bucket Frequencies

| Respiratory bucket | Stays | Percent |
|---|---:|---:|
| `low_only` | 39,633 | 52.96% |
| `high_support` | 32,455 | 43.37% |
| `medium_only` | 2,741 | 3.66% |

### Invasive Path Structure

| Invasive-path cluster | Stays | Percent |
|---|---:|---:|
| `no_invasive` | 42,374 | 56.63% |
| `direct_invasive_no_prior_medium` | 29,867 | 39.91% |
| `direct_invasive_or_same_time` | 1,798 | 2.40% |
| `medium_then_invasive` | 790 | 1.06% |

### Timing Within the First 24 Hours

| Metric | Present by `t=0` | `0-24h` | After `24h` | Never |
|---|---:|---:|---:|---:|
| benchmark medium-support start | 196 | 2,496 | 839 | 71,298 |
| invasive-support start | 4,136 | 25,396 | 2,923 | 42,374 |

As percentages of the full eligible cohort:

- benchmark medium support visible by `t=0`: `0.26%`
- benchmark medium support first appears during `0-24h`: `3.34%`
- invasive support visible by `t=0`: `5.53%`
- invasive support first appears during `0-24h`: `33.94%`

### Interpretation

- The respiratory intermediate state is **extremely rare** in the source cohort.
- Most high-support stays go straight to invasive support without a prior benchmark-visible medium step.
- A prevalence-faithful respiratory cohort would severely underrepresent `high_flow_or_noninvasive_support`.

This strongly supports deliberate over-sampling of medium-support trajectories in the final benchmark.

## Multitask Combination Frequencies

For multitask benchmarking, the current repo defines binary positives as:

- sepsis positive: any Sepsis-3 event
- AKI positive: any stage 2/3 event
- respiratory positive: any invasive support event

Using those exact definitions on the full eligible cohort:

| Sepsis | AKI | Resp | Stays | Percent |
|---:|---:|---:|---:|---:|
| 1 | 1 | 1 | 17,429 | 23.29% |
| 1 | 1 | 0 | 10,081 | 13.47% |
| 1 | 0 | 1 | 4,759 | 6.36% |
| 1 | 0 | 0 | 4,874 | 6.51% |
| 0 | 1 | 1 | 6,288 | 8.40% |
| 0 | 1 | 0 | 13,996 | 18.70% |
| 0 | 0 | 1 | 3,979 | 5.32% |
| 0 | 0 | 0 | 13,423 | 17.94% |

### Interpretation

- The source multitask distribution is far from balanced.
- The largest source cluster is actually triple-positive.
- The pure negative corner is only `17.94%` of the eligible cohort.
- Some mixed-sign corners are naturally small, especially:
  - sepsis positive / AKI negative / respiratory positive
  - respiratory-only positive

So the current `12-per-cell` multitask design is doing real balancing work, not just mild adjustment.

## Non-Monotonic AKI Source Statistics

### Fully Observed Cohort Size

- fully observed at all checkpoints `0:4:24`: `63,728` stays

### Path-Family Frequencies

| Path family | Stays | Percent of fully observed cohort |
|---|---:|---:|
| `stable_no_aki` | 21,212 | 33.28% |
| `stage2_progressive_or_persistent` | 17,282 | 27.12% |
| `stage1_progressive_or_persistent` | 7,074 | 11.10% |
| `stage1_recovery_or_fluctuating` | 6,816 | 10.69% |
| `stage2_recovery_or_fluctuating` | 5,104 | 8.01% |
| `stage3_recovery_or_fluctuating` | 3,199 | 5.02% |
| `stage3_progressive_or_persistent` | 3,041 | 4.77% |

### Dynamics Summary

- any upward checkpoint change: `39,672` (`62.25%`)
- any downward checkpoint change: `15,119` (`23.72%`)
- both upward and downward change: `13,587` (`21.32%`)
- mean number of checkpoint-stage changes: `1.24`
- median number of checkpoint-stage changes: `1`

### Checkpoint Stage Distribution

At `t=0`:

- stage 0: `54,024` (`84.77%`)
- stage 1: `5,782` (`9.07%`)
- stage 2: `1,802` (`2.83%`)
- stage 3: `2,120` (`3.33%`)

At `t=24`:

- stage 0: `28,526` (`44.76%`)
- stage 1: `9,735` (`15.28%`)
- stage 2: `21,203` (`33.27%`)
- stage 3: `4,264` (`6.69%`)

### Most Common 0-24h Paths

| Path | Stays |
|---|---:|
| `0>0>0>0>0>0>0` | 21,212 |
| `0>0>0>1>2>2>2` | 2,733 |
| `0>0>1>1>2>2>2` | 2,606 |
| `0>0>0>0>0>0>1` | 2,160 |
| `0>0>0>0>0>1>1` | 2,160 |
| `0>0>0>0>1>2>2` | 1,782 |
| `0>0>0>1>1>2>2` | 1,561 |
| `0>0>0>0>1>1>1` | 1,069 |
| `0>0>0>0>0>1>2` | 1,021 |
| `0>0>0>0>1>1>0` | 953 |

### Interpretation

- The non-monotonic AKI source cohort is still dominated by stable stage 0 and progressive stage 2 paths.
- Recovery and fluctuation paths are common enough to justify the task, but not common enough to dominate a prevalence-faithful sample.
- The current seven-family stratification is well motivated if the goal is to benchmark state tracking rather than prevalence estimation.

## What These Statistics Suggest for Final Cohort Design

These source distributions strongly suggest that the final benchmark should remain **stratified and benchmark-oriented**, not prevalence-faithful.

Key reasons:

- Sepsis negatives are heterogeneous, and the hardest negative mass is `sofa2_only_no_infection`, not clean normal stays.
- AKI positives are too common in the raw cohort for prevalence sampling to give a balanced escalation benchmark.
- Respiratory intermediate support is too rare for prevalence sampling to test the middle label well.
- Multitask source frequencies are highly uneven, so balanced combination sampling is justified.
- Non-monotonic AKI recovery/fluctuation paths are clinically meaningful but underrepresented without explicit over-sampling.

So the next design step should be:

- preserve source-informed cluster definitions
- sample within those clusters deliberately
- avoid “include all negatives” thinking
- instead target enough negatives of the **right type**

The sepsis source cohort in particular argues for at least separating negatives into:

- `neither_infection_nor_sofa2`
- `sofa2_only_no_infection`
- `infection_and_sofa2_but_not_sepsis3`

rather than treating all non-sepsis stays as one bucket.
