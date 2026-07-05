from __future__ import annotations

import re
from typing import Any


PORTUGUESE_SINGULARS = {
    "componentes": "componente",
    "courses": "course",
    "cursos": "curso",
    "discentes": "discente",
    "docentes": "docente",
    "disciplinas": "disciplina",
    "diagnoses": "diagnosis",
    "matriculas": "matricula",
    "módulos": "modulo",
    "modulos": "modulo",
}


def sanitize_identifier(value: str, default: str = "table") -> str:
    """Normalize external file, sheet, and column names into SQL-safe identifiers."""
    cleaned = re.sub(r"[^0-9a-zA-Z_]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = default
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def singularize(name: str) -> str:
    """Return a conservative singular form for English and common Portuguese table names."""
    if name in PORTUGUESE_SINGULARS:
        return PORTUGUESE_SINGULARS[name]
    if name.endswith("ies") and len(name) > 3:
        return f"{name[:-3]}y"
    if name.endswith("ses"):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def quote_ident(identifier: str) -> str:
    """Quote a SQL identifier for DuckDB-generated SQL."""
    return '"' + identifier.replace('"', '""') + '"'


def sql_literal(value: str) -> str:
    """Quote a SQL string literal for DuckDB-generated SQL."""
    return "'" + value.replace("'", "''") + "'"


def model_to_dict(model: Any) -> dict[str, Any]:
    """Bridge Pydantic v1/v2 style serialization for app and test code."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
