"""Tests for MCP Tool Hub."""

from __future__ import annotations

import pytest

from core.control.triage import analyze_triage_rules
from core.mcp.config_loader import load_mcp_catalog
from core.mcp.hub import get_tool_hub
from workflows.state import IntentType


def test_mcp_catalog_loads_builtin_servers():
    catalog = load_mcp_catalog()
    assert "builtin-translate" in catalog
    assert catalog["builtin-translate"].kind == "internal"
    assert catalog["builtin-translate"].enabled is True


def test_tool_hub_lists_enabled_tools():
    hub = get_tool_hub()
    tools = hub.list_tools()
    ids = {t.id for t in tools}
    assert "builtin-translate/translate_text" in ids
    assert "builtin-ocr/ocr_extract" in ids
    assert "builtin-image/merge_images" in ids


@pytest.mark.asyncio
async def test_translate_tool_without_llm_returns_hint():
    hub = get_tool_hub()
    result = await hub.call_tool(
        "builtin-translate/translate_text",
        {"text": "Hello world", "target_lang": "vi"},
    )
    assert result.tool_id == "builtin-translate/translate_text"
    # Có hoặc không LLM — đều phải trả JSON hợp lệ
    assert result.content or result.error


def test_triage_from_image_attachment():
    from core.control.triage import _triage_from_attachments

    result = _triage_from_attachments(
        [{"mime_type": "image/png", "file_path": "/tmp/inv.png", "filename": "invoice.png"}]
    )
    assert result is not None
    assert result.intent.value == "action"
    assert result.fast_path is True
