"""Tests for media task planning and OCR routing."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.mcp.attachments import materialize_attachments
from core.mcp.ocr_routing import (
    OCR_BUILTIN_TOOL,
    OCR_MCP_TOOL,
    build_ocr_fallback_chain,
    pick_ocr_tool,
    should_escalate_ocr,
)
from core.planning.llm_media_classifier import (
    MediaClassification,
    infer_task_kind_structural,
)
from core.planning.media_tasks import (
    has_image_attachments,
    plan_media_action,
    resolve_attachment_tool_args,
)
from core.control.triage import analyze_triage
from workflows.planner import _plan_from_triage_sync


def test_pick_builtin_by_default():
    available = {OCR_BUILTIN_TOOL, OCR_MCP_TOOL}
    assert pick_ocr_tool("đọc nội dung trong tấm ảnh này", available) == OCR_BUILTIN_TOOL


def test_escalate_on_builtin_error():
    content = '{"error": "Chưa có engine OCR"}'
    assert should_escalate_ocr("đọc ảnh", content, success=False) is True


def test_escalate_when_no_text():
    assert should_escalate_ocr("đọc ảnh", '{"text": "ab"}', success=True) is True


def test_no_escalate_when_good_text():
    content = '{"text": "Hóa đơn số 12345 ngày 01/01/2026 tổng tiền 1.000.000 VND"}'
    assert should_escalate_ocr("xem qua ảnh", content, success=True) is False


def test_structural_infer_ocr_from_image():
    att = [{"mime_type": "image/png", "file_path": "/tmp/x.png"}]
    cls = infer_task_kind_structural("", att)
    assert cls is not None
    assert cls.task_kind == "ocr"
    assert has_image_attachments(att) is True


def test_materialize_and_resolve_args():
    raw = base64.b64encode(b"fake-png").decode()
    mats = materialize_attachments([{"filename": "inv.png", "mime_type": "image/png", "data": raw}])
    args = resolve_attachment_tool_args(mats)
    assert args.get("file_path")
    assert Path(args["file_path"]).is_file()


def test_plan_from_triage_binds_ocr_tool():
    raw = base64.b64encode(b"fake-png").decode()
    attachments = materialize_attachments(
        [{"filename": "inv.png", "mime_type": "image/png", "data": raw}]
    )
    triage = analyze_triage("", attachments=attachments)
    plan = _plan_from_triage_sync("", triage, attachments=attachments)

    assert len(plan.subtasks) == 1
    st = plan.subtasks[0]
    assert st.task_kind == "ocr"
    assert st.tool_id == OCR_BUILTIN_TOOL
    assert st.tool_arguments.get("file_path")


@pytest.mark.asyncio
async def test_llm_classifier_picks_translate_without_keywords():
    with patch(
        "core.planning.llm_media_classifier.get_llm_client",
    ) as mock_client:
        client = mock_client.return_value
        client.enabled = True
        client.chat_json = AsyncMock(
            return_value={
                "task_kind": "translate",
                "target_lang": "en",
                "confidence": 0.9,
            }
        )
        from core.planning.llm_media_classifier import classify_media_task_llm

        result = await classify_media_task_llm(
            "Please render this paragraph in English for my client",
            attachments=None,
        )
        assert result is not None
        assert result.task_kind == "translate"
        assert result.target_lang == "en"


@pytest.mark.asyncio
async def test_plan_media_uses_llm_over_structural():
    with patch(
        "core.planning.llm_media_classifier.classify_media_task_llm",
        new_callable=AsyncMock,
    ) as mock_cls:
        mock_cls.return_value = MediaClassification(
            task_kind="translate",
            target_lang="ja",
            source="llm",
            confidence=0.95,
        )
        from core.planning.media_tasks import plan_media_action_async

        plan = await plan_media_action_async(
            "chuyển sang tiếng Nhật",
            attachments=None,
            available_tool_ids={"builtin-translate/translate_text"},
        )
        assert plan is not None
        assert plan.task_kind == "translate"
        assert plan.tool_arguments.get("target_lang") == "ja"


def test_high_accuracy_adds_paddle_to_chain_when_ready():
    available = {OCR_BUILTIN_TOOL, OCR_MCP_TOOL}
    with patch("core.planning.media_tasks.is_paddleocr_mcp_ready", return_value=True):
        chain = build_ocr_fallback_chain(available_tool_ids=available, high_accuracy=True)
    assert chain[0] == OCR_BUILTIN_TOOL
    assert OCR_MCP_TOOL in chain
