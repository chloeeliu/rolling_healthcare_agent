# General ICU Surveillance Checkpoint Ground-Truth Build Report

Date: 2026-04-25

## Purpose

This report documents the first implemented checkpoint-ground-truth build for the general ICU surveillance benchmark.

It follows the design in:

- [checkpoint_ground_truth_curation_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/checkpoint_ground_truth_curation_2026-04-25.md)
- [surveillance_dataset_cohort_audit_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/surveillance_dataset_cohort_audit_2026-04-25.md)

## What Was Built

The build now includes five concrete dataset artifacts:

1. full checkpoint truth for the finalized `LOS >= 48h` cohort
2. held-out stay-level sampling features
3. a soft-balanced `2,000`-stay benchmark manifest
4. checkpoint truth restricted to the `2,000`-stay benchmark package
5. a compact summary of the benchmark subset

## New Artifacts

### Full checkpoint truth

- [checkpoint_truth_all.csv](/Users/chloe/Documents/New project/dataset/surveilance/checkpoint_truth_all.csv)
- [checkpoint_truth_sql.sql](/Users/chloe/Documents/New project/dataset/surveilance/checkpoint_truth_sql.sql)

Headline shape:

- `602,381` checkpoint rows plus header
- `46,337` ICU stays
- `13` checkpoints per stay from `0` to `48`

Each checkpoint row includes:

- the `25` latent decision flags
- family-active indicators
- active family counts
- primary family decision labels
- `active_suspect_decisions`
- `active_alert_decisions`
- exposed `suspected_conditions`
- exposed `alerts`
- derived `global_action`
- derived `priority`

### Held-out stay-level sampling features

- [benchmark_stay_sampling_features.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_stay_sampling_features.csv)
- [benchmark_stay_sampling_features_sql.sql](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_stay_sampling_features_sql.sql)

Headline shape:

- `13,683` held-out stays plus header
- one row per stay from the original `dev` and `test` splits

This table contains the sampling metadata used to build the benchmark subset:

- unit group
- complexity bucket
- onset profile
- rare-alert grouping
- low-signal flag
- by-`48h` stay-level positivity for the key alert heads

### Final 2,000-stay benchmark subset

- [benchmark_2k_manifest.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_manifest.csv)
- [benchmark_2k_manifest_sql.sql](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_manifest_sql.sql)
- [benchmark_2k_checkpoint_truth.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_checkpoint_truth.csv)
- [benchmark_2k_checkpoint_truth_sql.sql](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_checkpoint_truth_sql.sql)
- [benchmark_2k_summary.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_summary.csv)
- [benchmark_2k_summary_sql.sql](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_summary_sql.sql)

Headline shape:

- `2,000` stays
- `400` dev stays
- `1,600` test stays
- `26,000` checkpoint rows plus header in the subset export

## Checkpoint Truth Semantics Implemented

The build follows the four checkpoint state types from the design doc:

- persistent episode
- cumulative max stage
- active interval
- recent measurement with TTL

Implemented examples:

- `infection_suspected`, `infection_confirmed_or_strongly_supported`, and `sepsis_alert` are persistent once they begin
- `aki_stage1/2/3` use the maximum KDIGO stage observed up to the checkpoint
- ventilation and vasoactive decisions require support overlap at the checkpoint
- GCS, PF ratio, lactate, pH, INR, and urine-output decisions use recency TTLs
- `septic_shock_alert` and `shock_hypoperfusion_alert` are recomputed from component states at every checkpoint

## Benchmark Subset Sampling Policy Implemented

The implemented benchmark sampler follows the three-layer plan:

- `core_diversity`
- `alert_enrichment`
- `low_signal`

Final split-layer counts from [benchmark_2k_summary.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_summary.csv):

| Split | Layer | Stays |
|---|---:|---:|
| dev | core_diversity | `240` |
| dev | alert_enrichment | `120` |
| dev | low_signal | `40` |
| test | core_diversity | `960` |
| test | alert_enrichment | `480` |
| test | low_signal | `160` |

The sampler is deterministic and stratified.

It balances on:

- unit group
- complexity bucket
- onset profile
- and rare-alert grouping

Within the alert-enrichment layer, the final ranking also uses a rarity-weighted priority score so that very important but thinner heads are not washed out by the more common severe states.

## Rare-Alert Coverage in the Final 2,000-Stay Package

The final sample meets the main soft floors that motivated the alert-enrichment layer.

Overall counts:

- `aki_stage3_by48h`: `325`
- `septic_shock_alert_by48h`: `350`
- `shock_hypoperfusion_alert_by48h`: `280`
- `hypoxemia_pf_lt_100_by48h`: `246`
- `gcs_severe_impairment_le_8_by48h`: `128`
- `severe_acidemia_ph_le_7_20_by48h`: `212`
- `coagulopathy_inr_ge_2_by48h`: `240`
- `vasoactive_multi_agent_or_high_intensity_by48h`: `285`

Optional extended heads:

- `crrt_active_by48h`: `128`
- `resp_support_hfnc_or_niv_by48h`: `104`

Interpretation:

- the sample is no longer dominated by only the most common ICU tasks
- the high-acuity heads are common enough to support meaningful evaluation
- the optional `HFNC/NIV` head remains somewhat thinner than the original aspirational floor, but still has enough support to be usable

## Sample Character

The final benchmark package preserves the intended layer behavior:

- `core_diversity` stays have mid-range complexity and broad ICU realism
- `alert_enrichment` stays are denser and richer in severe conditions
- `low_signal` stays keep a non-trivial monitoring subset that is not saturated with alarms

This is important because a benchmark built only from severe positives would be easier in the wrong way.

## Important Caveats

### 1. CRRT is still an approximation

The current build treats `crrt_active` using recent observed CRRT rows with a short TTL rather than a perfectly reconstructed support interval.

That is acceptable for an extended head, but it should be documented as an approximation if we score it prominently.

### 2. Family-level compression is intentionally lossy

The full table contains both:

- all active suspect/alert decisions
- and a single primary decision per family

This is deliberate.

It allows:

- richer latent analysis
- simpler benchmark outputs

but it also means the exposed `suspected_conditions` and `alerts` are a compressed view of the full checkpoint state.

### 3. Some families remain naturally correlated

The benchmark subset is softer-balanced, not independently balanced per head.

That is the right choice.

It preserves:

- sepsis-hemodynamic overlap
- renal-oliguria overlap
- respiratory-hemodynamic overlap
- metabolic co-occurrence

which are all important ICU realism signals.

## Recommended Next Step

The next clean step is pipeline integration.

Specifically:

1. wire the benchmark package into the rolling evaluation loader
2. define the exact JSON output contract for `suspected_conditions`, `alerts`, `global_action`, and `priority`
3. run a first smoke evaluation on a very small subset
4. then expand to the full `2,000`-stay benchmark package
