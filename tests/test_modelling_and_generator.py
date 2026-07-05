from __future__ import annotations

from pathlib import Path

import pandas as pd

from dw_ai.artifacts import build_artifact_zip
from dw_ai.ingestion import ingest_files
from dw_ai.modelling import deterministic_model_plan
from dw_ai.profiling import profile_duckdb


def test_orders_scenario_generates_fact_dimensions_date_and_dbt_files(tmp_path: Path) -> None:
    orders = pd.DataFrame(
        {
            "id": [1, 2],
            "customer_id": [10, 11],
            "order_date": ["2026-01-01", "2026-01-02"],
            "total_amount": [100.0, 200.0],
        }
    )
    customers = pd.DataFrame({"id": [10, 11], "customer_name": ["Ada", "Lin"]})
    products = pd.DataFrame({"id": [20, 21], "product_name": ["Book", "Desk"]})
    order_items = pd.DataFrame(
        {"id": [100, 101], "order_id": [1, 2], "product_id": [20, 21], "quantity": [1, 2], "line_amount": [40, 60]}
    )

    paths = []
    for name, frame in {
        "orders": orders,
        "customers": customers,
        "products": products,
        "order_items": order_items,
    }.items():
        path = tmp_path / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)

    conn, registry = ingest_files(paths)
    profile = profile_duckdb(conn, registry)
    plan = deterministic_model_plan(profile)
    zip_bytes, artifact = build_artifact_zip(plan, profile, registry)

    assert zip_bytes
    assert any(fact.name in {"fct_order", "fct_order_item"} for fact in plan.facts)
    assert "dim_customer" in {dimension.name for dimension in plan.dimensions}
    assert "dim_product" in {dimension.name for dimension in plan.dimensions}
    assert plan.date_dimension
    assert "models/sources.yml" in artifact.files
    assert any(path.startswith("models/marts/fct_") for path in artifact.files)
    assert "{{ source('raw', 'orders') }}" in artifact.files["models/staging/stg_orders.sql"]
    assert "ref('stg_orders')" in artifact.files["models/marts/dim_date.sql"]
    assert "ref('fct_" not in artifact.files["models/marts/dim_date.sql"]
    assert "erDiagram" in artifact.diagram
    assert "diagram_compact.mmd" in artifact.files
    assert "flowchart LR" in artifact.files["diagram_compact.mmd"]


def test_weak_relationships_record_assumption(tmp_path: Path) -> None:
    sales = pd.DataFrame({"sale_code": ["A", "B"], "amount": [10, 20], "region": ["North", "South"]})
    path = tmp_path / "sales.csv"
    sales.to_csv(path, index=False)

    conn, registry = ingest_files([path])
    profile = profile_duckdb(conn, registry)
    plan = deterministic_model_plan(profile)

    assert plan.facts
    assert any("No reliable relationships" in assumption for assumption in plan.assumptions)
    assert any(dimension.name == "dim_region" for dimension in plan.dimensions)
