"""OCR routing — đọc config/media_tasks.yaml."""

from __future__ import annotations

import json

from core.planning.media_tasks import (
    build_ocr_fallback_chain,
    is_ocr_tool_id,
    is_paddleocr_mcp_ready,
    list_external_ocr_tool_ids,
    load_media_config,
    media_defaults,
    plan_media_action,
    plan_media_action_async,
    resolve_attachment_tool_args,
    tool_ref_from_dict,
)

OCR_BUILTIN_TOOL = "builtin-ocr/ocr_extract"
OCR_MCP_TOOL = "paddleocr/ocr"


def primary_ocr_tool_id() -> str:
    ocr_cfg = (load_media_config().get("task_kinds") or {}).get("ocr") or {}
    ref = tool_ref_from_dict((ocr_cfg.get("tools") or {}).get("primary"))
    return ref.tool_id if ref else OCR_BUILTIN_TOOL


def fallback_ocr_tool_id() -> str | None:
    ocr_cfg = (load_media_config().get("task_kinds") or {}).get("ocr") or {}
    for fb in (ocr_cfg.get("tools") or {}).get("fallback") or []:
        ref = tool_ref_from_dict(fb)
        if ref:
            return ref.tool_id
    return None


def pick_ocr_tool(
    task: str,
    available_tool_ids: set[str],
    *,
    high_accuracy: bool = False,
) -> str | None:
    chain = build_ocr_fallback_chain(
        available_tool_ids=available_tool_ids,
        high_accuracy=high_accuracy,
    )
    return chain[0] if chain else None


def ocr_result_has_text(content: str, *, success: bool) -> bool:
    min_chars = int(media_defaults().get("min_ocr_text_chars", 10))
    if not success or not content.strip():
        return False
    try:
        data = json.loads(content)
        if data.get("error"):
            return False
        return len(str(data.get("text", "")).strip()) >= min_chars
    except json.JSONDecodeError:
        return len(content.strip()) >= min_chars


def should_escalate_ocr(task: str, builtin_result_content: str, *, success: bool) -> bool:
    return not ocr_result_has_text(builtin_result_content, success=success)


def extract_ocr_arguments(task: str, attachments: list[dict] | None = None) -> dict[str, str]:
    return resolve_attachment_tool_args(attachments, message=task)


def ocr_routing_hint_for_llm() -> str:
    builtin = primary_ocr_tool_id()
    mcp = fallback_ocr_tool_id()
    lines = [
        "OCR — chọn tool:",
        f"- `{builtin}`: mặc định (Tesseract → Azure Vision).",
    ]
    if mcp:
        lines.append(f"- `{mcp}`: fallback chính xác cao khi planner yêu cầu.")
    lines.append("Phân loại task do planner LLM quyết định — không cần đoán keyword.")
    return "\n".join(lines)


__all__ = [
    "OCR_BUILTIN_TOOL",
    "OCR_MCP_TOOL",
    "build_ocr_fallback_chain",
    "extract_ocr_arguments",
    "is_ocr_tool_id",
    "is_paddleocr_mcp_ready",
    "list_external_ocr_tool_ids",
    "ocr_result_has_text",
    "ocr_routing_hint_for_llm",
    "pick_ocr_tool",
    "plan_media_action",
    "plan_media_action_async",
    "primary_ocr_tool_id",
    "should_escalate_ocr",
]
