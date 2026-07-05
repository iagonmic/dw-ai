from __future__ import annotations

import json
import os
from dataclasses import dataclass

from pydantic import ValidationError

from dw_ai.models import DatasetProfile, ModelPlan
from dw_ai.utils import model_to_dict

OPENAI_DEFAULT_MODEL = os.getenv("DW_AI_OPENAI_MODEL", "gpt-4.1-mini")
GROQ_DEFAULT_MODEL = os.getenv("DW_AI_GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


@dataclass(frozen=True)
class AIProviderConfig:
    """Runtime-only configuration for the local AI provider selected in the UI."""

    provider: str = "openai"
    api_key: str | None = None
    model: str | None = None

    @property
    def normalized_provider(self) -> str:
        return self.provider.strip().lower()

    @property
    def display_name(self) -> str:
        return "Groq" if self.normalized_provider == "groq" else "OpenAI"

    @property
    def default_model(self) -> str:
        return GROQ_DEFAULT_MODEL if self.normalized_provider == "groq" else OPENAI_DEFAULT_MODEL

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key.strip()
        env_name = "GROQ_API_KEY" if self.normalized_provider == "groq" else "OPENAI_API_KEY"
        return os.getenv(env_name)

    @property
    def resolved_model(self) -> str:
        return (self.model or self.default_model).strip()

    @property
    def base_url(self) -> str | None:
        return GROQ_BASE_URL if self.normalized_provider == "groq" else None


def list_provider_models(config: AIProviderConfig) -> list[str]:
    """Fetch available models from the selected provider when its API supports listing."""
    api_key = config.resolved_api_key
    if not api_key:
        return []

    from openai import OpenAI

    client = _build_client(config, api_key)
    models = client.models.list()
    model_ids = sorted(
        {
            model.id
            for model in getattr(models, "data", [])
            if getattr(model, "id", None)
        }
    )
    return model_ids


def generate_model_plan(
    profile: DatasetProfile,
    fallback: ModelPlan,
    enabled: bool = True,
    provider_config: AIProviderConfig | None = None,
) -> ModelPlan:
    """Ask the selected AI provider for semantic refinement, falling back on any issue."""
    config = provider_config or AIProviderConfig()
    api_key = config.resolved_api_key
    if not enabled or not api_key:
        return fallback

    try:
        client = _build_client(config, api_key)
        response = client.chat.completions.create(
            model=config.resolved_model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior analytics engineer. Generate a Kimball dimensional model plan. "
                        "Return only JSON matching the provided schema keys. Prefer conservative joins and "
                        "state assumptions when confidence is low. Preserve Portuguese business terms when "
                        "the source data is in Portuguese, but use dbt model prefixes like dim_ and fct_."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "dataset_profile": _compact_profile(profile),
                            "fallback_plan": model_to_dict(fallback),
                            "required_keys": list(model_to_dict(fallback).keys()),
                        },
                        default=str,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        ai_plan = ModelPlan.model_validate_json(content)
        if not ai_plan.facts:
            return fallback
        return ai_plan
    except (ValidationError, Exception) as exc:
        fallback.assumptions.append(
            f"{config.display_name} modelling was unavailable or returned invalid JSON; used deterministic plan. Detail: {exc}"
        )
        return fallback


def _build_client(config: AIProviderConfig, api_key: str):
    from openai import OpenAI

    if config.base_url:
        return OpenAI(api_key=api_key, base_url=config.base_url)
    return OpenAI(api_key=api_key)


def _compact_profile(profile: DatasetProfile) -> dict:
    data = model_to_dict(profile)
    for table in data.get("tables", []):
        table["sample_rows"] = table.get("sample_rows", [])[:5]
        for column in table.get("columns", []):
            column["sample_values"] = column.get("sample_values", [])[:3]
    return data
