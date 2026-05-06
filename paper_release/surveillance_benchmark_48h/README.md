# Surveillance Benchmark 48h Release

This package rebuilds the primary 48-hour `2,000`-stay ICU surveillance benchmark from a local MIMIC-IV DuckDB database.

It writes the benchmark package into the chosen output directory:

- `checkpoint_truth_all.csv`
- `benchmark_stay_sampling_features.csv`
- `benchmark_2k_manifest.csv`
- `benchmark_2k_checkpoint_truth.csv`

The final benchmark file is:

- `benchmark_2k_checkpoint_truth.csv`

The other CSVs are generated locally inside the same output directory for transparent reconstruction and auditing.

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

1. build full cohort checkpoint truth into the output directory
2. derive held-out stay-level sampling features into the same output directory
3. sample the final `2,000` benchmark stays into the same output directory
4. export the final benchmark checkpoint table

No external intermediate CSVs are required.

The SQL templates are intentionally path-agnostic. They refer to locally generated
intermediate files through placeholders such as `{{CHECKPOINT_TRUTH_ALL_CSV}}`,
and `build_surveillance_benchmark_48h.py` resolves those placeholders into paths
inside the chosen output directory at runtime. The release folder therefore
remains standalone: the only external input is the local `mimic4_dk.db`.
