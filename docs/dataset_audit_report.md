# Longitudinal Healthcare Agent Dataset Audit

## Scope

This report audits the curated rolling-monitoring datasets under:

- `/Users/chloe/Documents/New project/rolling_monitor_dataset/sepsis`
- `/Users/chloe/Documents/New project/rolling_monitor_dataset/aki`
- `/Users/chloe/Documents/New project/rolling_monitor_dataset/respiratory_support`
- `/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask`

The goal is to compare the revised single-task cohorts with the shared multitask cohort and highlight what is aligned, what still differs, and what those differences mean for healthcare longitudinal-agent evaluation.

## Executive Summary

The sepsis package is now aligned with the other task packages in the most important benchmark-facing ways:

- DuckDB-native SQL
- 3-state escalation labels
- 4-hour checkpoints over a 24-hour horizon
- pre-ICU evidence snapped to `t=0` rather than represented as negative hours

That revision substantially improves consistency across the project.

The strongest current findings are:

1. The three single-task datasets now match structurally.
   Sepsis, AKI, and respiratory support are all 3-state escalation tasks on the same checkpoint grid.

2. The multitask cohort is still a separately curated sample, not a matched subset of the single-task cohorts.
   That means single-task vs multitask comparisons still mix task-load effects with cohort-sampling effects.

3. Sepsis now aligns much better with the multitask formulation.
   In the revised single-task sepsis dataset, 49 of 100 stays are already `infection_suspect` at `t=0`, close to the multitask sepsis head where 42 of 96 stays are already non-baseline at `t=0`.

4. AKI remains the most stable task when moving from single-task to multitask.
   Its intermediate state remains visible and meaningful in both settings.

5. Respiratory support remains the most compressed task in multitask mode.
   Only 7 of 96 multitask stays ever enter `high_flow_or_noninvasive_support`, so the multitask respiratory head behaves much more like low-vs-invasive than a full 3-state ladder.

## Current Dataset Inventory

| Dataset | Stays | Rows | Checkpoints/Stay | Label Space |
|---|---:|---:|---:|---|
| Sepsis single-task | 100 | 700 | 7 | `keep_monitoring`, `infection_suspect`, `trigger_sepsis_alert` |
| AKI single-task | 100 | 700 | 7 | `keep_monitoring`, `suspect_aki`, `trigger_aki_alert` |
| Respiratory single-task | 100 | 700 | 7 | `room_air_or_low_support`, `high_flow_or_noninvasive_support`, `invasive_vent_required` |
| Multitask | 96 | 672 | 7 | sepsis 3-state + AKI 3-state + respiratory 3-state |

All four datasets use:

- anchor: `icu_intime`
- checkpoints: `0, 4, 8, 12, 16, 20, 24`
- horizon: 24 hours

## Cohort Construction Summary

### Sepsis single-task

From `/Users/chloe/Documents/New project/rolling_monitor_dataset/sepsis/dataset_sql.sql`:

- 50 sepsis stays
- 50 non-sepsis stays
- sampled deterministically by `hash(stay_id)` within each class
- sepsis-positive stays are filtered to the strict 3-state contract:
  `infection_start_time <= sepsis_start_time`

Label rule:

- `keep_monitoring`
- `infection_suspect`
- `trigger_sepsis_alert`

Important revision:

- evidence before ICU admission is now snapped to `t=0` using `GREATEST(0, ...)`
- `organ_dysfunction_suspect` has been removed
- the SQL is now DuckDB-native

### AKI single-task

From `/Users/chloe/Documents/New project/rolling_monitor_dataset/aki/dataset_sql.sql`:

- 34 no-AKI stays
- 33 stage-1-only stays
- 33 stage-2-or-3 stays

Label rule:

- `keep_monitoring`
- `suspect_aki`
- `trigger_aki_alert`

### Respiratory single-task

From `/Users/chloe/Documents/New project/rolling_monitor_dataset/respiratory_support/dataset_sql.sql`:

- 34 low-only stays
- 33 medium-only stays
- 33 high-support stays

Label rule:

- `room_air_or_low_support`
- `high_flow_or_noninvasive_support`
- `invasive_vent_required`

### Multitask

From `/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask/dataset_sql.sql`:

- 12 stays from each binary combination of:
  - sepsis positive / negative
  - AKI stage-2-or-3 positive / negative
  - invasive respiratory support positive / negative
- total: 96 stays

This remains a balanced co-occurrence design rather than a direct union of the single-task cohorts.

## Revised Single-Task Cohort Findings

### Sepsis single-task

Top-line stats:

- stays: 100
- rows: 700
- prevalence: 50 sepsis / 50 non-sepsis
- label counts:
  - `keep_monitoring`: 285
  - `infection_suspect`: 143
  - `trigger_sepsis_alert`: 272

Checkpoint distribution:

