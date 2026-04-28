# Autoformalized Surveillance Dataset Package

This directory holds the cohort, feasibility, and checkpoint-curation artifacts for the general ICU surveillance benchmark.

The package is best understood as a cohort-and-ground-truth design foundation:

- the cohort is ICU-stay based
- the source coverage summaries are computed from the raw tables and item patterns used by the autoformalized functions
- the final benchmark design now uses MIMIC-derived SQL as ground truth

Important update:

- these phase-1 artifacts remain valid as the cohort and source-feasibility foundation
- but the current benchmark design now uses MIMIC-derived SQL as ground truth and a larger surveillance decision catalog

Design reference:

- [general_icu_surveillance_dataset_design_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/general_icu_surveillance_dataset_design_2026-04-25.md)

## Phase-1 contents

- `surveillance_stay_manifest.csv`
  - eligible `LOS >= 48h` ICU stays with deterministic split assignment
- `surveillance_checkpoint_grid.csv`
  - every-4-hour checkpoint grid from `0` to `48`
- `cohort_summary.csv`
  - split-level cohort counts and checkpoint row counts
- `task_source_coverage_summary.csv`
  - task-by-task raw source coverage and simple positive proxies where available
- `careunit_distribution.csv`
  - first ICU care unit mix for the eligible surveillance cohort
- `los_bucket_distribution.csv`
  - ICU LOS bucket distribution for the eligible surveillance cohort
- `task_overlap_coverage.csv`
  - per-stay distribution of the number of positive proxy task families by `24h`
- `task_overlap_top_patterns.csv`
  - most common overlap patterns among the threshold-style proxy heads
- `task_registry.csv`
  - finalized task list and benchmark-facing tool plan
- `cohort_option_comparison.csv`
  - side-by-side audit of `LOS >= 24h`, `48h`, and `72h` candidate cohorts
- `decision_catalog_feasibility.csv`
  - official derived-SQL prevalence table for the broader surveillance decision catalog
- `derived_core_overlap_distribution.csv`
  - per-stay distribution of the number of active official core surveillance families by `24h`
- `derived_core_overlap_top_patterns.csv`
  - top official overlap patterns across the core derived surveillance families
- `core_family_coverage_by_careunit.csv`
  - official core-family coverage broken down by first ICU care unit
- `measurement_availability_by24h.csv`
  - by-source observation coverage by `24h` for the final cohort
- `demographics_distribution.csv`
  - age-bucket and gender distribution for the final cohort
- `checkpoint_decision_registry.csv`
  - canonical checkpoint decision registry with state type and persistence rules
- `decision_onset_timing.csv`
  - onset timing distribution for the checkpoint decision catalog by `48h`
- `checkpoint_truth_all.csv`
  - full checkpoint-level ground-truth table for the finalized `LOS >= 48h` cohort
- `benchmark_stay_sampling_features.csv`
  - held-out stay-level features used for soft-balanced benchmark sampling
- `benchmark_2k_manifest.csv`
  - final `2,000`-stay benchmark subset manifest
- `benchmark_2k_checkpoint_truth.csv`
  - checkpoint ground-truth table restricted to the final `2,000`-stay subset
- `benchmark_2k_summary.csv`
  - summary table for the final `2,000`-stay benchmark package

## SQL specs

- `stay_manifest_sql.sql`
- `checkpoint_grid_sql.sql`
- `cohort_summary_sql.sql`
- `task_source_coverage_sql.sql`
- `careunit_distribution_sql.sql`
- `los_bucket_distribution_sql.sql`
- `task_overlap_coverage_sql.sql`
- `task_overlap_top_patterns_sql.sql`
- `cohort_option_comparison_sql.sql`
- `decision_catalog_feasibility_sql.sql`
- `derived_core_overlap_distribution_sql.sql`
- `derived_core_overlap_top_patterns_sql.sql`
- `core_family_coverage_by_careunit_sql.sql`
- `measurement_availability_by24h_sql.sql`
- `demographics_distribution_sql.sql`
- `decision_onset_timing_sql.sql`
- `checkpoint_truth_sql.sql`
- `benchmark_stay_sampling_features_sql.sql`
- `benchmark_2k_manifest_sql.sql`
- `benchmark_2k_checkpoint_truth_sql.sql`
- `benchmark_2k_summary_sql.sql`

## Scope of the current package

This package now covers the cohort, checkpoint-ground-truth, and runnable benchmark-input layers.

What is included:

- the eligible ICU cohort
- split assignment
- checkpoint scaffolding
- source feasibility analysis aligned to the autoformalized functions
- checkpoint decision registry
- onset-timing analysis for the checkpoint decision catalog
- full checkpoint truth over the finalized `LOS >= 48h` cohort
- a soft-balanced `2,000`-stay benchmark subset
- a directly runnable CSV input for the surveillance pipeline:
  - `benchmark_2k_checkpoint_truth.csv`

What remains intentionally deferred:

- deeper pipeline scoring outputs beyond the current ground-truth table
- optional benchmark extensions such as stronger CRRT interval reconstruction
- future alternate benchmark subsets or split variants

Runnable benchmark references:

- [general_icu_surveillance_dataset_design_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/general_icu_surveillance_dataset_design_2026-04-25.md)
- [general_icu_surveillance_pipeline_runbook_2026-04-27.md](/Users/chloe/Documents/New project/docs/surveilance/general_icu_surveillance_pipeline_runbook_2026-04-27.md)
