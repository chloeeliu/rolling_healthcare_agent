# General ICU Surveillance Checkpoint Ground-Truth Curation

Date: 2026-04-25

## Purpose

This document defines the next dataset-build step after cohort finalization:

- checkpoint-level ground truth
- the latent decision registry
- generalized `suspect` vs `alert` mapping
- and the recommended `~2,000`-stay benchmark package

It builds on:

- [general_icu_surveillance_dataset_design_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/general_icu_surveillance_dataset_design_2026-04-25.md)
- [surveillance_dataset_cohort_audit_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/surveillance_dataset_cohort_audit_2026-04-25.md)

The first concrete build based on this design is documented in:

- [checkpoint_ground_truth_build_report_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/checkpoint_ground_truth_build_report_2026-04-25.md)

## Core Recommendation

Build ground truth in two layers:

1. a latent checkpoint decision layer with `25` canonical ICU surveillance decisions
2. a benchmark response layer that maps those decisions into:
   - `suspected_conditions`
   - `alerts`
   - `global_action`
   - `priority`

This gives us:

- enough granularity for a hard ICU benchmark
- a generalized and stable scoring interface
- and a way to keep the model output simple even when the internal label space is larger

## Recommended Benchmark Size

Use a benchmark package of about `2,000` ICU stays.

Because the cohort already requires `LOS >= 48h`, this corresponds to roughly:

- `13` checkpoints per stay (`0, 4, ..., 48`)
- about `26,000` checkpoint rows

That is large enough for:

- meaningful trajectory evaluation
- many-task coverage
- unit and onset heterogeneity

but still small enough to:

- run agent evaluation at reasonable cost
- inspect failure modes
- and avoid an excessively prevalence-skewed benchmark

## Which Splits to Use

Keep the full `46,337`-stay cohort as the label-build universe, but create the public benchmark package from the held-out side only:

- benchmark `dev`: `400` stays
- benchmark `test`: `1,600` stays

Recommendation:

- do not use the original training split for the benchmark package
- keep it available only for ablations, prompt iteration, or internal experiments

This preserves a clean evaluation story.

## Latent Decision Registry

The latent decision registry is stored at:

- [checkpoint_decision_registry.csv](/Users/chloe/Documents/New project/dataset/surveilance/checkpoint_decision_registry.csv)

It contains `25` canonical decisions across `8` families:

1. infection
2. sepsis
3. renal
4. respiratory
5. hemodynamic
6. neurologic
7. metabolic
8. coagulation

### Why keep a latent registry

The benchmark prompt should stay simple.
The labels should not.

The latent registry gives us:

- finer task coverage than a small disease-only label set
- exact SQL-level semantics for checkpoint truth
- and a clean way to evaluate both family-level decisions and specific ICU states

## Generalized `suspect` vs `alert`

Use a generalized family-level method.

### `suspect`

A family is in `suspected_conditions` at checkpoint `t` if the highest active decision in that family is a `suspect` decision.

Examples:

- `aki_stage1`
- `oliguria_6h`
- `resp_support_hfnc_or_niv`
- `hyperlactatemia_ge_2`
- `coagulopathy_inr_ge_1_5`

### `alert`

A family is in `alerts` at checkpoint `t` if the highest active decision in that family is an `alert` decision.

Examples:

- `sepsis_alert`
- `septic_shock_alert`
- `aki_stage2`
- `aki_stage3`
- `resp_support_invasive_vent`
- `vasoactive_multi_agent_or_high_intensity`
- `gcs_severe_impairment_le_8`

### Precedence rule

Within each family, only the highest-precedence active decision should define the exposed output state.

Examples:

- if both `aki_stage1` and `aki_stage3` are active, expose renal as alert-level, not both
- if both `resp_support_hfnc_or_niv` and `resp_support_invasive_vent` are active, expose only the invasive state for scoring
- if both `coagulopathy_inr_ge_1_5` and `coagulopathy_inr_ge_2` are active, expose only the alert-level coagulation state

This gives a generalized and deterministic suspect/alert mapping without hand-writing per-disease output rules.

## Four Checkpoint State Types

The most important design choice is that not all ICU states should persist the same way.

We should use four checkpoint state types.

### 1. Persistent episode

Use for diagnoses or syndrome onsets that should remain true for the episode once detected in the `0-48h` benchmark window.

Applies to:

- `infection_suspected`
- `infection_confirmed_or_strongly_supported`
- `sepsis_alert`