| t_hour | keep_monitoring | infection_suspect | trigger_sepsis_alert |
|---:|---:|---:|---:|
| 0 | 51 | 49 | 0 |
| 4 | 39 | 23 | 38 |
| 8 | 39 | 18 | 43 |
| 12 | 39 | 15 | 46 |
| 16 | 39 | 13 | 48 |
| 20 | 39 | 13 | 48 |
| 24 | 39 | 12 | 49 |

Transition-hour summary at `t=0` row per stay:

- `infection_start_hour = 0`: 49 stays
- `infection_start_hour = 4`: 12 stays
- no infection transition in-window or observed: 39 stays

- `sepsis_start_hour = 4`: 38 stays
- `sepsis_start_hour = 8`: 5 stays
- `sepsis_start_hour = 12`: 3 stays
- `sepsis_start_hour = 16`: 2 stays
- `sepsis_start_hour = 24`: 1 stay
- `sepsis_start_hour = 64`: 1 stay
- no sepsis transition in-window or observed: 50 stays

Interpretation:

- The revised sepsis cohort is much cleaner than the earlier four-state version.
- The intermediate `infection_suspect` state is now substantial rather than sparse.
- 49% of stays are already non-baseline at `t=0`, which is a realistic and important property for a rolling-monitoring benchmark.
- Negative pre-ICU hours are gone by design, so the dataset now matches the multitask convention more closely.
- The revised CSV now passes the strict pipeline contract without skipped trajectories.

### AKI single-task

Top-line stats:

- stays: 100
- rows: 700
- stay buckets:
  - `no_aki`: 34
  - `stage1_only`: 33
  - `stage23`: 33
- label counts:
  - `keep_monitoring`: 456
  - `suspect_aki`: 168
  - `trigger_aki_alert`: 76

Checkpoint distribution:

| t_hour | keep_monitoring | suspect_aki | trigger_aki_alert |
|---:|---:|---:|---:|
| 0 | 91 | 8 | 1 |
| 4 | 82 | 14 | 4 |
| 8 | 71 | 24 | 5 |
| 12 | 64 | 29 | 7 |
| 16 | 57 | 26 | 17 |
| 20 | 47 | 32 | 21 |
| 24 | 44 | 35 | 21 |

Interpretation:

- This remains the cleanest single-task escalation cohort.
- The intermediate state is persistent and clinically meaningful.
- The task is neither too front-loaded nor too terminal-heavy.

### Respiratory single-task

Top-line stats:

- stays: 100
- rows: 700
- stay buckets:
  - `low_only`: 34
  - `medium_only`: 33
  - `high`: 33
- label counts:
  - `room_air_or_low_support`: 436
  - `high_flow_or_noninvasive_support`: 102
  - `invasive_vent_required`: 162

Checkpoint distribution:

| t_hour | room_air_or_low_support | high_flow_or_noninvasive_support | invasive_vent_required |
|---:|---:|---:|---:|
| 0 | 92 | 1 | 7 |
| 4 | 68 | 10 | 22 |
| 8 | 63 | 12 | 25 |
| 12 | 58 | 15 | 27 |
| 16 | 53 | 20 | 27 |
| 20 | 52 | 21 | 27 |
| 24 | 50 | 23 | 27 |

Interpretation:

- The medium respiratory state remains well represented in the single-task setting.
- This is still the best version if the goal is to test fine-grained respiratory escalation rather than only invasive support detection.

## Multitask Cohort Findings

Top-line stats:

- stays: 96
- rows: 672
- exactly 12 stays in each binary combination of:
  - sepsis positive / negative
  - AKI positive / negative
  - invasive respiratory support positive / negative

### Sepsis head

Row counts:

- `keep_monitoring`: 279
- `infection_suspect`: 142
- `trigger_sepsis_alert`: 251

Checkpoint distribution:

| t_hour | keep_monitoring | infection_suspect | trigger_sepsis_alert |
|---:|---:|---:|---:|
| 0 | 54 | 42 | 0 |
| 4 | 40 | 26 | 30 |
| 8 | 37 | 17 | 42 |
| 12 | 37 | 15 | 44 |
| 16 | 37 | 14 | 45 |
| 20 | 37 | 14 | 45 |
| 24 | 37 | 14 | 45 |

Interpretation:

- After the sepsis revision, the single-task and multitask sepsis heads are now structurally comparable.
- The main remaining difference is cohort identity, not label semantics.

### AKI head

Row counts:

- `keep_monitoring`: 373
- `suspect_aki`: 163
- `trigger_aki_alert`: 136

Checkpoint distribution:

| t_hour | keep_monitoring | suspect_aki | trigger_aki_alert |
|---:|---:|---:|---:|
| 0 | 79 | 11 | 6 |
| 4 | 72 | 16 | 8 |
| 8 | 60 | 28 | 8 |
| 12 | 49 | 38 | 9 |
| 16 | 42 | 27 | 27 |
| 20 | 36 | 24 | 36 |
| 24 | 35 | 19 | 42 |

Interpretation:

- AKI still transfers best into multitask mode.
- It becomes somewhat more alert-heavy because the stay balancing is driven by the stage-2-or-3 endpoint.

### Respiratory support head

Row counts:

