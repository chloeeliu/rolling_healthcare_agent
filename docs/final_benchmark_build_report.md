# Final Benchmark Build Report

## Status

The final benchmark packages have been generated under:

- [/Users/chloe/Documents/New project/rolling_monitor_dataset/sepsis_final](/Users/chloe/Documents/New project/rolling_monitor_dataset/sepsis_final)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_final](/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_final)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/respiratory_support_final](/Users/chloe/Documents/New project/rolling_monitor_dataset/respiratory_support_final)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask_final](/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask_final)
- [/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic_final](/Users/chloe/Documents/New project/rolling_monitor_dataset/aki_non_monotonic_final)

Each package includes:

- `dataset_sql.sql`
- full CSV export
- split-specific CSV exports
- `summary.json`
- `trajectory_schema.json`

## Final Dataset Sizes

| Dataset | Trajectories | Rows | Split counts |
|---|---:|---:|---|
| sepsis final | 2,000 | 14,000 | train 1,400 / dev 300 / test 300 |
| AKI final | 2,000 | 14,000 | train 1,400 / dev 300 / test 300 |
| respiratory final | 2,000 | 14,000 | train 1,400 / dev 300 / test 300 |
| multitask final | 2,048 | 14,336 | train 1,440 / dev 304 / test 304 |
| AKI non-monotonic final | 2,000 | 14,000 | train 1,400 / dev 300 / test 300 |

## Respiratory Final Design

The original respiratory design used:

- `low_only`
- `medium_only`
- `direct_invasive`
- `medium_then_invasive`

That was not feasible inside the strict `0-24h` benchmark horizon.

The implemented final respiratory design uses:

- `low_only`
- `medium_only`
- `invasive_early`
- `invasive_late`

This preserves:

- horizon-consistent labels
- a meaningful intermediate state
- early versus delayed invasive escalation
- the target dataset size

## Reproducibility

Export script:

- [/Users/chloe/Documents/New project/scripts/export_final_benchmark_datasets.py](/Users/chloe/Documents/New project/scripts/export_final_benchmark_datasets.py)

Generation command:

```bash
python scripts/export_final_benchmark_datasets.py \
  --db-path /Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db
```

## Compatibility Check

The exported CSVs were validated with `load_dataset_auto` and loaded successfully with these trajectory counts:

- sepsis final: `2000`
- AKI final: `2000`
- respiratory final: `2000`
- multitask final: `2048`
- AKI non-monotonic final: `2000`
