# Final Benchmark Feasibility Report

## Purpose

This note checks whether the proposed final benchmark design is feasible under:

- ICU LOS `>= 24h`
- deterministic `subject_id` split
- benchmark-visible event definitions within `t = 0..24h`

This report is the bridge between:

- the source-cohort statistics in [final_benchmark_source_statistics.md](/Users/chloe/Documents/New project/docs/final_benchmark_source_statistics.md)
- the target design in [final_benchmark_design_spec.md](/Users/chloe/Documents/New project/docs/final_benchmark_design_spec.md)

## Split Rule

Deterministic split assignment:

- `train` if `MOD(hash(subject_id), 20) < 14`
- `dev` if `MOD(hash(subject_id), 20) < 17`
- `test` otherwise

Resulting split sizes in the common source cohort:

| Split | Eligible ICU stays |
|---|---:|
| `train` | 52,589 |
| `dev` | 11,239 |
| `test` | 11,001 |

## Benchmark-Visible Stratum Rule

For feasibility, strata were recomputed using only events visible within the benchmark window:

- present by `t=0`
- or first visible by `t=24`

This is stricter than “ever during the ICU stay”.

That stricter definition is the right one for final benchmark generation, because otherwise some sampled “positive” stays would never transition during the 24-hour task.

## Proposed Split Targets

### Standard 2,000-trajectory datasets

For single-task and non-monotonic datasets targeting `2,000` trajectories:

- `train`: `1,400`
- `dev`: `300`
- `test`: `300`

### Multitask

For multitask targeting `2,048` trajectories with `256` per cell:

- exact `70/15/15` is not compatible with perfectly equal `256`-sized cells
- the cleanest implementation is to prioritize exact cell balance and accept a near-70/15/15 split

## Dataset 1: Sepsis Feasibility

### Feasibility Strata

Within-horizon leaf strata:

- `no_infection_no_sofa`
- `infection_only_no_sofa2`
- `sofa2_only_no_infection`
- `infection_and_sofa_but_not_sepsis3`
- `infection_and_sepsis3_onset_sofa_2_3`
- `infection_and_sepsis3_onset_sofa_4_plus`

### Available Counts by Split

| Split | Stratum | Available |
|---|---|---:|
| `train` | `no_infection_no_sofa` | 6,399 |
| `train` | `infection_only_no_sofa2` | 3,425 |
| `train` | `sofa2_only_no_infection` | 15,243 |
| `train` | `infection_and_sofa_but_not_sepsis3` | 3,766 |
| `train` | `infection_and_sepsis3_onset_sofa_2_3` | 13,700 |
| `train` | `infection_and_sepsis3_onset_sofa_4_plus` | 10,056 |
| `dev` | `no_infection_no_sofa` | 1,402 |
| `dev` | `infection_only_no_sofa2` | 722 |
| `dev` | `sofa2_only_no_infection` | 3,283 |
| `dev` | `infection_and_sofa_but_not_sepsis3` | 782 |
| `dev` | `infection_and_sepsis3_onset_sofa_2_3` | 2,910 |
| `dev` | `infection_and_sepsis3_onset_sofa_4_plus` | 2,140 |
| `test` | `no_infection_no_sofa` | 1,316 |
| `test` | `infection_only_no_sofa2` | 719 |
| `test` | `sofa2_only_no_infection` | 3,151 |
| `test` | `infection_and_sofa_but_not_sepsis3` | 778 |
| `test` | `infection_and_sepsis3_onset_sofa_2_3` | 2,960 |
| `test` | `infection_and_sepsis3_onset_sofa_4_plus` | 2,077 |

### Recommended Exact Quotas

To preserve the agreed 2,000 total:

| Split | Stratum | Target |
|---|---|---:|
| `train` | `no_infection_no_sofa` | 350 |
| `train` | `infection_only_no_sofa2` | 350 |
| `train` | `sofa2_only_no_infection` | 350 |
| `train` | `infection_and_sofa_but_not_sepsis3` | 175 |
| `train` | `infection_and_sepsis3_onset_sofa_2_3` | 88 |
| `train` | `infection_and_sepsis3_onset_sofa_4_plus` | 87 |
| `dev` | `no_infection_no_sofa` | 75 |
| `dev` | `infection_only_no_sofa2` | 75 |
| `dev` | `sofa2_only_no_infection` | 75 |
| `dev` | `infection_and_sofa_but_not_sepsis3` | 37 |
| `dev` | `infection_and_sepsis3_onset_sofa_2_3` | 19 |
| `dev` | `infection_and_sepsis3_onset_sofa_4_plus` | 19 |
| `test` | `no_infection_no_sofa` | 75 |
| `test` | `infection_only_no_sofa2` | 75 |
| `test` | `sofa2_only_no_infection` | 75 |
| `test` | `infection_and_sofa_but_not_sepsis3` | 38 |
| `test` | `infection_and_sepsis3_onset_sofa_2_3` | 18 |
| `test` | `infection_and_sepsis3_onset_sofa_4_plus` | 19 |

