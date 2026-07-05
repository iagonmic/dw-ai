from __future__ import annotations

import math
from typing import Any

import duckdb

from dw_ai.models import ColumnProfile, DatasetProfile, RelationshipCandidate, SourceRegistry, TableProfile
from dw_ai.utils import quote_ident, singularize

NUMERIC_TYPES = ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL", "HUGEINT", "UBIGINT", "BIGINT", "SMALLINT")
TEMPORAL_TYPES = ("DATE", "TIME", "TIMESTAMP")
ID_HINTS = (
    "id",
    "key",
    "code",
    "codigo",
    "código",
    "number",
    "numero",
    "número",
    "num",
    "uuid",
    "matricula",
    "matrícula",
)
PORTUGUESE_TABLE_KEY_ALIASES = {
    "componentes": {"id_disciplina", "codigo_componente_curricular", "codigo_disciplina"},
    "cursos": {"id_curso", "id_estrutura_curricular"},
    "discentes": {"id_discente"},
    "docentes": {"id_pessoa"},
    "matriculas": set(),
}


def profile_duckdb(
    conn: duckdb.DuckDBPyConnection,
    registry: SourceRegistry,
    sample_rows: int = 100,
) -> DatasetProfile:
    """Profile every registered DuckDB relation and infer likely table relationships."""
    tables = [_profile_table(conn, source.name, sample_rows=sample_rows) for source in registry.tables]
    relationships = infer_relationships(conn, tables)
    return DatasetProfile(tables=tables, relationships=relationships)


def infer_relationships(
    conn: duckdb.DuckDBPyConnection,
    tables: list[TableProfile],
    max_checks: int = 200,
) -> list[RelationshipCandidate]:
    """Infer foreign-key-like relationships from identifier names and sampled value overlap."""
    candidates: list[RelationshipCandidate] = []
    key_columns = {
        table.name: [col for col in table.columns if col.is_candidate_key or col.name in {"id", f"{table.name}_id"}]
        for table in tables
    }
    checks = 0
    for from_table in tables:
        for from_col in from_table.columns:
            if not from_col.is_identifier or _is_table_primary_key_name(from_table.name, from_col.name):
                continue
            # Compare id-like columns against candidate keys in other tables. The final
            # confidence still depends on value overlap, which keeps weak name matches conservative.
            normalized = from_col.name.removesuffix("_id")
            for to_table in tables:
                if from_table.name == to_table.name:
                    continue
                for to_col in key_columns.get(to_table.name, []):
                    if checks >= max_checks:
                        return sorted(candidates, key=lambda item: item.confidence, reverse=True)
                    checks += 1
                    name_match = _identifier_names_match(from_col.name, to_table.name, to_col.name)
                    if not name_match and from_col.name != to_col.name:
                        continue
                    confidence = _relationship_confidence(conn, from_table.name, from_col.name, to_table.name, to_col.name)
                    if confidence >= _relationship_threshold(from_col.name, to_table.name, to_col.name):
                        candidates.append(
                            RelationshipCandidate(
                                from_table=from_table.name,
                                from_column=from_col.name,
                                to_table=to_table.name,
                                to_column=to_col.name,
                                confidence=round(confidence, 3),
                                reason="Identifier naming and sampled value overlap suggest a foreign-key relationship.",
                            )
                        )
    return sorted(candidates, key=lambda item: item.confidence, reverse=True)


def _profile_table(conn: duckdb.DuckDBPyConnection, table_name: str, sample_rows: int) -> TableProfile:
    """Collect row count, column profiles, and a bounded sample for one DuckDB table."""
    relation = quote_ident(table_name)
    row_count = conn.execute(f"SELECT COUNT(*) FROM {relation}").fetchone()[0]
    describe_rows = conn.execute(f"DESCRIBE {relation}").fetchall()
    sample = _sample_rows(conn, table_name, sample_rows)
    columns = [
        _profile_column(conn, table_name, column_name, data_type, row_count)
        for column_name, data_type, *_rest in describe_rows
    ]
    return TableProfile(name=table_name, row_count=row_count, columns=columns, sample_rows=sample)


