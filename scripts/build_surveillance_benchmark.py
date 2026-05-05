from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_DIR = REPO_ROOT / "dataset" / "surveilance"

PIPELINE_STEPS: list[tuple[str, str]] = [
    ("checkpoint_truth_sql.sql", "checkpoint_truth_all.csv"),
    ("benchmark_stay_sampling_features_sql.sql", "benchmark_stay_sampling_features.csv"),
    ("benchmark_2k_manifest_sql.sql", "benchmark_2k_manifest.csv"),
    ("benchmark_2k_checkpoint_truth_sql.sql", "benchmark_2k_checkpoint_truth.csv"),
    ("benchmark_2k_summary_sql.sql", "benchmark_2k_summary.csv"),
    ("benchmark_2k_checkpoint_truth_24h_sql.sql", "benchmark_2k_checkpoint_truth_24h.csv"),
    ("benchmark_2k_summary_24h_sql.sql", "benchmark_2k_summary_24h.csv"),
    ("benchmark_2k_horizon_comparison_sql.sql", "benchmark_2k_horizon_comparison.csv"),
]

STATIC_FILES = [
    "checkpoint_decision_registry.csv",
    "task_registry.csv",
    "README.md",
]


def _strip_sql(sql: str) -> str:
    return sql.strip().rstrip(";")


def _resolve_db_path(db_path: str | None, mimic_root: str | None) -> Path:
    if db_path:
        path = Path(db_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Database file not found: {path}")
        return path

    if not mimic_root:
        raise ValueError("Provide either --db-path or --mimic-root.")

    root = Path(mimic_root).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"MIMIC root not found: {root}")

    preferred = root / "buildmimic" / "duckdb" / "mimic4_dk.db"
    if preferred.is_file():
        return preferred

    matches = sorted(root.rglob("mimic4_dk.db"))
    if not matches:
        raise FileNotFoundError(
            f"Could not locate mimic4_dk.db under {root}. "
            "Pass --db-path directly if the database file lives elsewhere."
        )
    if len(matches) > 1:
        print(
            f"[build_surveillance_benchmark] Found multiple mimic4_dk.db files under {root}; "
            f"using the first one: {matches[0]}"
        )
    return matches[0].resolve()


def _render_sql(template_path: Path, output_dir: Path) -> str:
    sql = template_path.read_text()
    return _strip_sql(sql.replace(str(DEFAULT_TEMPLATE_DIR), str(output_dir)))


def _copy_static_files(output_dir: Path) -> None:
    for name in STATIC_FILES:
        src = DEFAULT_TEMPLATE_DIR / name
        if src.exists():
            shutil.copy2(src, output_dir / name)


def _write_rendered_sql(output_dir: Path, sql_name: str, sql_text: str) -> None:
    rendered_dir = output_dir / "sql"
    rendered_dir.mkdir(parents=True, exist_ok=True)
    (rendered_dir / sql_name).write_text(sql_text + "\n")


def _export_query(con, sql: str, output_csv: Path) -> None:
    escaped = str(output_csv).replace("'", "''")
    con.execute(f"COPY ({sql}) TO '{escaped}' (HEADER, DELIMITER ',')")


def _row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _write_metadata(output_dir: Path, *, db_path: Path, generated_files: list[str]) -> None:
    metadata = {
        "db_path": str(db_path),
        "generated_files": generated_files,
        "primary_benchmark_csv": "benchmark_2k_checkpoint_truth.csv",
        "companion_24h_csv": "benchmark_2k_checkpoint_truth_24h.csv",
        "notes": [
            "The 48h package is the primary release.",
            "The 24h package is a truncated companion release over the same 2,000 sampled stays.",
            "Rendered SQL files used for this build are stored under output_dir/sql/.",
        ],
    }
    (output_dir / "build_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def build_surveillance_benchmark(db_path: Path, output_dir: Path, *, force: bool = False) -> None:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("This script requires the 'duckdb' Python package.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)

    expected_outputs = [output_dir / csv_name for _, csv_name in PIPELINE_STEPS]
    if not force:
        existing = [p for p in expected_outputs if p.exists()]
        if existing:
            names = ", ".join(p.name for p in existing[:5])
            raise FileExistsError(
                f"Output directory {output_dir} already contains generated files ({names}...). "
                "Use --force to overwrite."
            )

    _copy_static_files(output_dir)

    con = duckdb.connect(str(db_path), read_only=True)
    generated_files: list[str] = []
    try:
        for sql_name, csv_name in PIPELINE_STEPS:
            template_path = DEFAULT_TEMPLATE_DIR / sql_name
            rendered_sql = _render_sql(template_path, output_dir)
            output_csv = output_dir / csv_name
            if output_csv.exists():
                output_csv.unlink()
            _write_rendered_sql(output_dir, sql_name, rendered_sql)
            print(f"[build_surveillance_benchmark] Building {csv_name} from {sql_name} ...")
            _export_query(con, rendered_sql, output_csv)
            rows = _row_count(output_csv)
            print(f"[build_surveillance_benchmark] Wrote {output_csv} ({rows} rows).")
            generated_files.append(csv_name)
    finally:
        con.close()

    _write_metadata(output_dir, db_path=db_path, generated_files=generated_files)
    print("[build_surveillance_benchmark] Done.")
    print(f"[build_surveillance_benchmark] Primary output: {output_dir / 'benchmark_2k_checkpoint_truth.csv'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the general ICU surveillance 2k benchmark package from a MIMIC-IV DuckDB database."
        )
    )
    parser.add_argument(
        "--db-path",
        help="Path to the DuckDB database file (for example mimic4_dk.db).",
    )
    parser.add_argument(
        "--mimic-root",
        help=(
            "Path to a MIMIC-IV project root. If provided instead of --db-path, "
            "the script searches for buildmimic/duckdb/mimic4_dk.db or the first mimic4_dk.db under this tree."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the benchmark package should be written.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated outputs in the target directory.",
    )
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db_path, args.mimic_root)
    output_dir = Path(args.output_dir).expanduser().resolve()
    build_surveillance_benchmark(db_path, output_dir, force=args.force)


if __name__ == "__main__":
    main()