### Verdict

- fully feasible
- large safety margins in every split

## Dataset 2: AKI Escalation Feasibility

### Feasibility Strata

Within-horizon strata:

- `no_aki`
- `stage1_only`
- `stage23_early`
- `stage23_late`

Definitions:

- `no_aki`: no stage 1 by `t=24`
- `stage1_only`: stage 1 by `t=24`, no stage 2/3 by `t=24`
- `stage23_early`: first stage 2/3 by `t=12`
- `stage23_late`: first stage 2/3 in `(12, 24]`

### Available Counts by Split

| Split | Stratum | Available |
|---|---|---:|
| `train` | `no_aki` | 17,728 |
| `train` | `stage1_only` | 11,579 |
| `train` | `stage23_early` | 7,546 |
| `train` | `stage23_late` | 15,736 |
| `dev` | `no_aki` | 3,853 |
| `dev` | `stage1_only` | 2,442 |
| `dev` | `stage23_early` | 1,653 |
| `dev` | `stage23_late` | 3,291 |
| `test` | `no_aki` | 3,798 |
| `test` | `stage1_only` | 2,395 |
| `test` | `stage23_early` | 1,514 |
| `test` | `stage23_late` | 3,294 |

### Recommended Exact Quotas

| Split | Stratum | Target |
|---|---|---:|
| `train` | each of 4 strata | 350 |
| `dev` | each of 4 strata | 75 |
| `test` | each of 4 strata | 75 |

### Verdict

- fully feasible
- very large safety margins in every split

## Dataset 3: Respiratory Support Feasibility

### Original Path-Based Design

The original path-based design used:

- `low_only`
- `medium_only`
- `direct_invasive`
- `medium_then_invasive`

Under strict within-horizon definitions, that design was not feasible at the target scale because `medium_then_invasive` was too rare.

### Implemented Timing-Based Design

The final implemented respiratory strata are:

- `low_only`
- `medium_only`
- `invasive_early`
- `invasive_late`

Definitions:

- `low_only`: no benchmark medium support and no invasive support by `t=24`
- `medium_only`: medium support by `t=24`, no invasive support by `t=24`
- `invasive_early`: invasive support by `t=12`
- `invasive_late`: invasive support in `(12, 24]`

### Available Counts by Split

| Split | Stratum | Available |
|---|---|---:|
| `train` | `low_only` | 30,194 |
| `train` | `medium_only` | 1,696 |
| `train` | `invasive_early` | 19,519 |
| `train` | `invasive_late` | 1,180 |
| `dev` | `low_only` | 6,369 |
| `dev` | `medium_only` | 377 |
| `dev` | `invasive_early` | 4,226 |
| `dev` | `invasive_late` | 267 |
| `test` | `low_only` | 6,313 |
| `test` | `medium_only` | 348 |
| `test` | `invasive_early` | 4,107 |
| `test` | `invasive_late` | 233 |

### Recommended Exact Quotas

| Split | Stratum | Target |
|---|---|---:|
| `train` | each of 4 strata | 350 |
| `dev` | each of 4 strata | 75 |
| `test` | each of 4 strata | 75 |

### Verdict

- fully feasible
- implemented in the final package SQL

## Dataset 4: Multitask Feasibility

### Feasibility Definition

Within-horizon binary positives:

- sepsis positive: Sepsis-3 by `t=24`
- AKI positive: stage 2/3 by `t=24`
- respiratory positive: invasive support by `t=24`

### Available Counts by Split