Checkpoint rule:

- active at checkpoint `t` if first qualifying onset time is `<= t`

### 2. Cumulative max stage

Use for injury-stage concepts where the benchmark should reflect the worst stage attained so far, not only the current row value.

Applies to:

- `aki_stage1`
- `aki_stage2`
- `aki_stage3`

Checkpoint rule:

- compute the maximum KDIGO stage observed up to checkpoint `t`
- activate the highest attained stage only

This is better than instantaneous staging because the agent should remember that injury has occurred.

### 3. Active interval

Use for support therapies that are active only while the support overlaps the checkpoint.

Applies to:

- `resp_support_hfnc_or_niv`
- `resp_support_invasive_vent`
- `vasoactive_support_any`
- `vasoactive_multi_agent_or_high_intensity`
- `crrt_active`

Checkpoint rule:

- active if support start time is `<= t` and end time is `NULL` or `> t`

### 4. Recent-measurement / rolling-window state

Use for lab/vital-derived states where the decision should reflect the latest available evidence within a limited trailing window.

Applies to:

- `oliguria_6h`
- `severe_oliguria_or_anuria`
- `hypoxemia_pf_lt_200`
- `hypoxemia_pf_lt_100`
- `gcs_moderate_impairment_9_12`
- `gcs_severe_impairment_le_8`
- `hyperlactatemia_ge_2`
- `severe_hyperlactatemia_ge_4`
- `acidemia_ph_lt_7_30`
- `severe_acidemia_ph_le_7_20`
- `coagulopathy_inr_ge_1_5`
- `coagulopathy_inr_ge_2`

Checkpoint rule:

- select the most recent qualifying source row `<= t`
- require it to fall within the task-specific recency TTL
- deactivate if TTL expires and no newer abnormal row appears

Recommended TTLs:

- `6h` for `oliguria_6h`
- `24h` for `severe_oliguria_or_anuria`
- `8h` for GCS
- `12h` for blood-gas-based states
- `24h` for INR-based states

## Composite Current States

Some alert heads should be recomputed from component states at every checkpoint rather than treated as once-on episode flags.

This is the right pattern for shock-like states.

### `septic_shock_alert`

Active if all are true at checkpoint `t`:

- `sepsis_alert` is active
- `vasoactive_support_any` is active
- `hyperlactatemia_ge_2` is active in its recency window

### `shock_hypoperfusion_alert`

Active if all are true at checkpoint `t`:

- `sepsis_alert` is active
- `vasoactive_support_any` is active
- `severe_hyperlactatemia_ge_4` is active in its recency window

This makes these states more clinically faithful than a simple “once positive, always positive” rule.

## Why This Labeling Scheme Is Better

This checkpoint scheme is better than pure ever-positive labels because it preserves the difference between:

- a diagnosis that persists through the episode
- a support therapy that turns on and off
- a recent lab derangement that should expire if not refreshed
- and a cumulative injury stage that should not be forgotten once reached

That is the right level of realism for ICU surveillance.

## Onset Timing Evidence

The onset-timing audit is:

- [decision_onset_timing.csv](/Users/chloe/Documents/New project/dataset/surveilance/decision_onset_timing.csv)

This matters because a useful rolling benchmark should contain both:

- early positives
- delayed deterioration

Key patterns:

- very early-heavy states:
  - `infection_suspected`: `90.30%` of positive stays start by `4h`
  - `hyperlactatemia_ge_2`: `76.55%`
  - `resp_support_invasive_vent`: `70.77%`
  - `sepsis_alert`: `63.76%`
- delayed-progression states:
  - `aki_stage3`: `56.21%` start in `24-48h`
  - `severe_oliguria_or_anuria`: `32.42%` in `24-48h` and `65.89%` in `12-24h`
  - `crrt_active`: `35.96%` in `24-48h`
- mixed-timing states:
  - `septic_shock_alert`
  - `shock_hypoperfusion_alert`
  - `gcs` impairment states
  - `PF ratio` states

This is exactly why the benchmark subset should not be sampled only by stay-level positivity.
It should also be sampled by onset timing.

## Recommended 2,000-Stay Sampling Strategy

Do not try to make every decision exactly balanced.
That would destroy ICU realism.

Instead, use a soft-balanced sampling plan with three layers.

### Layer 1: Realistic core diversity (`1,200` stays)

Sample across:

- first care unit family
- overall checkpoint complexity
- onset profile