- `room_air_or_low_support`: 361
- `high_flow_or_noninvasive_support`: 30
- `invasive_vent_required`: 281

Checkpoint distribution:

| t_hour | room_air_or_low_support | high_flow_or_noninvasive_support | invasive_vent_required |
|---:|---:|---:|---:|
| 0 | 86 | 0 | 10 |
| 4 | 54 | 1 | 41 |
| 8 | 47 | 3 | 46 |
| 12 | 44 | 6 | 46 |
| 16 | 44 | 6 | 46 |
| 20 | 43 | 7 | 46 |
| 24 | 43 | 7 | 46 |

Interpretation:

- Respiratory support is still the least faithful task in multitask mode.
- The medium state is heavily compressed.
- This makes multitask respiratory easier as a coarse escalation problem, but weaker as a benchmark for nuanced support changes.

## Single-Task vs Multitask Comparison

### 1. Structural alignment is now much better

The three single-task datasets now match on:

- 3-state escalation framing
- shared 4-hour checkpoint grid
- 24-hour horizon
- no negative snapped transition hours

This is an important benchmark improvement because agent behavior can now be compared across tasks without also comparing different task semantics.

### 2. The cohorts are still not matched by stay identity

Observed stay overlap with the multitask cohort:

- sepsis single-task vs multitask: 0 stays
- AKI single-task vs multitask: 0 stays
- respiratory single-task vs multitask: 1 stay

This means:

- single-task vs multitask is still not a clean multitasking ablation
- differences may reflect cohort composition as much as task coupling

### 3. Sepsis is now close to multitask in onset behavior

At `t=0`:

- single-task sepsis non-baseline: 49 / 100
- multitask sepsis non-baseline: 42 / 96

Interpretation:

- This is a strong sign that the revised sepsis single-task cohort is now aligned with the multitask convention.
- That makes sepsis much more suitable for single-vs-multitask benchmarking than before.

### 4. AKI remains the most transferable task

Single-task AKI and multitask AKI both preserve:

- a real intermediate state
- gradual escalation across checkpoints
- non-trivial but not overwhelming early positives

Interpretation:

- AKI is currently the strongest task for comparing agent competence across single-task and multitask settings.

### 5. Respiratory support remains the major mismatch

Single-task respiratory:

- 23 of 100 stays ever show `high_flow_or_noninvasive_support`

Multitask respiratory:

- only 7 of 96 stays ever show `high_flow_or_noninvasive_support`

Interpretation:

- The multitask respiratory head is underpowered as a 3-state task.
- It behaves much closer to a binary invasive-support benchmark.

### 6. Step-level burden in multitask is meaningful

Across the 672 multitask checkpoint rows:

- 96 steps have zero escalated tasks
- 238 have one escalated task
- 249 have two escalated tasks
- 89 have all three tasks escalated

Interpretation:

- The multitask benchmark is not dominated by easy all-negative checkpoints.
- It creates a real shared-monitoring problem rather than three unrelated tasks glued together.

## Main Insights For The Agent Benchmark

### What is now strong

1. The project now has a coherent family of 3-state longitudinal escalation tasks.

2. Sepsis and AKI are both in good shape for single-task and multitask evaluation.

3. The multitask benchmark has meaningful joint burden and a balanced stay-level co-occurrence design.

### What is still limiting

1. The multitask cohort is not matched to the single-task cohorts.

2. Respiratory support loses most of its middle-state difficulty in multitask mode.

3. The single-task cohorts use different sampling logic from the multitask cohort:
   - sepsis: 50 positive / 50 negative
   - AKI: no-AKI / stage1-only / stage23
   - respiratory: low-only / medium-only / high
   - multitask: binary endpoint balancing across three tasks

This is reasonable operationally, but it means the benchmark family is aligned in semantics more than in cohort identity.

## Recommendations

### Highest priority

1. Rebuild the multitask respiratory sampling so the middle state is preserved.
   A better design would explicitly stratify respiratory stays by:
   - low-only
   - medium-only
   - invasive
   instead of only by invasive yes/no.

2. Create a matched single-vs-multitask comparison split.
   Use the same stays in:
   - sepsis single-task
   - AKI single-task
   - respiratory single-task
   - multitask

This would turn the benchmark into a much cleaner multitasking study.

### Medium priority

3. Add a small dataset manifest for each package with:
   - SQL version
   - generation date
   - cohort counts
   - label counts
   - sampling rule summary

4. Consider making the other single-task SQL files deterministic too, as was done for sepsis, to improve reproducibility.

## Bottom Line

The revised sepsis dataset materially improves the overall benchmark design.

The benchmark family is now consistent in task semantics and time framing:

- sepsis
- AKI
- respiratory support

The main remaining scientific gap is not the task formulation anymore. It is the cohort design gap between single-task and multitask datasets, especially the compressed respiratory middle state and the lack of matched stays across settings.

That means the project is now in a good place for iterative model development, smoke testing, and early benchmarking. The next major upgrade should focus on matched-cohort evaluation rather than further changes to the basic task definitions.