def _profile_column(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    column_name: str,
    data_type: str,
    row_count: int,
) -> ColumnProfile:
    """Profile one column and classify broad semantic roles used by the modeller."""
    relation = quote_ident(table_name)
    column = quote_ident(column_name)
    null_count, distinct_count = conn.execute(
        f"SELECT COUNT(*) FILTER (WHERE {column} IS NULL), COUNT(DISTINCT {column}) FROM {relation}"
    ).fetchone()
    samples = [
        _jsonable(row[0])
        for row in conn.execute(
            f"SELECT DISTINCT {column} FROM {relation} WHERE {column} IS NOT NULL LIMIT 5"
        ).fetchall()
    ]
    upper_type = data_type.upper()
    unique_ratio = float(distinct_count / row_count) if row_count else 0.0
    lower_name = column_name.lower()
    is_numeric = any(type_name in upper_type for type_name in NUMERIC_TYPES)
    is_temporal = any(type_name in upper_type for type_name in TEMPORAL_TYPES) or _is_temporal_name(lower_name)
    is_identifier = lower_name == "id" or lower_name.endswith("_id") or any(hint in lower_name for hint in ID_HINTS)
    is_candidate_key = (
        row_count > 0
        and unique_ratio >= 0.98
        and null_count == 0
        and is_identifier
        and _is_table_primary_key_name(table_name, column_name)
    )
    return ColumnProfile(
        name=column_name,
        data_type=data_type,
        null_count=int(null_count or 0),
        null_rate=float((null_count or 0) / row_count) if row_count else 0.0,
        distinct_count=int(distinct_count or 0),
        unique_ratio=unique_ratio,
        sample_values=samples,
        is_numeric=is_numeric,
        is_temporal=is_temporal,
        is_identifier=is_identifier,
        is_candidate_key=is_candidate_key,
    )


def _relationship_confidence(
    conn: duckdb.DuckDBPyConnection,
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
) -> float:
    """Measure how many non-null source values are found in the target key column."""
    source = quote_ident(from_table)
    target = quote_ident(to_table)
    source_col = quote_ident(from_column)
    target_col = quote_ident(to_column)
    matched, total = conn.execute(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE src.{source_col} IS NOT NULL AND tgt.{target_col} IS NOT NULL),
            COUNT(*) FILTER (WHERE src.{source_col} IS NOT NULL)
        FROM {source} src
        LEFT JOIN {target} tgt
          ON cast(src.{source_col} as varchar) = cast(tgt.{target_col} as varchar)
        """
    ).fetchone()
    if not total:
        return 0.0
    return min(1.0, float(matched / total))


def _is_table_primary_key_name(table_name: str, column_name: str) -> bool:
    lower_column = column_name.lower()
    singular_table = singularize(table_name.lower())
    alias_keys = PORTUGUESE_TABLE_KEY_ALIASES.get(table_name.lower(), set())
    return (
        lower_column in {"id", f"{singular_table}_id", f"id_{singular_table}", f"{table_name.lower()}_id"}
        or lower_column in alias_keys
        or lower_column.endswith("_key")
    )


def _is_temporal_name(column_name: str) -> bool:
    tokens = [token for token in column_name.replace("__", "_").split("_") if token]
    if column_name.endswith("_at") or column_name.startswith("dt_"):
        return True
    if any(
        token in {"date", "time", "data", "year", "term", "semester", "month", "ano", "periodo", "período", "semestre", "mes", "mês"}
        for token in tokens
    ):
        return True
    return any(
        token in {"nascimento", "admissao", "admissão", "desligamento"}
        for token in tokens
    )


def _identifier_names_match(from_column: str, to_table: str, to_column: str) -> bool:
    from_lower = from_column.lower()
    to_lower = to_column.lower()
    table_lower = to_table.lower()
    table_singular = singularize(table_lower)
    table_key_aliases = PORTUGUESE_TABLE_KEY_ALIASES.get(table_lower, set())
    normalized_from = from_lower.removesuffix("_id")
    return (
        from_lower == to_lower
        or from_lower in table_key_aliases
        or normalized_from in {table_lower, table_singular, to_lower.removesuffix("_id")}
        or from_lower in {f"id_{table_singular}", f"{table_singular}_id"}
    )


def _relationship_threshold(from_column: str, to_table: str, to_column: str) -> float:
    table_aliases = PORTUGUESE_TABLE_KEY_ALIASES.get(to_table.lower(), set())
    exact_domain_key = from_column.lower() == to_column.lower() or from_column.lower() in table_aliases
    return 0.25 if exact_domain_key else 0.55


def _sample_rows(conn: duckdb.DuckDBPyConnection, table_name: str, sample_rows: int) -> list[dict[str, Any]]:
    rows = conn.execute(f"SELECT * FROM {quote_ident(table_name)} LIMIT {int(sample_rows)}").fetchdf()
    return [{key: _jsonable(value) for key, value in record.items()} for record in rows.to_dict("records")]


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except Exception:
        pass
    if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