Recommended stratification axes:

- unit group: `MICU/CVICU`, `mixed med-surg/surgical/trauma`, `CCU`, `neuro-facing`
- core-family count by `24h`: `0-1`, `2-3`, `4+`
- onset profile:
  - mostly early (`>=60%` of first positive families by `12h`)
  - mixed
  - delayed (`at least one alert family first turns on in 24-48h`)

This layer preserves realism.

### Layer 2: alert enrichment (`600` stays)

Oversample stays positive by `48h` for at least one of the rarer but benchmark-important alert heads:

- `aki_stage3`
- `septic_shock_alert`
- `shock_hypoperfusion_alert`
- `hypoxemia_pf_lt_100`
- `gcs_severe_impairment_le_8`
- `severe_acidemia_ph_le_7_20`
- `coagulopathy_inr_ge_2`
- `vasoactive_multi_agent_or_high_intensity`

These heads are all common enough in the full cohort to support enrichment without duplicating odd edge cases.

### Layer 3: low-signal / mostly-negative stays (`200` stays)

Reserve a smaller slice for harder low-evidence monitoring:

- zero or one core family by `24h`
- fewer intervention-heavy supports
- neuro-intermediate and other lower-density contexts included

This prevents the benchmark from becoming only a “severely positive ICU” dataset.

## Soft Floors for the 2,000-Stay Package

After sampling, enforce soft stay-level minimums for the following heads by `48h`:

- `aki_stage3`: at least `180`
- `septic_shock_alert`: at least `180`
- `shock_hypoperfusion_alert`: at least `120`
- `hypoxemia_pf_lt_100`: at least `180`
- `gcs_severe_impairment_le_8`: at least `120`
- `severe_acidemia_ph_le_7_20`: at least `120`
- `coagulopathy_inr_ge_2`: at least `180`
- `vasoactive_multi_agent_or_high_intensity`: at least `150`

Optional extended floors:

- `resp_support_hfnc_or_niv`: at least `120`
- `crrt_active`: at least `60`

These are soft floors, not exact prevalence targets.

The purpose is:

- not to equalize every head
- but to avoid a benchmark where high-acuity decisions are too sparse to evaluate well

## What Should Be Scored

The benchmark should score three layers.

### 1. Family-level structured outputs

Primary benchmark score:

- `suspected_conditions`
- `alerts`
- `global_action`
- `priority`

This is the main user-facing score.

### 2. Latent decision recovery

Secondary score:

- evaluate whether the latent `25` checkpoint decisions are recoverable from the agent output and rationale
- use these mainly for slice analysis and error taxonomy

### 3. Timing

Track:

- first correct suspicion time
- first correct alert time
- false early alert rate
- delayed alert rate

This is critical for a rolling benchmark.

## Global Action and Priority Derivation

Use generalized rules from the active checkpoint states.

### `global_action`

- `escalate` if any alert-level family is active
- `continue_monitoring` otherwise

### `priority`

- `high` if any of:
  - hemodynamic alert active
  - respiratory alert active
  - `aki_stage3`
  - `gcs_severe_impairment_le_8`
  - `severe_acidemia_ph_le_7_20`
  - `shock_hypoperfusion_alert`
- `medium` if any alert is active but none of the high-priority rules fire, or if `>=3` suspect families are active
- `low` otherwise

This can be revised later, but it is a clean starting rule set.

## Implementation Plan

The build should happen in this order.

1. Materialize the `LOS >= 48h` checkpoint grid.
2. Build per-decision checkpoint states for all `25` latent decisions using the registry rules.
3. Apply family precedence at each checkpoint.
4. Derive `suspected_conditions`, `alerts`, `global_action`, and `priority`.
5. Summarize each stay into sampling features:
   - family counts
   - alert-head positives
   - onset timing profile
   - unit group
6. Sample the `2,000`-stay benchmark package using the three-layer strategy.
7. Export:
   - full checkpoint truth for the selected stays
   - stay-level manifest
   - per-decision benchmark prevalence summary
   - onset/timing summary

## Main Recommendation

The safest and strongest design is:

- label all `46,337` cohort stays first
- sample the final benchmark package second
- use a `25`-decision latent registry
- expose generalized `suspect` and `alert` outputs at the family level
- and target a soft-balanced `2,000`-stay benchmark rather than artificial exact balancing

That preserves both:

- ICU realism
- and enough head coverage for meaningful evaluation
