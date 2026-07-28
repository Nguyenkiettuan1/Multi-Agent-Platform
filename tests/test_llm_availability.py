"""Tests for LLM model availability remapping."""

from __future__ import annotations

from unittest.mock import patch


def test_pick_azure_when_openrouter_missing():
    from core.llm.availability import pick_available_model_ref

    with patch("core.llm.availability._provider_ready") as mock_ready:
        mock_ready.side_effect = lambda name: name == "azure"
        assert pick_available_model_ref("balanced") == "az-gpt-4.1"
        assert pick_available_model_ref("or-gpt-4o-mini") == "az-gpt-4o-mini"
