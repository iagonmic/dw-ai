from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from dw_ai.ingestion import ingest_files
from dw_ai.profiling import profile_duckdb


def test_ingests_csv_tsv_json_parquet_xlsx_and_profiles(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "id": [1, 2],
            "customer_id": [10, 11],
            "amount": [20.5, 30.0],
            "created_at": ["2026-01-01", "2026-01-02"],
        }
    )
    csv_path = tmp_path / "orders.csv"
    tsv_path = tmp_path / "payments.tsv"
    json_path = tmp_path / "events.ndjson"
    parquet_path = tmp_path / "items.parquet"
    xlsx_path = tmp_path / "customers.xlsx"

    frame.to_csv(csv_path, index=False)
    frame.to_csv(tsv_path, index=False, sep="\t")
    parquet_frame = pd.DataFrame({"id": [1, 2], "order_id": [1, 2], "quantity": [3, 4]})
    parquet_frame.to_parquet(parquet_path, index=False)
    xlsx_frame = pd.DataFrame({"id": [10, 11], "name": ["Ada", "Lin"]})
    xlsx_frame.to_excel(xlsx_path, index=False)
    json_path.write_text("\n".join(json.dumps(record) for record in frame.to_dict("records")), encoding="utf-8")

    conn, registry = ingest_files([csv_path, tsv_path, json_path, parquet_path, xlsx_path])
    profile = profile_duckdb(conn, registry, sample_rows=5)

    assert {table.name for table in registry.tables} == {"orders", "payments", "events", "items", "customers"}
    assert len(profile.tables) == 5
    orders = profile.table("orders")
    assert orders.row_count == 2
    assert any(column.name == "id" and column.is_candidate_key for column in orders.columns)


def test_infers_relationship_candidates(tmp_path: Path) -> None:
    orders = pd.DataFrame({"id": [1, 2], "customer_id": [10, 11], "total": [100, 200]})
    customers = pd.DataFrame({"id": [10, 11], "name": ["Ada", "Lin"]})
    orders_path = tmp_path / "orders.csv"
    customers_path = tmp_path / "customers.csv"
    orders.to_csv(orders_path, index=False)
    customers.to_csv(customers_path, index=False)

    conn, registry = ingest_files([orders_path, customers_path])
    profile = profile_duckdb(conn, registry)

    assert any(
        rel.from_table == "orders"
        and rel.from_column == "customer_id"
        and rel.to_table == "customers"
        and rel.to_column == "id"
        for rel in profile.relationships
    )


def test_profiles_portuguese_academic_identifiers_and_temporal_columns(tmp_path: Path) -> None:
    discentes = pd.DataFrame(
        {
            "id_discente": ["d1", "d2"],
            "sexo": ["F", "M"],
            "ano_ingresso": [2024, 2025],
            "periodo_ingresso": [1, 2],
        }
    )
    componentes = pd.DataFrame(
        {
            "id_disciplina": [10, 20],
            "nome": ["Banco de Dados", "Estatistica"],
            "ch_total": [60, 45],
        }
    )
    matriculas = pd.DataFrame(
        {
            "id_discente": ["d1", "d2"],
            "id_disciplina": [10, 20],
            "ano": ["2025", "2025"],
            "periodo": ["1", "2"],
            "situacao": ["APROVADO", "REPROVADO"],
        }
    )
    paths = []
    for name, frame in {"discentes": discentes, "componentes": componentes, "matriculas": matriculas}.items():
        path = tmp_path / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        paths.append(path)

    conn, registry = ingest_files(paths)
    profile = profile_duckdb(conn, registry)

    discentes_id = next(column for column in profile.table("discentes").columns if column.name == "id_discente")
    disciplina_id = next(column for column in profile.table("componentes").columns if column.name == "id_disciplina")
    ano = next(column for column in profile.table("matriculas").columns if column.name == "ano")
    periodo = next(column for column in profile.table("matriculas").columns if column.name == "periodo")

    assert discentes_id.is_candidate_key
    assert disciplina_id.is_candidate_key
    assert ano.is_temporal
    assert periodo.is_temporal
    assert any(
        rel.from_table == "matriculas"
        and rel.from_column == "id_discente"
        and rel.to_table == "discentes"
        and rel.to_column == "id_discente"
        for rel in profile.relationships
    )
    assert any(
        rel.from_table == "matriculas"
        and rel.from_column == "id_disciplina"
        and rel.to_table == "componentes"
        and rel.to_column == "id_disciplina"
        for rel in profile.relationships
    )
