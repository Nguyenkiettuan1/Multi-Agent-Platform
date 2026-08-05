"""Tests for action worker prompt / planning."""

from workflows.workers.action_worker import _TOOL_SELECT_SYSTEM
from core.mcp.ocr_routing import ocr_routing_hint_for_llm


def test_tool_select_system_format_does_not_raise():
    text = _TOOL_SELECT_SYSTEM.format(ocr_hint=ocr_routing_hint_for_llm())
    assert "calls" in text
    assert "{ocr_hint}" not in text
