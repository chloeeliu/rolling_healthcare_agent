from __future__ import annotations

import argparse
import json
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
SQL_TEMPLATE_DIR = PACKAGE_ROOT / "sql_templates"

FINAL_ONLY_PIPELINE: list[tuple[str, str]] = [
    ("checkpoint_truth_sql.sql", "checkpoint_truth_all"),
    ("benchmark_stay_sampling_features_sql.sql", "benchmark_stay_sampling_features"),
    ("benchmark_2k_manifest_sql.sql", "benchmark_2k_manifest"),
]

FINAL_SQL_NAME = "benchmark_2k_checkpoint_truth_sql.sql"
FINAL_OUTPUT_NAME = "benchmark_2k_checkpoint_truth.csv"


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


def _template_sql(sql_name: str) -> str:
    return (SQL_TEMPLATE_DIR / sql_name).read_text()


def _replace_csv_dependency(sql: str, csv_name: str, replacement: str) -> str:
    absolute = str(SQL_TEMPLATE_DIR / csv_name)
    needle = f"read_csv_auto('{absolute}', header = true)"
    return sql.replace(needle, replacement)


def _render_view_sql(sql_name: str, replacements: dict[str, str]) -> str:
    sql = _template_sql(sql_name)
    for csv_name, relation_name in replacements.items():
        sql = _replace_csv_dependency(sql, csv_name, relation_name)
    return _strip_sql(sql)


def _row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _write_sql_snapshot(output_dir: Path, sql_name: str, sql_text: str) -> None:
    sql_dir = output_dir / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)
    (sql_dir / sql_name).write_text(sql_text + "\n")


def _write_metadata(output_dir: Path, db_path: Path) -> None:
    metadata = {
        "db_path": str(db_path),
        "generated_file": FINAL_OUTPUT_NAME,
        "pipeline_views": [view_name for _, view_name in FINAL_ONLY_PIPELINE],
        "sql_dependencies": [sql_name for sql_name, _ in FINAL_ONLY_PIPELINE] + [FINAL_SQL_NAME],
        "note": "This script writes only the final 48h benchmark CSV. Intermediate tables are temporary in-memory DuckDB views.",
    }
    (output_dir / "build_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def build_final_benchmark_48h(db_path: Path, output_dir: Path, *, force: bool = False) -> None:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("This script requires the 'duckdb' Python package.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = output_dir / FINAL_OUTPUT_NAME
    if output_csv.exists() and not force:
        raise FileExistsError(f"{output_csv} already exists. Use --force to overwrite.")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        replacements: dict[str, str] = {}
        for sql_name, view_name in FINAL_ONLY_PIPELINE:
            rendered_sql = _render_view_sql(sql_name, replacements)
            _write_sql_snapshot(output_dir, sql_name, rendered_sql)
            print(f"[build_surveillance_benchmark_48h] Creating temp view {view_name} from {sql_name} ...")
            con.execute(f"CREATE OR REPLACE TEMP VIEW {view_name} AS {rendered_sql}")
            replacements[f"{view_name}.csv"] = view_name

        final_sql = _render_view_sql(FINAL_SQL_NAME, replacements)
        _write_sql_snapshot(output_dir, FINAL_SQL_NAME, final_sql)
        if output_csv.exists():
            output_csv.unlink()
        escaped = str(output_csv).replace("'", "''")
        print(f"[build_surveillance_benchmark_48h] Writing {FINAL_OUTPUT_NAME} ...")
        con.execute(f"COPY ({final_sql}) TO '{escaped}' (HEADER, DELIMITER ',')")
    finally:
        con.close()

    _write_metadata(output_dir, db_path)
    print(f"[build_surveillance_benchmark_48h] Wrote {output_csv} ({_row_count(output_csv)} rows).")
    print("[build_surveillance_benchmark_48h] Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build only the final 48-hour 2k ICU surveillance benchmark CSV."
    )
    parser.add_argument("--db-path", help="Path to mimic4_dk.db.")
    parser.add_argument("--mimic-root", help="Path to a MIMIC-IV project root; the script will search for mimic4_dk.db.")
    parser.add_argument("--output-dir", required=True, help="Directory for the generated benchmark CSV.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing benchmark CSV.")
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db_path, args.mimic_root)
    output_dir = Path(args.output_dir).expanduser().resolve()
    build_final_benchmark_48h(db_path, output_dir, force=args.force)


if __name__ == "__main__":
    main()
