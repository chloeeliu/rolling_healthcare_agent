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

Important clarification:

- this is **not** a uniform one-time-trigger benchmark
- the step-level ground truth intentionally varies across disease families

In practice:

- infection and sepsis are episode-style persistent states once they begin
- AKI uses worst-stage-attained-so-far semantics
- support therapies such as ventilation, vasoactives, and CRRT are current interval states
- labs and physiologic abnormalities such as GCS, PF ratio, lactate, pH, INR, and oliguria are recent-evidence states with TTLs
- shock-like states are recomputed each checkpoint from their component conditions

This varied semantics is part of the benchmark design, not a temporary implementation detail.

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

## Companion `24h` Truncated Release

We also generated a companion `24h` version of the benchmark package over the **same** `2,000` sampled stays:

- [benchmark_2k_checkpoint_truth_24h.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_checkpoint_truth_24h.csv)
- [benchmark_2k_summary_24h.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_summary_24h.csv)
- [benchmark_2k_horizon_comparison.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_horizon_comparison.csv)

This is a truncated horizon variant, not a newly re-sampled benchmark.

Headline shape:

- `48h` package: `26,000` checkpoint rows, `13` checkpoints per stay
- `24h` package: `14,000` checkpoint rows, `7` checkpoints per stay

So moving from `48h` to `24h` cuts the rollout length by about half while keeping the stay set fixed.

## Effect of Changing the Horizon from `48h` to `24h`

The horizon change does **not** affect the cohort identity:

- still `2,000` stays
- still the same `400` dev and `1,600` test stays
- still the same soft-balanced sampling layers

What changes is the amount of visible longitudinal evidence.

At the stay level:

- stays with any escalation drop from `1,883` to `1,795` (`94.15%` -> `89.75%`)
- this is a modest drop in positive-stay coverage (`-88` stays, `-4.7%`)

At the checkpoint level:

- escalate rows drop from `20,114` to `9,469`
- checkpoint escalation prevalence drops from `77.36%` to `67.64%`

This is a much larger checkpoint-level reduction because the later half of the trajectory contains many persistent or newly triggered alert states.

### Which heads are most affected

The horizon truncation mostly removes heads that often begin or intensify in the `24-48h` window.

Largest stay-level drops in the released `2,000`-stay package:

- `aki_stage3`: `325` -> `158` (`-51.4%`)
- `crrt_active`: `128` -> `82` (`-35.9%`)
- `gcs_severe_impairment_le_8`: `128` -> `86` (`-32.8%`)
- `aki_stage2`: `1,319` -> `970` (`-26.5%`)
- `hypoxemia_pf_lt_100`: `246` -> `199` (`-19.1%`)
- `vasoactive_multi_agent_or_high_intensity`: `285` -> `241` (`-15.4%`)

More modest drops:

- `sepsis_alert`: `1,314` -> `1,273` (`-3.1%`)
- `septic_shock_alert`: `350` -> `328` (`-6.3%`)
- `shock_hypoperfusion_alert`: `280` -> `253` (`-9.6%`)
- `resp_support_invasive_vent`: `1,082` -> `1,031` (`-4.7%`)
- `severe_hyperlactatemia_ge_4`: `312` -> `289` (`-7.4%`)
- `severe_acidemia_ph_le_7_20`: `212` -> `188` (`-11.3%`)
- `coagulopathy_inr_ge_2`: `240` -> `212` (`-11.7%`)

Interpretation:

- early infection and sepsis burden is already visible by `24h`, so those heads are relatively stable
- severe renal progression, CRRT exposure, and some neurologic / respiratory severe alerts are meaningfully delayed, so they thin out much more when the horizon is truncated

### Why this matters for evaluation

The `24h` package is attractive because it is cheaper and faster:

- fewer checkpoints
- fewer model calls
- shorter histories

But it is also easier in a specific way:

- it removes much of the delayed `24-48h` escalation behavior
- it reduces persistence-driven alert density in the second half of each stay
- it weakens some of the rare-alert enrichment that was originally selected using by-`48h` features

In other words:

- the `48h` package is the main longitudinal benchmark
- the `24h` package is a convenience variant for shorter experiments, ablations, and faster debugging
- if we ever wanted a *primary* `24h` benchmark, we should re-sample a dedicated subset using by-`24h` enrichment targets rather than simply truncating the existing `48h` release

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

### 4. The companion `24h` package is truncated, not rebalanced

The new `24h` export is intentionally the same stay set with fewer checkpoints.

That is the right first convenience release because it preserves direct comparability with the primary `48h` package.

But it also means:

- delayed `24-48h` alerts are removed rather than replaced
- some rare severe heads become much thinner
- the alert-enrichment layer is less saturated at `24h` than it is by `48h`

## Recommended Next Step

The next clean step is pipeline integration.

Specifically:

1. wire the benchmark package into the rolling evaluation loader
2. define the exact JSON output contract for `suspected_conditions`, `alerts`, `global_action`, and `priority`
3. run a first smoke evaluation on a very small subset
4. then expand to the full `2,000`-stay benchmark package
