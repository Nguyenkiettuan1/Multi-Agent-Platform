"""Tests for embedding provider routing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.search.embeddings import (
    EmbeddingRoute,
    _openai_model_id,
    _openrouter_model_id,
    resolve_embedding_route,
)


def test_openai_model_strips_prefix():
    assert _openai_model_id("openai/text-embedding-ada-002") == "text-embedding-ada-002"
    assert _openai_model_id("text-embedding-ada-002") == "text-embedding-ada-002"


def test_openrouter_model_adds_prefix():
    assert _openrouter_model_id("text-embedding-ada-002") == "openai/text-embedding-ada-002"
    assert _openrouter_model_id("openai/text-embedding-ada-002") == "openai/text-embedding-ada-002"


@patch("core.search.embeddings.resolve_env")
@patch("core.search.embeddings.get_settings")
def test_resolve_openai_ada002(mock_settings, mock_env):
    mock_settings.return_value.embedding_provider = "openai"
    mock_settings.return_value.embedding_model = "text-embedding-ada-002"
    mock_settings.return_value.embedding_deployment = ""
    mock_settings.return_value.azure_openai_api_version = "2024-02-01"

    def env_side(key):
        return {"OPENAI_API_KEY": "sk-test"}.get(key, "")

    mock_env.side_effect = env_side

    route = resolve_embedding_route()
    assert route is not None
    assert route.provider == "openai"
    assert route.model == "text-embedding-ada-002"
    assert route.base_url == "https://api.openai.com/v1"


@patch("core.search.embeddings.resolve_env")
@patch("core.search.embeddings.get_settings")
def test_resolve_openrouter_with_prefix(mock_settings, mock_env):
    mock_settings.return_value.embedding_provider = "openrouter"
    mock_settings.return_value.embedding_model = "openai/text-embedding-ada-002"
    mock_settings.return_value.embedding_deployment = ""
    mock_settings.return_value.azure_openai_api_version = "2024-02-01"

    def env_side(key):
        return {"OPENROUTER_API_KEY": "sk-or-test"}.get(key, "")

    mock_env.side_effect = env_side

    route = resolve_embedding_route()
    assert route is not None
    assert route.provider == "openrouter"
    assert route.model == "openai/text-embedding-ada-002"


@patch("core.search.embeddings.resolve_env")
@patch("core.search.embeddings.get_settings")
def test_auto_prefers_openai_when_key_set(mock_settings, mock_env):
    mock_settings.return_value.embedding_provider = "auto"
    mock_settings.return_value.embedding_model = "text-embedding-ada-002"
    mock_settings.return_value.embedding_deployment = ""
    mock_settings.return_value.azure_openai_api_version = "2024-02-01"

    def env_side(key):
        return {
            "OPENAI_API_KEY": "sk-test",
            "OPENROUTER_API_KEY": "sk-or-test",
        }.get(key, "")

    mock_env.side_effect = env_side

    route = resolve_embedding_route()
    assert route is not None
    assert route.provider == "openai"
    assert route.model == "text-embedding-ada-002"
