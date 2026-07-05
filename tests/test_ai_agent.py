from __future__ import annotations

from types import SimpleNamespace

from dw_ai.ai_agent import AIProviderConfig, GROQ_BASE_URL, generate_model_plan, list_provider_models
from dw_ai.models import DatasetProfile, FactModel, ModelPlan, TableProfile


def test_provider_config_resolves_groq_defaults_and_base_url() -> None:
    config = AIProviderConfig(provider="groq", api_key="gsk_test")

    assert config.display_name == "Groq"
    assert config.base_url == GROQ_BASE_URL
    assert config.resolved_api_key == "gsk_test"
    assert config.resolved_model


def test_list_provider_models_uses_configured_client(monkeypatch) -> None:
    class FakeModels:
        def list(self):
            return SimpleNamespace(
                data=[
                    SimpleNamespace(id="llama-3.1-8b-instant"),
                    SimpleNamespace(id="llama-3.3-70b-versatile"),
                ]
            )

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr("dw_ai.ai_agent._build_client", lambda config, api_key: fake_client)

    models = list_provider_models(AIProviderConfig(provider="groq", api_key="gsk_test"))

    assert models == ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]


def test_generate_model_plan_passes_selected_provider_and_model(monkeypatch) -> None:
    calls = {}
    ai_plan = ModelPlan(
        facts=[FactModel(name="fct_test", source_table="source", grain="One row per test.")],
        confidence=0.9,
        rationale="AI generated.",
    )

    class FakeCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=ai_plan.model_dump_json()))])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setattr("dw_ai.ai_agent._build_client", lambda config, api_key: fake_client)

    fallback = ModelPlan(
        facts=[FactModel(name="fct_fallback", source_table="source", grain="One row per fallback.")],
        confidence=0.5,
    )
    profile = DatasetProfile(tables=[TableProfile(name="source", row_count=1)])
    result = generate_model_plan(
        profile,
        fallback,
        enabled=True,
        provider_config=AIProviderConfig(provider="groq", api_key="gsk_test", model="llama-test"),
    )

    assert result.rationale == "AI generated."
    assert calls["model"] == "llama-test"
    assert calls["response_format"] == {"type": "json_object"}

