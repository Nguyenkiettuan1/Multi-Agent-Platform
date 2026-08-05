"""LLM media task classifier — no hardcoded keywords."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.llm.client import get_llm_client
from core.planning.media_tasks import (
    format_attachment_summary,
    has_image_attachments,
    list_task_kinds,
)
from workflows.state import AgentId

logger = logging.getLogger(__name__)


@dataclass
class MediaClassification:
    task_kind: str
    high_accuracy: bool = False
    target_lang: str = "vi"
    layout: str = "horizontal"
    confidence: float = 0.0
    source: str = "llm"


def _build_classifier_prompt() -> str:
    kinds = list_task_kinds()
    lines = [
        "You are a Media Task Classifier in a multi-agent pipeline.",
        "Classify the user request based on MESSAGE + ATTACHMENTS (metadata).",
        "Do not rely on hardcoded keywords — understand natural context (Vietnamese/English, with/without diacritics).",
        "",
        "Available task kinds:",
    ]
    for kind, cfg in kinds.items():
        desc = str(cfg.get("description", "")).strip().replace("\n", " ")
        lines.append(f"- `{kind}`: {desc}")
    lines.extend(
        [
            "- `none`: none of the above (e.g. general Q&A about an image, no tool needed).",
            "",
            "Rules:",
            "- Image attached + user wants to read/extract text or numbers → usually `ocr`.",
            "- User wants to translate text (with or without image) → `translate`.",
            "- Multiple images + user wants to merge → `merge_images`.",
            "- `high_accuracy`: true when high-precision OCR is needed (scanned invoices, tables, small text, blurry images).",
            "",
            "Return JSON:",
            "{",
            '  "task_kind": "ocr|translate|merge_images|none",',
            '  "high_accuracy": false,',
            '  "target_lang": "vi|en|ja|...",',
            '  "layout": "horizontal|vertical",',
            '  "confidence": 0.0-1.0',
            "}",
        ]
    )
    return "\n".join(lines)


async def classify_media_task_llm(
    message: str,
    attachments: list[dict] | None = None,
    *,
    chat_history: list[dict] | None = None,
) -> MediaClassification | None:
    client = get_llm_client()
    if not client.enabled:
        return None

    kinds = set(list_task_kinds()) | {"none"}
    attach_block = format_attachment_summary(attachments)
    history_block = _format_history(chat_history)

    messages = [
        {"role": "system", "content": _build_classifier_prompt()},
        {
            "role": "user",
            "content": (
                f"{history_block}"
                f"## User message\n{message or '(no text — attachment only)'}\n\n"
                f"## Attachments\n{attach_block}\n\n"
                "Classify task_kind as JSON."
            ),
        },
    ]

    data = await client.chat_json("triage", messages, agent_id=AgentId.ACTION_WORKER)
    if not data:
        return None

    try:
        kind = str(data.get("task_kind", "none")).strip().lower()
        if kind not in kinds:
            kind = "none"
        if kind == "none":
            return None
        confidence = float(data.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))
        return MediaClassification(
            task_kind=kind,
            high_accuracy=bool(data.get("high_accuracy", False)),
            target_lang=str(data.get("target_lang", "vi")).strip() or "vi",
            layout=str(data.get("layout", "horizontal")).strip() or "horizontal",
            confidence=confidence,
            source="llm",
        )
    except (TypeError, ValueError) as exc:
        logger.warning("Media classifier parse error: %s", exc)
        return None


def infer_task_kind_structural(
    message: str,
    attachments: list[dict] | None = None,
) -> MediaClassification | None:
    """Non-LLM fallback — structure only (mime, file count), no keywords."""
    if not attachments:
        return None

    image_count = sum(
        1
        for a in attachments
        if str(a.get("mime_type", "")).lower().startswith("image/")
        and (a.get("file_path") or a.get("data"))
    )
    if image_count >= 2:
        return MediaClassification(task_kind="merge_images", source="structural", confidence=0.5)
    if image_count == 1 or has_image_attachments(attachments):
        return MediaClassification(task_kind="ocr", source="structural", confidence=0.6)
    return None


def _format_history(chat_history: list[dict] | None) -> str:
    if not chat_history:
        return ""
    lines = ["## Recent conversation"]
    for msg in chat_history[-4:]:
        role = msg.get("role", "user")
        content = str(msg.get("content", ""))[:800]
        if content:
            lines.append(f"- {role}: {content}")
    lines.append("")
    return "\n".join(lines) + "\n"
