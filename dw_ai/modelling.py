from __future__ import annotations

from collections import defaultdict

from dw_ai.models import DatasetProfile, DimensionModel, DimensionRef, FactModel, ModelPlan, TableProfile
from dw_ai.utils import singularize


def deterministic_model_plan(profile: DatasetProfile) -> ModelPlan:
    """Build a conservative Kimball model from metadata without calling an LLM."""
    if not profile.tables:
        return ModelPlan(
            assumptions=["No tables were detected."],
            unresolved_questions=["Provide at least one supported data source."],
            confidence=0.0,
            rationale="No dimensional model could be generated because the dataset is empty.",
        )

    relationship_count = defaultdict(int)
    for rel in profile.relationships:
        relationship_count[rel.from_table] += 1

    fact_tables = [table for table in profile.tables if _fact_score(table, relationship_count[table.name]) >= 2]
    if not fact_tables:
        fact_tables = [max(profile.tables, key=lambda table: (_measure_count(table), relationship_count[table.name], table.row_count))]

    dimensions: dict[str, DimensionModel] = {}
    facts: list[FactModel] = []

    for table in profile.tables:
        if table.name not in {fact.name for fact in fact_tables}:
            dimensions[_dimension_name(table.name)] = _dimension_from_table(table)

    for fact_table in fact_tables:
        fact = _fact_from_table(fact_table, profile)
        for rel in profile.relationships:
            if rel.from_table != fact_table.name:
                continue
            dim_name = _dimension_name(rel.to_table)
            if dim_name not in dimensions:
                dimensions[dim_name] = _dimension_from_table(profile.table(rel.to_table))
            facts_dimension = DimensionRef(
                dimension=dim_name,
                source_column=rel.from_column,
                dimension_key=rel.to_column,
            )
            if facts_dimension not in fact.dimensions:
                fact.dimensions.append(facts_dimension)
        facts.append(fact)

    if len(profile.tables) == 1:
        dimensions.update(_dimensions_from_flat_table(profile.tables[0]))

    date_dimension = any(fact.date_columns for fact in facts)
    if date_dimension:
        dimensions["dim_date"] = DimensionModel(
            name="dim_date",
            source_table=None,
            natural_key="date_day",
            surrogate_key="date_key",
            columns=["date_day", "year", "quarter", "month", "month_name", "day_of_month", "day_of_week"],
            description="Calendar dimension generated from temporal columns detected in fact tables.",
        )

    assumptions = [
        "This model was generated from schema, profiling statistics, and bounded samples.",
        "Review grains, measures, and relationship tests before using the dbt project in production.",
    ]
    if not profile.relationships:
        assumptions.append("No reliable relationships were detected; joins are intentionally conservative.")
    for rel in profile.relationships:
        if rel.confidence < 0.55:
            assumptions.append(
                f"Relationship {rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column} has partial value overlap "
                f"({rel.confidence:.0%}); review source coverage before production use."
            )

    return ModelPlan(
        facts=facts,
        dimensions=sorted(dimensions.values(), key=lambda dim: dim.name),
        date_dimension=date_dimension,
        assumptions=assumptions,
        unresolved_questions=[],
        confidence=0.72 if profile.relationships else 0.55,
        rationale="Deterministic Kimball heuristics identified transaction-like fact tables, descriptive dimensions, measures, and date columns.",
    )


def _fact_score(table: TableProfile, relation_count: int) -> int:
    """Score how likely a source table is to represent measurable business events."""
    transactional_name = any(
        token in table.name
        for token in (
            "order",
            "sale",
            "transaction",
            "payment",
            "invoice",
            "event",
            "line",
            "item",
            "matricula",
            "matrícula",
            "inscricao",
            "inscrição",
            "avaliacao",
            "avaliação",
        )
    )
    if relation_count < 2 and not transactional_name:
        return 0

    score = relation_count
    if _measure_count(table) > 0:
        score += 1
    if any(col.is_temporal for col in table.columns):
        score += 1
    if transactional_name:
        score += 1
    return score


def _measure_count(table: TableProfile) -> int:
    return len([col for col in table.columns if col.is_numeric and not col.is_identifier])


def _fact_from_table(table: TableProfile, profile: DatasetProfile) -> FactModel:
    """Translate one source table into a fact model proposal."""
    measures = [col.name for col in table.columns if col.is_numeric and not col.is_identifier]
    date_columns = [col.name for col in table.columns if col.is_temporal]
    related_fk_columns = {rel.from_column for rel in profile.relationships if rel.from_table == table.name}
    degenerate_dimensions = [
        col.name
        for col in table.columns
        if col.is_identifier and not col.is_candidate_key and col.name not in related_fk_columns and not col.name.endswith("_id")
    ]
    return FactModel(
        name=f"fct_{singularize(table.name)}",
        source_table=table.name,
        grain=f"One row per {singularize(table.name)} source record.",
        measures=measures,
        degenerate_dimensions=degenerate_dimensions,
        date_columns=date_columns,
        description=f"Fact table generated from source table {table.name}.",
    )


def _dimension_from_table(table: TableProfile) -> DimensionModel:
    """Translate one descriptive source table into a dimension model proposal."""
    key = next((col.name for col in table.columns if col.is_candidate_key), None)
    descriptive_columns = [col.name for col in table.columns if not col.is_candidate_key and not col.is_temporal]
    return DimensionModel(
        name=_dimension_name(table.name),
        source_table=table.name,
        natural_key=key,
        surrogate_key=f"{singularize(table.name)}_key",
        columns=descriptive_columns or [col.name for col in table.columns],
        description=f"Dimension generated from source table {table.name}.",
    )


def _dimensions_from_flat_table(table: TableProfile) -> dict[str, DimensionModel]:
    """Create lightweight dimensions for one-table datasets with descriptive columns."""
    dimensions: dict[str, DimensionModel] = {}
    descriptive = [col for col in table.columns if not col.is_numeric and not col.is_identifier and not col.is_temporal]
    for col in descriptive[:5]:
        dim_base = singularize(col.name.removesuffix("_name").removesuffix("_description"))
        dimensions[f"dim_{dim_base}"] = DimensionModel(
            name=f"dim_{dim_base}",
            source_table=table.name,
            natural_key=col.name,
            surrogate_key=f"{dim_base}_key",
            columns=[col.name],
            description=f"Inferred low-complexity dimension from descriptive column {col.name}.",
        )
    return dimensions


def _dimension_name(table_name: str) -> str:
    base = table_name
    if base.startswith("dim_"):
        return base
    return f"dim_{singularize(base)}"
