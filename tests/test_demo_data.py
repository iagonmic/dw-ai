from __future__ import annotations

from pathlib import Path

from dw_ai.artifacts import build_artifact_zip
from dw_ai.ingestion import ingest_files
from dw_ai.modelling import deterministic_model_plan
from dw_ai.profiling import profile_duckdb


def test_demo_data_scenarios_are_small_and_modelable() -> None:
    base = Path("test_data")
    scenarios = ["easy_retail", "medium_university", "hard_healthcare"]

    for scenario in scenarios:
        paths = sorted((base / scenario).glob("*.csv"))
        assert paths, f"{scenario} should include CSV files"

        conn, registry = ingest_files(paths)
        profile = profile_duckdb(conn, registry, sample_rows=20)
        plan = deterministic_model_plan(profile)
        zip_bytes, artifact = build_artifact_zip(plan, profile, registry)

        assert all(table.row_count <= 20 for table in profile.tables)
        assert plan.facts, f"{scenario} should generate at least one fact"
        assert zip_bytes
        assert "diagram_compact.mmd" in artifact.files
        fact_names = {fact.name for fact in plan.facts}
        assert "fct_employee" not in fact_names
        assert "fct_provider" not in fact_names


def test_medium_university_is_english_and_has_clear_enrollment_pattern() -> None:
    base = Path("test_data/medium_university")
    conn, registry = ingest_files(sorted(base.glob("*.csv")))
    profile = profile_duckdb(conn, registry, sample_rows=20)
    plan = deterministic_model_plan(profile)

    assert {source.name for source in registry.tables} == {
        "course_components",
        "enrollments",
        "instructors",
        "program_courses",
        "students",
    }
    assert any(fact.name == "fct_enrollment" for fact in plan.facts)
    assert {"dim_student", "dim_instructor", "dim_course_component"}.issubset({dimension.name for dimension in plan.dimensions})
    assert any(column.name == "year" and column.is_temporal for column in profile.table("enrollments").columns)
    assert any(column.name == "term" and column.is_temporal for column in profile.table("enrollments").columns)
