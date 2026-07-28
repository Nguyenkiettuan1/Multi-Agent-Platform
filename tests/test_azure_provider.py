"""Azure OpenAI provider resolution tests."""

from __future__ import annotations

from unittest.mock import patch

from core.llm.models_config import ModelEntry, ProviderConfig, load_models_config
from core.llm.providers import resolve_azure_api_version, resolve_azure_deployment


def test_resolve_azure_api_version_prefers_env():
    cfg = load_models_config()
    provider = cfg.providers["azure"]
    model = cfg.models["az-gpt-4o-mini"]

    with patch("core.llm.providers.resolve_env", return_value="2025-01-01-preview"):
        assert resolve_azure_api_version(model, provider) == "2025-01-01-preview"


def test_resolve_azure_api_version_model_default():
    cfg = load_models_config()
    provider = cfg.providers["azure"]
    model = cfg.models["az-gpt-4.1"]

    with patch("core.llm.providers.resolve_env", return_value=""):
        with patch("core.llm.providers.get_settings") as mock_settings:
            mock_settings.return_value.azure_openai_api_version = ""
            assert resolve_azure_api_version(model, provider) == "2025-01-01-preview"


def test_resolve_azure_deployment_uses_model_id():
    model = ModelEntry(
        ref="az-gpt-4.1",
        provider="azure",
        model_id="gpt-4.1",
        api_version="2025-01-01-preview",
    )
    assert resolve_azure_deployment(model) == "gpt-4.1"


def test_azure_models_yaml_api_version():
    cfg = load_models_config()
    for ref in ("az-gpt-4o-mini", "az-gpt-4.1"):
        assert cfg.models[ref].api_version == "2025-01-01-preview"
    assert cfg.providers["azure"].api_version == "2025-01-01-preview"
