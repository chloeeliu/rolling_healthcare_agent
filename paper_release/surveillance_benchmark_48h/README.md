# Surveillance Benchmark 48h Release

This package rebuilds the primary 48-hour `2,000`-stay ICU surveillance benchmark from a local MIMIC-IV DuckDB database.

It writes only one benchmark CSV:

- `benchmark_2k_checkpoint_truth.csv`

Intermediate benchmark-construction stages are computed as in-memory DuckDB views and are not written to disk.

## Requirements

- Python with the `duckdb` package installed
- a local MIMIC-IV DuckDB database, typically `mimic4_dk.db`

## Usage

Using a direct database path:

```bash
python build_surveillance_benchmark_48h.py \
  --db-path /path/to/mimic4_dk.db \
  --output-dir /path/to/output/surveilance_benchmark_48h
```

Using a MIMIC project root:

```bash
python build_surveillance_benchmark_48h.py \
  --mimic-root /path/to/mimic-iv-project-root \
  --output-dir /path/to/output/surveilance_benchmark_48h
```

## Included SQL templates

- `sql_templates/checkpoint_truth_sql.sql`
- `sql_templates/benchmark_stay_sampling_features_sql.sql`
- `sql_templates/benchmark_2k_manifest_sql.sql`
- `sql_templates/benchmark_2k_checkpoint_truth_sql.sql`

These are sufficient to reproduce the final benchmark CSV:

1. build full cohort checkpoint truth in memory
2. derive held-out stay-level sampling features in memory
3. sample the final `2,000` benchmark stays in memory
4. export the final benchmark checkpoint table
