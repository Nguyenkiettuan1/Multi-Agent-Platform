"""Plan-stage media task — bind tool + attachment args (LLM classify, no keywords)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from config.settings import ROOT_DIR

_CONFIG_PATH = ROOT_DIR / "config" / "media_tasks.yaml"


@dataclass(frozen=True)
class ToolRef:
    server: str
    name: str

    @property
    def tool_id(self) -> str:
        return f"{self.server}/{self.name}"


@dataclass
class MediaTaskPlan:
    """Plan result for tasks with attached files/images."""

    task_kind: str
    tool_id: str
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    fallback_tool_ids: list[str] = field(default_factory=list)
    attachment_refs: list[dict[str, Any]] = field(default_factory=list)
    high_accuracy: bool = False
    classify_source: str = ""


@lru_cache
def load_media_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def media_defaults() -> dict[str, Any]:
    return dict(load_media_config().get("defaults") or {})


def tool_ref_from_dict(data: dict[str, Any] | None) -> ToolRef | None:
    if not data:
        return None
    server = str(data.get("server", "")).strip()
    name = str(data.get("name", "")).strip()
    if server and name:
        return ToolRef(server=server, name=name)
    return None


def list_task_kinds() -> dict[str, Any]:
    return dict(load_media_config().get("task_kinds") or {})


def has_image_attachments(attachments: list[dict] | None) -> bool:
    if not attachments:
        return False
    prefix = str(media_defaults().get("image_mime_prefix", "image/"))
    for item in attachments:
        mime = str(item.get("mime_type", "")).lower()
        if not mime.startswith(prefix):
            continue
        if item.get("file_path") or item.get("data"):
            return True
    return False


def format_attachment_summary(attachments: list[dict] | None) -> str:
    if not attachments:
        return "(no attachments)"
    lines: list[str] = []
    for i, item in enumerate(attachments, 1):
        mime = str(item.get("mime_type", "unknown"))
        name = str(item.get("filename", f"file-{i}"))
        has_file = bool(item.get("file_path"))
        lines.append(f"- #{i}: {name} ({mime}) saved={has_file}")
    return "\n".join(lines)


def should_attempt_media_plan(
    message: str,
    attachments: list[dict] | None,
) -> bool:
    """Whether there is enough signal to attempt media classification (image or text)."""
    if has_image_attachments(attachments):
        return True
    if attachments:
        return True
    return bool(message.strip())


def resolve_attachment_tool_args(
    attachments: list[dict] | None,
    *,
    message: str = "",
) -> dict[str, str]:
    """Get file_path / image_base64 from materialized attachment."""
    if attachments:
        for item in attachments:
            file_path = str(item.get("file_path", "")).strip()
            mime = str(item.get("mime_type", media_defaults().get("image_mime_prefix", "image/") + "png"))
            if not mime.startswith("image/"):
                mime = "image/png"
            data = str(item.get("data", "")).strip()
            if file_path:
                return {"file_path": file_path, "mime_type": mime}
            if mime.startswith("image/") and data:
                return {"image_base64": data, "mime_type": mime}

    match = re.search(
        r"([\w./\\:-]+\.(?:png|jpe?g|webp|tiff?|bmp|gif))",
        message,
        re.IGNORECASE,
    )
    if match:
        return {"file_path": match.group(1)}
    return {}


def is_paddleocr_mcp_ready() -> bool:
    import importlib.util

    return bool(
        importlib.util.find_spec("paddleocr_mcp")
        and importlib.util.find_spec("paddle")
    )


def is_ocr_tool_id(tool_id_value: str) -> bool:
    tid = tool_id_value.lower()
    if tid.endswith("/ocr_extract") or tid.endswith("/ocr"):
        return True
    ocr_cfg = list_task_kinds().get("ocr") or {}
    primary = tool_ref_from_dict((ocr_cfg.get("tools") or {}).get("primary"))
    if primary and primary.tool_id == tool_id_value:
        return True
    for fb in (ocr_cfg.get("tools") or {}).get("fallback") or []:
        ref = tool_ref_from_dict(fb)
        if ref and ref.tool_id == tool_id_value:
            return True
    return "ocr" in tid


def build_ocr_fallback_chain(
    *,
    available_tool_ids: set[str],
    high_accuracy: bool = False,
) -> list[str]:
    """builtin first → paddleocr (if high_accuracy + ready) → other MCP OCR."""
    ocr_cfg = list_task_kinds().get("ocr") or {}
    tools_cfg = ocr_cfg.get("tools") or {}
    chain: list[str] = []

    primary = tool_ref_from_dict(tools_cfg.get("primary"))
    if primary and primary.tool_id in available_tool_ids:
        chain.append(primary.tool_id)

    for fb in tools_cfg.get("fallback") or []:
        ref = tool_ref_from_dict(fb)
        if not ref or ref.tool_id in chain:
            continue
        when = str(fb.get("when", "")).strip()
        if when == "high_accuracy" and not high_accuracy:
            continue
        if ref.server == "paddleocr" and not is_paddleocr_mcp_ready():
            continue
        if ref.tool_id in available_tool_ids:
            chain.append(ref.tool_id)

    for ext_id in list_external_ocr_tool_ids():
        if ext_id not in chain and ext_id in available_tool_ids:
            chain.append(ext_id)

    if primary and primary.tool_id not in chain and primary.tool_id in available_tool_ids:
        chain.append(primary.tool_id)
    return chain


def list_external_ocr_tool_ids() -> list[str]:
    from core.mcp.config_loader import list_app_servers

    ids: list[str] = []
    known = set()
    ocr_cfg = list_task_kinds().get("ocr") or {}
    tools_cfg = ocr_cfg.get("tools") or {}
    primary = tool_ref_from_dict(tools_cfg.get("primary"))
    if primary:
        known.add(primary.tool_id)
    for fb in tools_cfg.get("fallback") or []:
        ref = tool_ref_from_dict(fb)
        if ref:
            known.add(ref.tool_id)

    for cfg in list_app_servers():
        if cfg.kind != "mcp":
            continue
        for spec in cfg.tools:
            name = str(spec.get("name", "")).strip()
            if not name:
                continue
            tid = f"{cfg.id}/{name}"
            if tid in known:
                continue
            if "ocr" in tid.lower() or "ocr" in str(spec.get("description", "")).lower():
                ids.append(tid)
    return ids


def _build_plan_from_classification(
    message: str,
    attachments: list[dict] | None,
    classification,
    *,
    available_tool_ids: set[str],
) -> MediaTaskPlan | None:
    kind = classification.task_kind
    cfg = list_task_kinds().get(kind) or {}
    tools_cfg = cfg.get("tools") or {}
    primary = tool_ref_from_dict(tools_cfg.get("primary"))
    if not primary:
        return None

    chosen_id = primary.tool_id
    fallback_ids: list[str] = []
    high_accuracy = bool(getattr(classification, "high_accuracy", False))

    if kind == "ocr":
        chain = build_ocr_fallback_chain(
            available_tool_ids=available_tool_ids or {primary.tool_id},
            high_accuracy=high_accuracy,
        )
        if chain:
            chosen_id = chain[0]
            fallback_ids = chain[1:]
        tool_args = resolve_attachment_tool_args(attachments, message=message)
        return MediaTaskPlan(
            task_kind=kind,
            tool_id=chosen_id,
            tool_arguments=tool_args,
            fallback_tool_ids=fallback_ids,
            attachment_refs=list(attachments or []),
            high_accuracy=high_accuracy,
            classify_source=getattr(classification, "source", ""),
        )

    if kind == "translate":
        target = str(getattr(classification, "target_lang", "vi")).strip() or "vi"
        return MediaTaskPlan(
            task_kind=kind,
            tool_id=chosen_id,
            tool_arguments={"text": message, "target_lang": target},
            attachment_refs=list(attachments or []),
            classify_source=getattr(classification, "source", ""),
        )

    if kind == "merge_images":
        layout = str(getattr(classification, "layout", "horizontal")).strip() or "horizontal"
        paths = [
            str(a.get("file_path", "")).strip()
            for a in (attachments or [])
            if str(a.get("file_path", "")).strip()
        ]
        return MediaTaskPlan(
            task_kind=kind,
            tool_id=chosen_id,
            tool_arguments={"image_paths": paths, "layout": layout},
            attachment_refs=list(attachments or []),
            classify_source=getattr(classification, "source", ""),
        )

    return MediaTaskPlan(
        task_kind=kind,
        tool_id=chosen_id,
        tool_arguments={},
        attachment_refs=list(attachments or []),
        classify_source=getattr(classification, "source", ""),
    )


async def plan_media_action_async(
    message: str,
    attachments: list[dict] | None,
    *,
    available_tool_ids: set[str] | None = None,
    chat_history: list[dict] | None = None,
) -> MediaTaskPlan | None:
    """Plan stage async: LLM classify → structural fallback."""
    from core.planning.llm_media_classifier import (
        classify_media_task_llm,
        infer_task_kind_structural,
    )

    if not should_attempt_media_plan(message, attachments):
        return None

    available = available_tool_ids or set()
    classification = await classify_media_task_llm(message, attachments, chat_history=chat_history)
    if classification is None:
        classification = infer_task_kind_structural(message, attachments)
    if classification is None:
        return None

    return _build_plan_from_classification(
        message,
        attachments,
        classification,
        available_tool_ids=available,
    )


def plan_media_action(
    message: str,
    attachments: list[dict] | None,
    *,
    available_tool_ids: set[str] | None = None,
) -> MediaTaskPlan | None:
    """Sync fallback — structural only (tests, LLM off)."""
    from core.planning.llm_media_classifier import infer_task_kind_structural

    if not should_attempt_media_plan(message, attachments):
        return None

    classification = infer_task_kind_structural(message, attachments)
    if classification is None:
        return None

    return _build_plan_from_classification(
        message,
        attachments,
        classification,
        available_tool_ids=available_tool_ids or set(),
    )


def image_only_default_message() -> str:
    return str(media_defaults().get("image_only_message", "Read the information in the attached image"))


def upload_dir() -> Path:
    sub = str(media_defaults().get("upload_subdir", "data/chat-uploads"))
    path = ROOT_DIR / sub
    path.mkdir(parents=True, exist_ok=True)
    return path