| Split | Sepsis | AKI | Resp | Available |
|---|---:|---:|---:|---:|
| `train` | 1 | 1 | 1 | 7,287 |
| `train` | 1 | 1 | 0 | 5,682 |
| `train` | 1 | 0 | 1 | 5,779 |
| `train` | 1 | 0 | 0 | 5,756 |
| `train` | 0 | 1 | 1 | 3,404 |
| `train` | 0 | 1 | 0 | 6,909 |
| `train` | 0 | 0 | 1 | 4,229 |
| `train` | 0 | 0 | 0 | 13,543 |
| `dev` | 1 | 1 | 1 | 1,600 |
| `dev` | 1 | 1 | 0 | 1,155 |
| `dev` | 1 | 0 | 1 | 1,281 |
| `dev` | 1 | 0 | 0 | 1,180 |
| `dev` | 0 | 1 | 1 | 698 |
| `dev` | 0 | 1 | 0 | 1,491 |
| `dev` | 0 | 0 | 1 | 914 |
| `dev` | 0 | 0 | 0 | 2,920 |
| `test` | 1 | 1 | 1 | 1,482 |
| `test` | 1 | 1 | 0 | 1,189 |
| `test` | 1 | 0 | 1 | 1,263 |
| `test` | 1 | 0 | 0 | 1,242 |
| `test` | 0 | 1 | 1 | 700 |
| `test` | 0 | 1 | 0 | 1,437 |
| `test` | 0 | 0 | 1 | 895 |
| `test` | 0 | 0 | 0 | 2,793 |

### Recommended Exact Quotas

All 8 cells can support `256` stays each.

The cleanest implementation is:

- keep exact `256` per cell
- allow slight deviation from exact `70/15/15`

One simple target pattern:

- `180` train
- `38` dev
- `38` test

per cell, for:

- train total: `1,440`
- dev total: `304`
- test total: `304`

This preserves exact cell balance and stays close to the intended split ratio.

### Verdict

- fully feasible
- exact per-cell balancing is easy

## Dataset 5: Non-Monotonic AKI Feasibility

### Eligibility

Additional eligibility beyond the common cohort:

- a visible KDIGO stage at every checkpoint `0, 4, 8, 12, 16, 20, 24`

### Available Counts by Split

| Split | Path family | Available |
|---|---|---:|
| `train` | `stable_no_aki` | 14,860 |
| `train` | `stage1_progressive_or_persistent` | 5,019 |
| `train` | `stage1_recovery_or_fluctuating` | 4,783 |
| `train` | `stage2_progressive_or_persistent` | 12,156 |
| `train` | `stage2_recovery_or_fluctuating` | 3,565 |
| `train` | `stage3_progressive_or_persistent` | 2,198 |
| `train` | `stage3_recovery_or_fluctuating` | 2,273 |
| `dev` | `stable_no_aki` | 3,197 |
| `dev` | `stage1_progressive_or_persistent` | 1,070 |
| `dev` | `stage1_recovery_or_fluctuating` | 1,004 |
| `dev` | `stage2_progressive_or_persistent` | 2,571 |
| `dev` | `stage2_recovery_or_fluctuating` | 743 |
| `dev` | `stage3_progressive_or_persistent` | 467 |
| `dev` | `stage3_recovery_or_fluctuating` | 483 |
| `test` | `stable_no_aki` | 3,155 |
| `test` | `stage1_progressive_or_persistent` | 985 |
| `test` | `stage1_recovery_or_fluctuating` | 1,029 |
| `test` | `stage2_progressive_or_persistent` | 2,555 |
| `test` | `stage2_recovery_or_fluctuating` | 796 |
| `test` | `stage3_progressive_or_persistent` | 376 |
| `test` | `stage3_recovery_or_fluctuating` | 443 |

### Recommended Exact Quotas

For the proposed `2,000` total:

| Split | Path family | Target |
|---|---|---:|
| `train` | `stable_no_aki` | 175 |
| `train` | `stage1_progressive_or_persistent` | 175 |
| `train` | each of the five 300-target families | 210 |
| `dev` | `stable_no_aki` | 37 |
| `dev` | `stage1_progressive_or_persistent` | 37 |
| `dev` | each of the five 300-target families | 45 |
| `test` | `stable_no_aki` | 38 |
| `test` | `stage1_progressive_or_persistent` | 38 |
| `test` | each of the five 300-target families | 45 |

### Verdict

- fully feasible
- even the smallest severe families have comfortable safety margins

## Overall Conclusion

### Fully feasible as implemented

- sepsis
- AKI escalation
- respiratory support
- multitask
- non-monotonic AKI

All five final benchmark packages are now implementable under the horizon-consistent design.
