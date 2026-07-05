from __future__ import annotations

from dw_ai.models import ModelPlan


def build_mermaid_diagram(plan: ModelPlan) -> str:
    """Render a Mermaid ER diagram that mirrors the generated dimensional model."""
    lines = ["erDiagram"]
    for dimension in plan.dimensions:
        lines.append(f"    {dimension.name} {{")
        lines.append(f"        string {dimension.surrogate_key} PK")
        if dimension.natural_key:
            lines.append(f"        string {dimension.natural_key} UK")
        for column in dimension.columns:
            if column not in {dimension.surrogate_key, dimension.natural_key}:
                lines.append(f"        string {column}")
        lines.append("    }")

    for fact in plan.facts:
        lines.append(f"    {fact.name} {{")
        lines.append("        string fact_row_key PK")
        for dimension in fact.dimensions:
            lines.append(f"        string {dimension.source_column} FK")
        for date_column in fact.date_columns:
            lines.append(f"        date {date_column}")
        for measure in fact.measures:
            lines.append(f"        number {measure}")
        lines.append("    }")
        for dimension_name in sorted({dimension.dimension for dimension in fact.dimensions}):
            lines.append(f"    {dimension_name} ||--o{{ {fact.name} : contextualizes")
        if plan.date_dimension and fact.date_columns:
            lines.append(f"    dim_date ||--o{{ {fact.name} : dates")
    return "\n".join(lines) + "\n"


def build_compact_mermaid_diagram(plan: ModelPlan) -> str:
    """Render a readable star-schema overview without listing every column."""
    lines = [
        "flowchart LR",
        "    classDef fact fill:#fff3cd,stroke:#b7791f,stroke-width:2px,color:#1f2937",
        "    classDef dimension fill:#e0f2fe,stroke:#0369a1,stroke-width:1px,color:#0f172a",
        "    classDef date fill:#dcfce7,stroke:#15803d,stroke-width:1px,color:#052e16",
    ]
    dimension_lookup = {dimension.name: dimension for dimension in plan.dimensions}
    used_dimensions: set[str] = set()

    for fact in plan.facts:
        measure_label = ", ".join(fact.measures[:4]) if fact.measures else "no measures detected"
        date_label = ", ".join(fact.date_columns[:3]) if fact.date_columns else "no dates"
        lines.append(f'    {fact.name}["{fact.name}<br/>grain: {fact.grain}<br/>measures: {measure_label}<br/>dates: {date_label}"]:::fact')
        for dimension_name in sorted({dimension.dimension for dimension in fact.dimensions}):
            dimension = dimension_lookup.get(dimension_name)
            if dimension:
                key_label = dimension.natural_key or dimension.surrogate_key
                lines.append(f'    {dimension.name}["{dimension.name}<br/>key: {key_label}"]:::dimension')
                lines.append(f"    {dimension.name} --> {fact.name}")
                used_dimensions.add(dimension.name)
        if plan.date_dimension and fact.date_columns:
            lines.append('    dim_date["dim_date<br/>calendar attributes"]:::date')
            lines.append(f"    dim_date --> {fact.name}")
            used_dimensions.add("dim_date")

    for dimension in plan.dimensions:
        if dimension.name not in used_dimensions and dimension.name != "dim_date":
            key_label = dimension.natural_key or dimension.surrogate_key
            lines.append(f'    {dimension.name}["{dimension.name}<br/>key: {key_label}"]:::dimension')
    return "\n".join(lines) + "\n"
