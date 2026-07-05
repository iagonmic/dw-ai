from __future__ import annotations

import yaml

from dw_ai.diagram import build_compact_mermaid_diagram, build_mermaid_diagram
from dw_ai.models import ArtifactBundle, DatasetProfile, DimensionModel, FactModel, ModelPlan, SourceRegistry, TableProfile
from dw_ai.utils import quote_ident


def generate_dbt_project(plan: ModelPlan, profile: DatasetProfile, registry: SourceRegistry) -> ArtifactBundle:
    """Render a complete dbt DuckDB project from a validated dimensional model plan."""
    files: dict[str, str] = {
        "dbt_project.yml": _dbt_project_yml(),
        "profiles.yml.example": _profiles_yml(),
        "README.md": _readme(plan),
        "models/sources.yml": _sources_yml(profile, registry),
        "models/marts/schema.yml": _schema_yml(plan),
    }

    for table in profile.tables:
        files[f"models/staging/stg_{table.name}.sql"] = _staging_model_sql(table)

    if plan.date_dimension:
        files["models/marts/dim_date.sql"] = _date_dimension_sql(plan)

    for dimension in plan.dimensions:
        if dimension.name == "dim_date":
            continue
        files[f"models/marts/{dimension.name}.sql"] = _dimension_sql(dimension)

    for fact in plan.facts:
        files[f"models/marts/{fact.name}.sql"] = _fact_sql(fact, plan)

    diagram = build_mermaid_diagram(plan)
    compact_diagram = build_compact_mermaid_diagram(plan)
    files["diagram.mmd"] = diagram
    files["diagram_compact.mmd"] = compact_diagram
    return ArtifactBundle(files=files, diagram=diagram)


def _dbt_project_yml() -> str:
    return yaml.safe_dump(
        {
            "name": "dw_ai_generated",
            "version": "1.0.0",
            "config-version": 2,
            "profile": "dw_ai_duckdb",
            "model-paths": ["models"],
            "models": {
                "dw_ai_generated": {
                    "staging": {"+materialized": "view"},
                    "marts": {"+materialized": "table"},
                }
            },
        },
        sort_keys=False,
    )


def _profiles_yml() -> str:
    return yaml.safe_dump(
        {
            "dw_ai_duckdb": {
                "target": "dev",
                "outputs": {
                    "dev": {
                        "type": "duckdb",
                        "path": "dw_ai.duckdb",
                        "threads": 4,
                    }
                },
            }
        },
        sort_keys=False,
    )


def _sources_yml(profile: DatasetProfile, registry: SourceRegistry) -> str:
    table_lookup = {source.name: source for source in registry.tables}
    return yaml.safe_dump(
        {
            "version": 2,
            "sources": [
                {
                    "name": registry.name,
                    "schema": "main",
                    "description": "Raw source tables ingested by DW-AI.",
                    "tables": [
                        {
                            "name": table.name,
                            "identifier": table_lookup.get(table.name).relation if table.name in table_lookup else table.name,
                            "description": f"Raw table generated from {table_lookup[table.name].original_name if table.name in table_lookup else table.name}.",
                            "columns": [
                                {
                                    "name": column.name,
                                    "description": f"Detected type: {column.data_type}.",
                                    **({"data_tests": ["not_null", "unique"]} if column.is_candidate_key else {}),
                                }
                                for column in table.columns
                            ],
                        }
                        for table in profile.tables
                    ],
                }
            ],
        },
        sort_keys=False,
    )


def _schema_yml(plan: ModelPlan) -> str:
    dimension_lookup = {dimension.name: dimension for dimension in plan.dimensions}
    models = []
    for dimension in plan.dimensions:
        columns = [{"name": dimension.surrogate_key, "data_tests": ["not_null", "unique"]}]
        columns.extend({"name": column} for column in dimension.columns if column != dimension.surrogate_key)
        models.append({"name": dimension.name, "description": dimension.description, "columns": columns})
    for fact in plan.facts:
        columns = [{"name": "fact_row_key", "data_tests": ["not_null", "unique"]}]
        columns.extend({"name": measure} for measure in fact.measures)
        for dimension_ref in fact.dimensions:
            dimension = dimension_lookup.get(dimension_ref.dimension)
            if not dimension:
                continue
            columns.append(
                {
                    "name": dimension.surrogate_key,
                    "data_tests": [
                        "not_null",
                        {"relationships": {"to": f"ref('{dimension.name}')", "field": dimension.surrogate_key}},
                    ],
                }
            )
        models.append({"name": fact.name, "description": fact.description or fact.grain, "columns": columns})
    return yaml.safe_dump({"version": 2, "models": models}, sort_keys=False)


