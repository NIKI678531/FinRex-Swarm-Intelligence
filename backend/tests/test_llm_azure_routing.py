from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for path in (ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _clear_llm_env(monkeypatch):
    keys = [
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL_NAME",
        "LLM_DEPLOYMENT_NAME",
        "LLM_API_VERSION",
        "LLM_BOOST_ENABLED",
        "LLM_BOOST_API_KEY",
        "LLM_BOOST_BASE_URL",
        "LLM_BOOST_MODEL_NAME",
        "LLM_BOOST_DEPLOYMENT_NAME",
        "LLM_BOOST_API_VERSION",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE_URL",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_BASE_URL",
        "AZURE_API_VERSION",
        "AZURE_DEPLOYMENT_NAME",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_llm_client_azure_uses_deployment_and_gpt5_token_param(monkeypatch):
    from app.utils import llm_client

    captured_init = {}
    captured_create = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured_create.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"ok": true}')
                    )
                ]
            )

    class FakeAzureOpenAI:
        def __init__(self, **kwargs):
            captured_init.update(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(llm_client, "AzureOpenAI", FakeAzureOpenAI)

    client = llm_client.LLMClient(
        api_key="test-key",
        base_url="https://unit-test.openai.azure.com/openai/deployments/old",
        model="gpt-5.4",
        deployment_name="finrex-gpt54",
    )

    assert client.chat_json([{"role": "user", "content": "ping"}]) == {"ok": True}
    assert captured_init["azure_endpoint"] == "https://unit-test.openai.azure.com"
    assert captured_create["model"] == "finrex-gpt54"
    assert "max_completion_tokens" in captured_create
    assert "temperature" not in captured_create
    assert "max_tokens" not in captured_create


def test_profile_generator_uses_shared_llm_client(monkeypatch):
    from app.services import oasis_profile_generator

    calls = []

    class FakeLLMClient:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def chat_json(self, **kwargs):
            calls.append(("chat_json", kwargs))
            return {"bio": "bio", "persona": "persona"}

    monkeypatch.setattr(oasis_profile_generator, "LLMClient", FakeLLMClient)

    generator = oasis_profile_generator.OasisProfileGenerator(
        api_key="test-key",
        base_url="https://unit-test.openai.azure.com",
        model_name="gpt-5.4",
        zep_api_key="",
    )
    result = generator._generate_profile_with_llm("Alice", "Person", "summary", {}, "")

    assert result["bio"] == "bio"
    assert result["persona"] == "persona"
    assert calls[0] == (
        "init",
        {
            "api_key": "test-key",
            "base_url": "https://unit-test.openai.azure.com",
            "model": "gpt-5.4",
        },
    )
    assert calls[1][0] == "chat_json"


def test_simulation_config_generator_uses_shared_llm_client(monkeypatch):
    from app.services import simulation_config_generator

    calls = []

    class FakeLLMClient:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def chat_json(self, **kwargs):
            calls.append(("chat_json", kwargs))
            return {"agent_configs": []}

    monkeypatch.setattr(simulation_config_generator, "LLMClient", FakeLLMClient)

    generator = simulation_config_generator.SimulationConfigGenerator(
        api_key="test-key",
        base_url="https://unit-test.openai.azure.com",
        model_name="gpt-5.4",
    )
    result = generator._call_llm_with_retry("prompt", "system")

    assert result == {"agent_configs": []}
    assert calls[0][0] == "init"
    assert calls[0][1]["model"] == "gpt-5.4"
    assert calls[1][0] == "chat_json"


def test_camel_factory_routes_azure_and_openai(monkeypatch):
    from camel.models.azure_openai_model import AzureOpenAIModel
    from camel.models.openai_model import OpenAIModel
    from llm_model_factory import create_camel_model

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://unit-test.openai.azure.com/openai")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-5.4")
    monkeypatch.setenv("LLM_DEPLOYMENT_NAME", "finrex-gpt54")
    monkeypatch.setenv("LLM_API_VERSION", "2024-12-01-preview")
    monkeypatch.setenv("OPENAI_API_BASE_URL", "https://unit-test.openai.azure.com")

    azure_model = create_camel_model({}, announce=False)

    assert isinstance(azure_model, AzureOpenAIModel)
    assert str(azure_model._url) == "https://unit-test.openai.azure.com"
    assert azure_model._azure_deployment_name == "finrex-gpt54"
    assert "OPENAI_API_BASE_URL" not in __import__("os").environ

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-4o-mini")

    openai_model = create_camel_model({}, announce=False)

    assert isinstance(openai_model, OpenAIModel)
    assert str(openai_model._url) == "https://api.openai.com/v1"


def test_camel_factory_boost_requires_explicit_enable(monkeypatch):
    from llm_model_factory import resolve_camel_llm_settings

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "main-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://main.openai.azure.com")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-5.4")
    monkeypatch.setenv("LLM_BOOST_API_KEY", "boost-key")
    monkeypatch.setenv("LLM_BOOST_BASE_URL", "https://boost.openai.azure.com")
    monkeypatch.setenv("LLM_BOOST_MODEL_NAME", "gpt-5.4-mini")

    settings = resolve_camel_llm_settings({}, use_boost=True)
    assert settings.label == "[通用LLM]"
    assert settings.model == "gpt-5.4"

    monkeypatch.setenv("LLM_BOOST_ENABLED", "true")
    monkeypatch.setenv("LLM_BOOST_DEPLOYMENT_NAME", "finrex-gpt54-mini")

    boost_settings = resolve_camel_llm_settings({}, use_boost=True)
    assert boost_settings.label == "[加速LLM]"
    assert boost_settings.model == "gpt-5.4-mini"
    assert boost_settings.deployment_name == "finrex-gpt54-mini"

