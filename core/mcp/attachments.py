"""Attachment utilities — materialize upload, resolve tool args."""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any

from core.planning.media_tasks import upload_dir


def materialize_attachments(attachments: list[dict] | None) -> list[dict]:
    """Write base64 to disk; keep metadata for LangGraph checkpoint."""
    if not attachments:
        return []

    dest = upload_dir()
    out: list[dict] = []
    for item in attachments:
        data = str(item.get("data", "")).strip()
        mime = str(item.get("mime_type", "image/png"))
        filename = str(item.get("filename", "upload"))
        file_path = str(item.get("file_path", "")).strip()
        att_id = str(item.get("id", "")).strip() or filename

        if not file_path and data:
            suffix = Path(filename).suffix or ".png"
            raw = base64.b64decode(data.split(",")[-1])
            tmp = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                prefix="chat-",
                dir=dest,
            )
            tmp.write(raw)
            tmp.close()
            file_path = tmp.name

        out.append(
            {
                "id": att_id,
                "filename": filename,
                "mime_type": mime,
                "file_path": file_path,
                "data": data,
            }
        )
    return out


def ensure_file_path(arguments: dict[str, Any], *, prefix: str = "chat-ocr-") -> dict[str, Any]:
    """Write base64 to a temp file when external MCP only accepts a path."""
    args = dict(arguments)
    if args.get("file_path") or args.get("image_path"):
        if args.get("file_path") and not args.get("image_path"):
            args["image_path"] = args["file_path"]
        return args

    raw_b64 = str(args.get("image_base64", "")).strip()
    if not raw_b64:
        return args

    mime = str(args.get("mime_type", "image/png")).lower()
    suffix = ".png"
    if "jpeg" in mime or "jpg" in mime:
        suffix = ".jpg"
    elif "webp" in mime:
        suffix = ".webp"

    data = base64.b64decode(raw_b64.split(",")[-1])
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=prefix, dir=upload_dir())
    path = Path(tmp.name)
    tmp.write(data)
    tmp.close()

    args["file_path"] = str(path)
    args["image_path"] = str(path)
    return args
