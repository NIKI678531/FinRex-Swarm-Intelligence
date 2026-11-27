"""Shared CAMEL model factory for FinRex simulation scripts."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from camel.models import ModelFactory
from camel.types import ModelPlatformType


AZURE_API_VERSION_DEFAULT = "2024-12-01-preview"


@dataclass(frozen=True)
class CamelLLMSettings:
    label: str
    api_key: str
    base_url: str
    model: str
    deployment_name: str
    api_version: str
    is_azure: bool


def is_azure_endpoint(base_url: Optional[str]) -> bool:
    return bool(base_url) and ".openai.azure.com" in base_url


def normalize_azure_endpoint(base_url: str) -> str:
    """Return only the Azure resource endpoint, without OpenAI path suffixes."""
    match = re.match(r"^(https?://[^/]+)", base_url or "")
    return match.group(1) if match else base_url


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_camel_llm_settings(config: Dict[str, Any], use_boost: bool = False) -> CamelLLMSettings:
    boost_enabled = _env_bool("LLM_BOOST_ENABLED", False)
    boost_has_key = bool(os.environ.get("LLM_BOOST_API_KEY"))
    selected_boost = bool(use_boost and boost_enabled and boost_has_key)
    prefix = "LLM_BOOST" if selected_boost else "LLM"
    label = "[加速LLM]" if selected_boost else "[通用LLM]"

    api_key = os.environ.get(f"{prefix}_API_KEY", "")
    base_url = os.environ.get(f"{prefix}_BASE_URL", "")
    model = os.environ.get(f"{prefix}_MODEL_NAME", "")

    if selected_boost:
        base_url = base_url or os.environ.get("LLM_BASE_URL", "")
        model = model or os.environ.get("LLM_MODEL_NAME", "")
    else:
        base_url = base_url or config.get("llm_base_url", "")
        model = model or config.get("llm_model", "gpt-4o-mini")

    if not api_key:
        raise ValueError("缺少 API Key 配置，请在项目根目录 .env 文件中设置 LLM_API_KEY")

    is_azure = is_azure_endpoint(base_url)
    if is_azure:
        deployment = os.environ.get(f"{prefix}_DEPLOYMENT_NAME") or model
        api_version = (
            os.environ.get(f"{prefix}_API_VERSION")
            or os.environ.get("LLM_API_VERSION")
            or AZURE_API_VERSION_DEFAULT
        )
        base_url = normalize_azure_endpoint(base_url)
    else:
        deployment = model
        api_version = os.environ.get(f"{prefix}_API_VERSION") or os.environ.get("LLM_API_VERSION", "")

    return CamelLLMSettings(
        label=label,
        api_key=api_key,
        base_url=base_url,
        model=model,
        deployment_name=deployment,
        api_version=api_version,
        is_azure=is_azure,
    )


def create_camel_model(config: Dict[str, Any], use_boost: bool = False, announce: bool = True):
    """Create a CAMEL model backend with correct Azure/OpenAI routing."""
    settings = resolve_camel_llm_settings(config, use_boost=use_boost)

    if announce:
        base_preview = settings.base_url[:40] if settings.base_url else "默认"
        print(f"{settings.label} model={settings.model}, base_url={base_preview}...")

    if settings.is_azure:
        os.environ["AZURE_OPENAI_API_KEY"] = settings.api_key
        os.environ["AZURE_OPENAI_BASE_URL"] = settings.base_url
        os.environ["AZURE_API_VERSION"] = settings.api_version
        os.environ["AZURE_DEPLOYMENT_NAME"] = settings.deployment_name
        if is_azure_endpoint(os.environ.get("OPENAI_API_BASE_URL")):
            os.environ.pop("OPENAI_API_BASE_URL", None)
        return ModelFactory.create(
            model_platform=ModelPlatformType.AZURE,
            model_type=settings.model,
            api_key=settings.api_key,
            url=settings.base_url,
            api_version=settings.api_version,
            azure_deployment_name=settings.deployment_name,
        )

    os.environ["OPENAI_API_KEY"] = settings.api_key
    if settings.base_url:
        os.environ["OPENAI_API_BASE_URL"] = settings.base_url
    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=settings.model,
        api_key=settings.api_key,
        url=settings.base_url or None,
    )
