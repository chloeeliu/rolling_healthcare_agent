from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_TEMPLATE_DIR = REPO_ROOT / "dataset" / "surveilance"

PIPELINE_48H: list[tuple[str, str]] = [
    ("checkpoint_truth_sql.sql", "checkpoint_truth_all.csv"),
    ("benchmark_stay_sampling_features_sql.sql", "benchmark_stay_sampling_features.csv"),
    ("benchmark_2k_manifest_sql.sql", "benchmark_2k_manifest.csv"),
    ("benchmark_2k_checkpoint_truth_sql.sql", "benchmark_2k_checkpoint_truth.csv"),
    ("benchmark_2k_summary_sql.sql", "benchmark_2k_summary.csv"),
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
            f"Could not locate mimic4_dk.db under {root}. Pass --db-path directly if needed."
        )
    return matches[0].resolve()


def _render_sql(template_path: Path, output_dir: Path) -> str:
    sql = template_path.read_text()
    return _strip_sql(sql.replace(str(SQL_TEMPLATE_DIR), str(output_dir)))


def _row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _write_sql_snapshot(output_dir: Path, sql_name: str, sql_text: str) -> None:
    sql_dir = output_dir / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)
    (sql_dir / sql_name).write_text(sql_text + "\n")


def _write_metadata(output_dir: Path, db_path: Path, generated_files: list[str]) -> None:
    metadata = {
        "db_path": str(db_path),
        "generated_files": generated_files,
        "primary_benchmark_csv": "benchmark_2k_checkpoint_truth.csv",
        "sql_dependencies": [sql_name for sql_name, _ in PIPELINE_48H],
    }
    (output_dir / "build_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def build_benchmark_48h(db_path: Path, output_dir: Path, *, force: bool = False) -> None:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("This script requires the 'duckdb' Python package.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)

    expected = [output_dir / csv_name for _, csv_name in PIPELINE_48H]
    if not force:
        existing = [p for p in expected if p.exists()]
        if existing:
            raise FileExistsError(
                f"Output directory {output_dir} already contains generated benchmark files. "
                "Use --force to overwrite."
            )

    con = duckdb.connect(str(db_path), read_only=True)
    generated_files: list[str] = []
    try:
        for sql_name, csv_name in PIPELINE_48H:
            rendered_sql = _render_sql(SQL_TEMPLATE_DIR / sql_name, output_dir)
            _write_sql_snapshot(output_dir, sql_name, rendered_sql)
            output_csv = output_dir / csv_name
            if output_csv.exists():
                output_csv.unlink()
            print(f"[build_surveillance_benchmark_48h] Building {csv_name} ...")
            escaped = str(output_csv).replace("'", "''")
            con.execute(f"COPY ({rendered_sql}) TO '{escaped}' (HEADER, DELIMITER ',')")
            print(
                f"[build_surveillance_benchmark_48h] Wrote {output_csv} "
                f"({_row_count(output_csv)} rows)."
            )
            generated_files.append(csv_name)
    finally:
        con.close()

    _write_metadata(output_dir, db_path, generated_files)
    print("[build_surveillance_benchmark_48h] Done.")
    print(
        "[build_surveillance_benchmark_48h] Primary output: "
        f"{output_dir / 'benchmark_2k_checkpoint_truth.csv'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the primary 48-hour 2k ICU surveillance benchmark package."
    )
    parser.add_argument("--db-path", help="Path to mimic4_dk.db.")
    parser.add_argument(
        "--mimic-root",
        help="Path to a MIMIC-IV project root; the script will search for mimic4_dk.db under it.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for the generated benchmark package.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated outputs.")
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db_path, args.mimic_root)
    output_dir = Path(args.output_dir).expanduser().resolve()
    build_benchmark_48h(db_path, output_dir, force=args.force)


if __name__ == "__main__":
    main()