def _staging_model_sql(table: TableProfile) -> str:
    columns = ",\n    ".join(quote_ident(column.name) for column in table.columns)
    return (
        "with source as (\n"
        f"    select * from {{{{ source('raw', '{table.name}') }}}}\n"
        ")\n\n"
        "select\n"
        f"    {columns}\n"
        "from source\n"
    )


def _dimension_sql(dimension: DimensionModel) -> str:
    if not dimension.source_table:
        return ""
    select_columns = [f"    md5(cast({quote_ident(dimension.natural_key or dimension.columns[0])} as varchar)) as {dimension.surrogate_key}"]
    if dimension.natural_key:
        select_columns.append(f"    {quote_ident(dimension.natural_key)} as natural_key")
    select_columns.extend(f"    {quote_ident(column)}" for column in dimension.columns if column != dimension.natural_key)
    return (
        f"with source as (\n    select * from {{{{ ref('stg_{dimension.source_table}') }}}}\n),\n"
        "deduplicated as (\n"
        "    select distinct\n"
        + ",\n".join(select_columns)
        + "\n    from source\n"
        ")\n\n"
        "select * from deduplicated\n"
    )


def _fact_sql(fact: FactModel, plan: ModelPlan) -> str:
    dimension_lookup = {dimension.name: dimension for dimension in plan.dimensions}
    select_columns = ["    md5(cast(row_number() over () as varchar)) as fact_row_key"]
    for dim_ref in fact.dimensions:
        dimension = dimension_lookup.get(dim_ref.dimension)
        if dimension:
            select_columns.append(f"    {dim_ref.dimension}.{dimension.surrogate_key} as {dimension.surrogate_key}")
    select_columns.extend(f"    cast(source.{quote_ident(date_col)} as date) as {date_col}" for date_col in fact.date_columns)
    select_columns.extend(f"    source.{quote_ident(measure)}" for measure in fact.measures)
    select_columns.extend(f"    source.{quote_ident(degenerate)}" for degenerate in fact.degenerate_dimensions)
    if len(select_columns) == 1:
        select_columns.append("    source.*")
    joins = []
    for dim in fact.dimensions:
        joins.append(
            f"left join {{{{ ref('{dim.dimension}') }}}} as {dim.dimension}\n"
            f"  on source.{quote_ident(dim.source_column)} = {dim.dimension}.natural_key"
        )
    if plan.date_dimension and fact.date_columns:
        joins.append(
            f"left join {{{{ ref('dim_date') }}}} as dim_date\n"
            f"  on cast(source.{quote_ident(fact.date_columns[0])} as date) = dim_date.date_day"
        )
    return (
        f"with source as (\n    select * from {{{{ ref('stg_{fact.source_table}') }}}}\n)\n\n"
        "select\n"
        + ",\n".join(select_columns)
        + "\nfrom source\n"
        + ("\n".join(joins) + "\n" if joins else "")
    )


def _date_dimension_sql(plan: ModelPlan) -> str:
    date_selects = []
    for fact in plan.facts:
        for date_column in fact.date_columns:
            date_selects.append(
                f"select cast({quote_ident(date_column)} as date) as date_day from {{{{ ref('stg_{fact.source_table}') }}}}"
            )
    unioned = "\nunion\n".join(date_selects) or "select current_date as date_day"
    return (
        "with dates as (\n"
        f"    {unioned}\n"
        "), distinct_dates as (\n"
        "    select distinct date_day from dates where date_day is not null\n"
        ")\n\n"
        "select\n"
        "    cast(strftime(date_day, '%Y%m%d') as integer) as date_key,\n"
        "    date_day,\n"
        "    year(date_day) as year,\n"
        "    quarter(date_day) as quarter,\n"
        "    month(date_day) as month,\n"
        "    strftime(date_day, '%B') as month_name,\n"
        "    day(date_day) as day_of_month,\n"
        "    dayofweek(date_day) as day_of_week\n"
        "from distinct_dates\n"
    )


def _readme(plan: ModelPlan) -> str:
    facts = "\n".join(f"- `{fact.name}`: {fact.grain}" for fact in plan.facts) or "- No facts generated."
    dimensions = "\n".join(f"- `{dim.name}`" for dim in plan.dimensions) or "- No dimensions generated."
    assumptions = "\n".join(f"- {item}" for item in plan.assumptions) or "- None."
    questions = "\n".join(f"- {item}" for item in plan.unresolved_questions) or "- None."
    return f"""# DW-AI Generated dbt Project

## Facts
{facts}

## Dimensions
{dimensions}

## Assumptions
{assumptions}

## Unresolved Questions
{questions}

## Run
Install `dbt-duckdb`, copy `profiles.yml.example` into your dbt profiles directory or pass it with `--profiles-dir`, load the raw tables into `dw_ai.duckdb`, then run:

```bash
dbt run
dbt test
```
"""
