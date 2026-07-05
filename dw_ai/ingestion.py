from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from dw_ai.models import SourceRegistry, SourceTable
from dw_ai.utils import quote_ident, sanitize_identifier, sql_literal

SUPPORTED_FILE_SUFFIXES = {".csv", ".tsv", ".xlsx", ".parquet", ".json", ".ndjson"}


def ingest_files(paths: list[Path]) -> tuple[duckdb.DuckDBPyConnection, SourceRegistry]:
    """Load supported uploaded files into an in-memory DuckDB database."""
    conn = duckdb.connect(database=":memory:")
    registry = SourceRegistry()
    used_names: set[str] = set()

    for path in paths:
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_FILE_SUFFIXES:
            raise ValueError(f"Unsupported file type: {path.suffix}")
        if suffix == ".xlsx":
            _ingest_xlsx(conn, registry, path, used_names)
            continue
        table_name = _unique_name(sanitize_identifier(path.stem), used_names)
        relation = quote_ident(table_name)
        file_literal = sql_literal(str(path))

        if suffix == ".csv":
            conn.execute(f"CREATE TABLE {relation} AS SELECT * FROM read_csv_auto({file_literal})")
        elif suffix == ".tsv":
            conn.execute(f"CREATE TABLE {relation} AS SELECT * FROM read_csv_auto({file_literal}, delim='\\t')")
        elif suffix == ".parquet":
            conn.execute(f"CREATE TABLE {relation} AS SELECT * FROM read_parquet({file_literal})")
        elif suffix in {".json", ".ndjson"}:
            conn.execute(f"CREATE TABLE {relation} AS SELECT * FROM read_json_auto({file_literal})")

        registry.tables.append(
            SourceTable(
                name=table_name,
                relation=table_name,
                original_name=path.name,
                source_type=suffix.lstrip("."),
                path=str(path),
            )
        )

    return conn, registry


def introspect_postgres(connection_string: str, schema: str = "public") -> tuple[duckdb.DuckDBPyConnection, SourceRegistry]:
    """Attach PostgreSQL read-only through DuckDB and expose each base table as a local view."""
    conn = duckdb.connect(database=":memory:")
    safe_schema = schema.replace("'", "''")
    safe_connection = connection_string.replace("'", "''")
    conn.execute("INSTALL postgres")
    conn.execute("LOAD postgres")
    conn.execute(
        f"ATTACH '{safe_connection}' AS pg_source (TYPE postgres, READ_ONLY, SCHEMA '{safe_schema}')"
    )
    rows = conn.execute(
        """
        SELECT table_name
        FROM pg_source.information_schema.tables
        WHERE table_schema = ?
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        [schema],
    ).fetchall()
    registry = SourceRegistry()
    for (table_name,) in rows:
        safe_name = sanitize_identifier(table_name)
        conn.execute(
            f"CREATE VIEW {quote_ident(safe_name)} AS SELECT * FROM pg_source.{quote_ident(schema)}.{quote_ident(table_name)}"
        )
        registry.tables.append(
            SourceTable(
                name=safe_name,
                relation=safe_name,
                original_name=f"{schema}.{table_name}",
                source_type="postgres",
            )
        )
    return conn, registry


def _ingest_xlsx(
    conn: duckdb.DuckDBPyConnection,
    registry: SourceRegistry,
    path: Path,
    used_names: set[str],
) -> None:
    workbook = pd.ExcelFile(path)
    for sheet_name in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet_name)
        base_name = sanitize_identifier(path.stem if len(workbook.sheet_names) == 1 else f"{path.stem}_{sheet_name}")
        table_name = _unique_name(base_name, used_names)
        conn.register("_dw_ai_frame", frame)
        conn.execute(f"CREATE TABLE {quote_ident(table_name)} AS SELECT * FROM _dw_ai_frame")
        conn.unregister("_dw_ai_frame")
        registry.tables.append(
            SourceTable(
                name=table_name,
                relation=table_name,
                original_name=f"{path.name}:{sheet_name}",
                source_type="xlsx",
                path=str(path),
            )
        )


def _unique_name(base: str, used: set[str]) -> str:
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate
