from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from dw_ai.ai_agent import AIProviderConfig, GROQ_DEFAULT_MODEL, OPENAI_DEFAULT_MODEL, generate_model_plan, list_provider_models
from dw_ai.artifacts import build_artifact_zip
from dw_ai.ingestion import SUPPORTED_FILE_SUFFIXES, ingest_files, introspect_postgres
from dw_ai.modelling import deterministic_model_plan
from dw_ai.profiling import profile_duckdb
from dw_ai.utils import model_to_dict

DEMO_SCENARIOS = {
    "Easy - Retail": Path("test_data/easy_retail"),
    "Medium - University": Path("test_data/medium_university"),
    "Hard - Healthcare": Path("test_data/hard_healthcare"),
}


TEXT = {
    "English": {
        "title": "DW-AI",
        "caption": "Generate Kimball-style dimensional models and dbt projects from operational data.",
        "input": "Input",
        "language": "Language",
        "source": "Source",
        "custom_data": "Custom data",
        "files": "Files",
        "demo_data": "Demo data",
        "postgres": "PostgreSQL",
        "upload_help": "Upload CSV, TSV, XLSX, Parquet, JSON, or NDJSON files.",
        "demo_help": "Use built-in sample data when you do not have files ready.",
        "demo_disabled": "Sample data is disabled while custom files are uploaded.",
        "demo_scenario": "Demo scenario",
        "load_demo": "Load demo data",
        "demo_loaded": "Loaded demo data",
        "sample_rows": "Sample rows per table",
        "use_ai": "Use OpenAI when available",
        "ai_caption": "The AI receives metadata and bounded samples only.",
        "upload": "Upload one or more enterprise data files",
        "pg_warning": "Use a read-only PostgreSQL user for demos.",
        "connection": "Connection string",
        "schema": "Schema",
        "inspect_pg": "Inspect PostgreSQL",
        "detected": "Detected Data",
        "tables": "Tables",
        "relationships": "Relationships",
        "profile_depth": "Profile depth",
        "generate": "Generate dimensional model",
        "spinner": "Modelling facts, dimensions, dbt files, and diagram...",
        "generated": "Generated Model",
        "diagram": "Diagram",
        "dbt_project": "dbt Project",
        "download": "Download dbt project ZIP",
    },
    "Português": {
        "title": "DW-AI",
        "caption": "Gere modelos dimensionais Kimball e projetos dbt a partir de dados operacionais.",
        "input": "Entrada",
        "language": "Idioma",
        "source": "Fonte",
        "custom_data": "Dados personalizados",
        "files": "Arquivos",
        "demo_data": "Dados de teste",
        "postgres": "PostgreSQL",
        "upload_help": "Envie arquivos CSV, TSV, XLSX, Parquet, JSON ou NDJSON.",
        "demo_help": "Use dados de exemplo quando ainda nao tiver arquivos.",
        "demo_disabled": "Os dados de exemplo ficam desativados enquanto arquivos personalizados estao enviados.",
        "demo_scenario": "Cenario de teste",
        "load_demo": "Carregar dados de teste",
        "demo_loaded": "Dados de teste carregados",
        "sample_rows": "Linhas de amostra por tabela",
        "use_ai": "Usar OpenAI quando disponível",
        "ai_caption": "A IA recebe apenas metadados e amostras limitadas.",
        "upload": "Envie um ou mais arquivos de dados corporativos",
        "pg_warning": "Use um usuário PostgreSQL somente leitura para demonstrações.",
        "connection": "String de conexão",
        "schema": "Schema",
        "inspect_pg": "Inspecionar PostgreSQL",
        "detected": "Dados Detectados",
        "tables": "Tabelas",
        "relationships": "Relacionamentos",
        "profile_depth": "Profundidade do perfil",
        "generate": "Gerar modelo dimensional",
        "spinner": "Modelando fatos, dimensões, arquivos dbt e diagrama...",
        "generated": "Modelo Gerado",
        "diagram": "Diagrama",
        "dbt_project": "Projeto dbt",
        "download": "Baixar ZIP do projeto dbt",
    },
}


TEXT["English"].update(
    {
        "use_ai": "Use AI provider",
        "ai_provider": "AI provider",
        "ai_api_key": "API key",
        "ai_model": "Model",
        "load_models": "Load Groq models",
        "models_loaded": "Loaded Groq models.",
        "models_empty": "No models returned. Check the API key or type a model manually.",
        "models_error": "Could not load models",
    }
)
TEXT[list(TEXT)[1]].update(
    {
        "use_ai": "Usar provedor de IA",
        "ai_provider": "Provedor de IA",
        "ai_api_key": "Chave de API",
        "ai_model": "Modelo",
        "load_models": "Carregar modelos da Groq",
        "models_loaded": "Modelos da Groq carregados.",
        "models_empty": "Nenhum modelo retornado. Verifique a chave de API ou digite um modelo manualmente.",
        "models_error": "Nao foi possivel carregar os modelos",
    }
)


st.set_page_config(page_title="DW-AI", page_icon="DW", layout="wide")

with st.sidebar:
    language = st.selectbox("Language / Idioma", list(TEXT), index=0)
    t = TEXT[language]
    st.header(t["input"])
    sample_rows = st.slider(t["sample_rows"], min_value=10, max_value=1000, value=100, step=10)
    use_ai = st.toggle(t["use_ai"], value=True)
    ai_provider = st.selectbox(t["ai_provider"], ["OpenAI", "Groq"], disabled=not use_ai)
    ai_api_key = st.text_input(t["ai_api_key"], type="password", disabled=not use_ai)
    provider_key = ai_provider.lower()
    if provider_key == "groq":
        groq_config = AIProviderConfig(provider="groq", api_key=ai_api_key)
        if st.button(t["load_models"], disabled=not use_ai or not ai_api_key):
            try:
                st.session_state["groq_models"] = list_provider_models(groq_config)
                if st.session_state["groq_models"]:
                    st.success(t["models_loaded"])
                else:
                    st.warning(t["models_empty"])
            except Exception as exc:  # pragma: no cover - Streamlit surface
                st.error(f"{t['models_error']}: {exc}")
        groq_models = st.session_state.get("groq_models", [])
        if groq_models:
            ai_model = st.selectbox(t["ai_model"], groq_models, index=0, disabled=not use_ai)
        else:
            ai_model = st.text_input(t["ai_model"], value=GROQ_DEFAULT_MODEL, disabled=not use_ai)
    else:
        ai_model = st.text_input(t["ai_model"], value=OPENAI_DEFAULT_MODEL, disabled=not use_ai)
    ai_config = AIProviderConfig(provider=provider_key, api_key=ai_api_key, model=ai_model)
    st.caption(t["ai_caption"])

st.title(t["title"])
st.caption(t["caption"])

profile = None
source_registry = None

with tempfile.TemporaryDirectory(prefix="dw_ai_") as tmp:
    workdir = Path(tmp)

    custom_col, demo_col = st.columns(2)
    with custom_col:
        st.subheader(t["custom_data"])
        st.caption(t["upload_help"])
        uploads = st.file_uploader(
            t["upload"],
            type=[suffix.lstrip(".") for suffix in SUPPORTED_FILE_SUFFIXES],
            accept_multiple_files=True,
        )

    custom_files_active = bool(uploads)

    with demo_col:
        st.subheader(t["demo_data"])
        st.caption(t["demo_help"])
        scenario_name = st.selectbox(t["demo_scenario"], list(DEMO_SCENARIOS), disabled=custom_files_active)
        if st.button(t["load_demo"], type="primary", disabled=custom_files_active):
            st.session_state["active_demo_scenario"] = scenario_name
            st.session_state.pop("plan", None)
            st.session_state.pop("artifact", None)
            st.session_state.pop("zip_bytes", None)
        if custom_files_active:
            st.info(t["demo_disabled"])

    if custom_files_active:
        if st.session_state.get("active_demo_scenario"):
            st.session_state.pop("active_demo_scenario", None)
            st.session_state.pop("plan", None)
            st.session_state.pop("artifact", None)
            st.session_state.pop("zip_bytes", None)
        saved_paths: list[Path] = []
        upload_dir = workdir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        for upload in uploads:
            target = upload_dir / upload.name
            target.write_bytes(upload.getbuffer())
            saved_paths.append(target)

        try:
            conn, source_registry = ingest_files(saved_paths)
            profile = profile_duckdb(conn, source_registry, sample_rows=sample_rows)
        except Exception as exc:  # pragma: no cover - Streamlit surface
            st.error(f"Could not ingest files: {exc}")
    elif st.session_state.get("active_demo_scenario"):
        active_scenario = st.session_state["active_demo_scenario"]
        demo_paths = sorted(DEMO_SCENARIOS[active_scenario].glob("*.csv"))
        try:
            conn, source_registry = ingest_files(demo_paths)
            profile = profile_duckdb(conn, source_registry, sample_rows=sample_rows)
            st.success(f"{t['demo_loaded']}: {active_scenario}")
        except Exception as exc:  # pragma: no cover - Streamlit surface
            st.error(f"Could not load demo data: {exc}")

    if not custom_files_active and not st.session_state.get("active_demo_scenario"):
        st.divider()
        st.warning(t["pg_warning"])
        connection_string = st.text_input(
            t["connection"],
            placeholder="dbname=postgres user=postgres host=127.0.0.1 password=...",
            type="password",
        )
        schema = st.text_input(t["schema"], value="public")
        if st.button(t["inspect_pg"], type="primary") and connection_string:
            try:
                conn, source_registry = introspect_postgres(connection_string, schema=schema)
                profile = profile_duckdb(conn, source_registry, sample_rows=sample_rows)
            except Exception as exc:  # pragma: no cover - Streamlit surface
                st.error(f"Could not inspect PostgreSQL: {exc}")

    if profile and source_registry:
        st.subheader(t["detected"])
        metric_cols = st.columns(3)
        metric_cols[0].metric(t["tables"], len(profile.tables))
        metric_cols[1].metric(t["relationships"], len(profile.relationships))
        metric_cols[2].metric(t["profile_depth"], f"{sample_rows} rows")

        for table in profile.tables:
            with st.expander(f"{table.name} ({table.row_count} rows)", expanded=len(profile.tables) <= 3):
                st.dataframe(
                    [
                        {
                            "column": col.name,
                            "type": col.data_type,
                            "null_rate": round(col.null_rate, 4),
                            "distinct": col.distinct_count,
                            "unique_ratio": round(col.unique_ratio, 4),
                            "candidate_key": col.is_candidate_key,
                            "identifier": col.is_identifier,
                            "numeric": col.is_numeric,
                            "temporal": col.is_temporal,
                            "sample_values": ", ".join(map(str, col.sample_values[:3])),
                        }
                        for col in table.columns
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                if table.sample_rows:
                    st.dataframe(table.sample_rows, use_container_width=True)

        if st.button(t["generate"], type="primary"):
            with st.spinner(t["spinner"]):
                fallback = deterministic_model_plan(profile)
                plan = generate_model_plan(profile, fallback=fallback, enabled=use_ai, provider_config=ai_config)
                zip_bytes, artifact = build_artifact_zip(plan, profile, source_registry)
                st.session_state["plan"] = plan
                st.session_state["artifact"] = artifact
                st.session_state["zip_bytes"] = zip_bytes

    if "plan" in st.session_state:
        plan = st.session_state["plan"]
        artifact = st.session_state["artifact"]

        st.subheader(t["generated"])
        st.write(plan.rationale)
        st.json(model_to_dict(plan), expanded=False)

        st.subheader(t["diagram"])
        if "diagram_compact.mmd" in artifact.files:
            st.code(artifact.files["diagram_compact.mmd"], language="mermaid")
            with st.expander("Full ER Mermaid"):
                st.code(artifact.diagram, language="mermaid")
        else:
            st.code(artifact.diagram, language="mermaid")

        st.subheader(t["dbt_project"])
        st.download_button(
            t["download"],
            data=st.session_state["zip_bytes"],
            file_name="dw_ai_dbt_project.zip",
            mime="application/zip",
        )
        st.dataframe(
            [{"path": path, "bytes": len(content.encode("utf-8"))} for path, content in artifact.files.items()],
            hide_index=True,
            use_container_width=True,
        )
