# Non-Monotonic AKI Dataset: Creation and Distribution

## Files

Dataset package:

- [/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/dataset_sql.sql](/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/dataset_sql.sql)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/rolling_aki_non_monotonic.csv](/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/rolling_aki_non_monotonic.csv)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/trajectory_schema.json](/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/trajectory_schema.json)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/trajectory_family_summary.csv](/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/trajectory_family_summary.csv)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/checkpoint_label_distribution.csv](/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic/checkpoint_label_distribution.csv)

## Goal

Create a first 100-stay AKI dataset for rolling non-monotonic state tracking, rather than monotonic first-onset escalation.

Label space:

- `no_aki`
- `aki_stage_1`
- `aki_stage_2`
- `aki_stage_3`

Each checkpoint label reflects the **current visible AKI stage** at that time, not the first stage ever reached.

## Hidden State Definition

Source concept:

- `mimiciv_derived.kdigo_stages`

Hidden label source:

- latest visible `aki_stage_smoothed` at each checkpoint

Checkpoint grid:

- `t = 0, 4, 8, 12, 16, 20, 24`

Anchor:

- ICU `intime`

The dataset stores the latest visible KDIGO stage by each checkpoint and maps it directly into the four-label state space.

## Eligibility Rules

Stays are eligible if they satisfy all of the following:

- ICU LOS `>= 24` hours
- a visible KDIGO stage is already available at `t=0`
- a visible KDIGO stage is available at every checkpoint through `t=24`

This choice is deliberate. It keeps the task in the requested four-label space without introducing an additional `insufficient_data` state.

Eligible source cohort size under these rules:

- `63,728` ICU stays

## Sampling Strategy

The sample is **deterministic stratified sampling**, not pure random sampling.

Reason:

- a purely prevalence-based sample would be dominated by stable stage-0 trajectories
- the benchmark is more useful if it contains worsening, recovery, and fluctuation patterns

We stratify stays into seven checkpoint-path families using the 0–24h path of latest visible `aki_stage_smoothed`:

- `stable_no_aki`
- `stage1_progressive_or_persistent`
- `stage1_recovery_or_fluctuating`
- `stage2_progressive_or_persistent`
- `stage2_recovery_or_fluctuating`
- `stage3_progressive_or_persistent`
- `stage3_recovery_or_fluctuating`

Sampling quotas:

- `stable_no_aki`: `16`
- `stage1_progressive_or_persistent`: `14`
- `stage1_recovery_or_fluctuating`: `14`
- `stage2_progressive_or_persistent`: `14`
- `stage2_recovery_or_fluctuating`: `14`
- `stage3_progressive_or_persistent`: `14`
- `stage3_recovery_or_fluctuating`: `14`

Total:

- `100` stays

Within each family, selection is deterministic using `ORDER BY HASH(stay_id)`, so the sample is reproducible.

## Exported Dataset Shape

CSV size:

- `700` rows
- `100` trajectories
- `7` checkpoints per trajectory

Per-row fields include:

- patient and stay identifiers
- ICU timing
- path-family metadata
- `path_0_24`
- `max_stage_24h`
- `has_up_24h`
- `has_down_24h`
- `num_changes_24h`
- checkpoint hour and time
- `current_aki_stage_smoothed`
- `state_label`

`terminal` is always `false` because this is a current-state tracking task, not a monotonic alert task.

## Structure Compatibility

The new dataset follows the same runner-facing single-task structure as the sepsis package:

- shared identifier and timing columns:
  - `trajectory_id`
  - `subject_id`
  - `hadm_id`
  - `stay_id`
  - `icu_intime`
  - `icu_outtime`
  - `icu_los_hours`
  - `t_hour`
  - `checkpoint_time`
  - `state_label`
  - `terminal`
- single-task AKI tool set:
  - `query_kdigo_stage`

What is intentionally different from monotonic single-task sepsis:

- there are no first-transition columns like `aki_stage1_start_hour`
- instead, the dataset carries path metadata:
  - `path_family`
  - `path_0_24`
  - `max_stage_24h`
  - `has_up_24h`
  - `has_down_24h`
  - `num_changes_24h`

This is appropriate because the task is current-state tracking rather than first-onset detection.

The pipeline auto-loader has also been updated so this CSV is recognized as a single-task AKI dataset automatically.

## Sampled Family Distribution

Observed family counts in the exported sample:

- `stable_no_aki`: `16`
- `stage1_progressive_or_persistent`: `14`
- `stage1_recovery_or_fluctuating`: `14`
- `stage2_progressive_or_persistent`: `14`
- `stage2_recovery_or_fluctuating`: `14`
- `stage3_progressive_or_persistent`: `14`
- `stage3_recovery_or_fluctuating`: `14`

This gives the sample a balanced mix of:

- negative controls
- mild AKI
- moderate AKI
- severe AKI
- recovery paths
- fluctuating paths

## Sampled Label Distribution

Across all `700` checkpoint rows:

- `no_aki`: `335`
- `aki_stage_1`: `163`
- `aki_stage_2`: `110`
- `aki_stage_3`: `92`

Checkpoint label distribution:

- `t=0`: no_aki `70`, stage_1 `15`, stage_2 `9`, stage_3 `6`
- `t=4`: no_aki `64`, stage_1 `15`, stage_2 `7`, stage_3 `14`
- `t=8`: no_aki `60`, stage_1 `20`, stage_2 `7`, stage_3 `13`
- `t=12`: no_aki `43`, stage_1 `34`, stage_2 `10`, stage_3 `13`
- `t=16`: no_aki `37`, stage_1 `30`, stage_2 `21`, stage_3 `12`
- `t=20`: no_aki `31`, stage_1 `24`, stage_2 `29`, stage_3 `16`
- `t=24`: no_aki `30`, stage_1 `25`, stage_2 `27`, stage_3 `18`

This distribution is intentionally more informative than the source prevalence. It still contains many stage-0 checkpoints, but no longer lets them dominate the entire benchmark.

## Sampled Trajectory Dynamics

At the trajectory level:

- trajectories with any upward change: `77`
- trajectories with any downward change: `42`
- trajectories with both upward and downward changes: `38`
- mean number of checkpoint-stage changes: `1.64`
- median number of checkpoint-stage changes: `2`

Stay-level max stage in the sample:

- max stage 0: `16`
- max stage 1: `28`
- max stage 2: `28`
- max stage 3: `28`

This is close to a balanced max-severity mix while still preserving explicit recovery/fluctuation strata.

## Example Path Families

Representative examples from the exported sample:

- `stable_no_aki`: `0>0>0>0>0>0>0`
- `stage1_progressive_or_persistent`: `0>0>0>0>0>0>1`
- `stage1_recovery_or_fluctuating`: `0>0>0>0>1>1>0`
- `stage2_progressive_or_persistent`: `0>1>1>1>2>2>2`
- `stage2_recovery_or_fluctuating`: `1>0>1>1>0>0>2`
- `stage3_progressive_or_persistent`: `0>3>3>3>3>3>3`
- `stage3_recovery_or_fluctuating`: `0>3>0>1>1>2>3`

These examples show why the dataset is useful:

- some cases are simple and monotonic
- others improve after severe AKI
- some fluctuate in clinically awkward ways that a longitudinal agent should learn to track

## Practical Interpretation

This dataset is not an “AKI onset” benchmark anymore. It is a **current-state monitoring** benchmark.

That changes the agent requirement:

- the model must keep track of the latest stage
- the model should not assume alerts are permanent
- the model should be able to de-escalate when the visible KDIGO stage falls

## Recommended Next Step

The next benchmark iteration should expose a visible AKI tool that returns:

- latest `aki_stage_smoothed`
- contributor breakdown from creatinine, urine output, and CRRT
- optionally a short recent trend

That would let the agent reason over the same non-monotonic state dynamics encoded in this dataset.
