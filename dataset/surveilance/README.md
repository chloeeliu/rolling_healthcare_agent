# Autoformalized Surveillance Dataset Package

This directory holds the phase-1 dataset curation artifacts for the general ICU surveillance benchmark.

The package is intentionally autoformalized-first:

- the cohort is ICU-stay based
- the task list follows the audited autoformalized function library
- the source coverage summaries are computed from the raw tables and item patterns used by the autoformalized functions

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

## SQL specs

- `stay_manifest_sql.sql`
- `checkpoint_grid_sql.sql`
- `cohort_summary_sql.sql`
- `task_source_coverage_sql.sql`
- `careunit_distribution_sql.sql`
- `los_bucket_distribution_sql.sql`
- `task_overlap_coverage_sql.sql`
- `task_overlap_top_patterns_sql.sql`

## Scope of this phase

This is the dataset foundation layer, not the final gold-label package.

What is included:

- the eligible ICU cohort
- split assignment
- checkpoint scaffolding
- source feasibility analysis aligned to the autoformalized functions

What is intentionally deferred:

- frozen per-task label contracts
- full checkpoint labels for `keep_monitoring` / `suspect` / `alert`
- the composed sepsis label builder

Those belong in the next dataset-build phase.
