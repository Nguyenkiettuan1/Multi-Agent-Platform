"""Built-in tools — run in-process, no MCP stdio spawn."""

from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

from core.mcp.models import ToolDescriptor
from workflows.state import AgentId

logger = logging.getLogger(__name__)

InternalHandler = Callable[[dict[str, Any]], Awaitable[str]]

_BUILTIN_SERVERS: dict[str, list[ToolDescriptor]] = {}
_BUILTIN_HANDLERS: dict[str, InternalHandler] = {}


def _register(server_id: str, tool: ToolDescriptor, handler: InternalHandler) -> None:
    _BUILTIN_SERVERS.setdefault(server_id, []).append(tool)
    _BUILTIN_HANDLERS[f"{server_id}/{tool.name}"] = handler


async def _translate_text(args: dict[str, Any]) -> str:
    text = str(args.get("text", "")).strip()
    if not text:
        return json.dumps({"error": "text is required"}, ensure_ascii=False)

    target = str(args.get("target_lang", "vi")).strip() or "vi"
    source = str(args.get("source_lang", "auto")).strip() or "auto"

    from core.llm.client import get_llm_client

    client = get_llm_client()
    if not client.enabled:
        return json.dumps(
            {
                "error": "LLM not configured — set OPENROUTER_API_KEY or AZURE_OPENAI_*",
                "hint": "Add keys in .env and restart the gateway",
            },
            ensure_ascii=False,
        )

    prompt = (
        f"Translate the following text into target language `{target}`"
        + (f" (source: {source})" if source != "auto" else "")
        + ". Return only the translation, no explanation.\n\n"
        + text
    )
    resp = await client.chat(
        "worker",
        [
            {"role": "system", "content": "You are a professional translator."},
            {"role": "user", "content": prompt},
        ],
        agent_id=AgentId.ACTION_WORKER,
    )
    if not resp.content:
        return json.dumps({"error": "Translation failed"}, ensure_ascii=False)
    return json.dumps({"translation": resp.content.strip(), "target_lang": target}, ensure_ascii=False)


async def _ocr_extract(args: dict[str, Any]) -> str:
    """OCR — Tesseract → LLM vision (Azure/OpenAI) → MCP guidance."""
    file_path = str(args.get("file_path", "")).strip()
    image_base64 = str(args.get("image_base64", "")).strip()
    mime_type = str(args.get("mime_type", "image/png")).strip() or "image/png"

    if file_path:
        path = Path(file_path)
        if not path.is_file():
            return json.dumps(
                {"error": f"File not found: {file_path}"},
                ensure_ascii=False,
            )
        try:
            from PIL import Image

            img = Image.open(path)
            text = _try_tesseract(img)
            if text:
                return json.dumps(
                    {"text": text, "source": str(path), "engine": "tesseract"},
                    ensure_ascii=False,
                )
            with open(path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("ascii")
            if path.suffix.lower() in (".jpg", ".jpeg"):
                mime_type = "image/jpeg"
        except ImportError:
            pass
        except Exception as exc:
            return json.dumps({"error": f"Failed to read image: {exc}"}, ensure_ascii=False)

    if image_base64:
        try:
            from PIL import Image

            raw = base64.b64decode(image_base64.split(",")[-1])
            img = Image.open(io.BytesIO(raw))
            text = _try_tesseract(img)
            if text:
                return json.dumps({"text": text, "engine": "tesseract"}, ensure_ascii=False)
        except Exception:
            pass

        from core.mcp.vision_ocr import extract_text_from_image_base64

        logger.info("OCR fallback vision-llm mime=%s", mime_type)
        vision_text = await extract_text_from_image_base64(image_base64, mime_type=mime_type)
        if vision_text:
            return json.dumps(
                {"text": vision_text, "engine": "vision-llm"},
                ensure_ascii=False,
            )

    return json.dumps(
        {
            "error": "Could not read image — check LLM vision (Azure gpt-4o-mini/4.1) or install Tesseract/paddleocr",
            "accepted_args": ["file_path", "image_base64", "mime_type"],
        },
        ensure_ascii=False,
    )


def _try_tesseract(img: Any) -> str:
    try:
        import pytesseract

        return pytesseract.image_to_string(img).strip()
    except Exception:
        return ""


async def _merge_images(args: dict[str, Any]) -> str:
    paths = args.get("image_paths") or []
    if not isinstance(paths, list) or len(paths) < 2:
        return json.dumps(
            {"error": "image_paths requires at least 2 image paths"},
            ensure_ascii=False,
        )

    layout = str(args.get("layout", "horizontal")).lower()
    output_path = str(args.get("output_path", "")).strip()

    try:
        from PIL import Image
    except ImportError:
        return json.dumps(
            {"error": "Missing Pillow — pip install pillow"},
            ensure_ascii=False,
        )

    images: list[Any] = []
    for p in paths:
        path = Path(str(p))
        if not path.is_file():
            return json.dumps({"error": f"Image not found: {p}"}, ensure_ascii=False)
        images.append(Image.open(path).convert("RGB"))

    if layout == "vertical":
        width = max(im.width for im in images)
        height = sum(im.height for im in images)
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        y = 0
        for im in images:
            canvas.paste(im, ((width - im.width) // 2, y))
            y += im.height
    else:
        width = sum(im.width for im in images)
        height = max(im.height for im in images)
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        x = 0
        for im in images:
            canvas.paste(im, (x, (height - im.height) // 2))
            x += im.width

    if not output_path:
        out_dir = Path("data") / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"merged-{len(paths)}.png")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return json.dumps(
        {"output_path": str(out.resolve()), "layout": layout, "count": len(images)},
        ensure_ascii=False,
    )


def _init_builtin_registry() -> None:
    if _BUILTIN_SERVERS:
        return

    _register(
        "builtin-translate",
        ToolDescriptor(
            id="builtin-translate/translate_text",
            server_id="builtin-translate",
            name="translate_text",
            description="Translate text to a target language (vi, en, ja, …).",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source_lang": {"type": "string", "default": "auto"},
                    "target_lang": {"type": "string", "default": "vi"},
                },
                "required": ["text"],
            },
            kind="internal",
        ),
        _translate_text,
    )

    _register(
        "builtin-ocr",
        ToolDescriptor(
            id="builtin-ocr/ocr_extract",
            server_id="builtin-ocr",
            name="ocr_extract",
            description=(
                "Image OCR — Tesseract when available, otherwise LLM vision (Azure GPT-4o). "
                "Use image_base64 from chat uploads."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "image_base64": {"type": "string"},
                    "mime_type": {"type": "string", "default": "image/png"},
                },
            },
            kind="internal",
        ),
        _ocr_extract,
    )

    _register(
        "builtin-image",
        ToolDescriptor(
            id="builtin-image/merge_images",
            server_id="builtin-image",
            name="merge_images",
            description="Merge multiple images horizontally or vertically.",
            input_schema={
                "type": "object",
                "properties": {
                    "image_paths": {"type": "array", "items": {"type": "string"}},
                    "layout": {"type": "string", "enum": ["horizontal", "vertical"]},
                    "output_path": {"type": "string"},
                },
                "required": ["image_paths"],
            },
            kind="internal",
        ),
        _merge_images,
    )

    _register(
        "sql-server",
        ToolDescriptor(
            id="sql-server/list_tables",
            server_id="sql-server",
            name="list_tables",
            description="List PostgreSQL tables (read-only).",
            input_schema={"type": "object", "properties": {}},
            kind="internal",
        ),
        _list_tables,
    )

    _register(
        "sql-server",
        ToolDescriptor(
            id="sql-server/execute_query",
            server_id="sql-server",
            name="execute_query",
            description="Run a read-only SELECT.",
            input_schema={
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
            kind="internal",
        ),
        _execute_query,
    )

    _register(
        "search-server",
        ToolDescriptor(
            id="search-server/search_documents",
            server_id="search-server",
            name="search_documents",
            description="Search knowledge base + web.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                    "include_web": {"type": "boolean", "default": True},
                },
                "required": ["query"],
            },
            kind="internal",
        ),
        _search_documents,
    )


async def _list_tables(_args: dict[str, Any]) -> str:
    from core.mcp.sql_tools import list_tables

    return json.dumps(list_tables(), ensure_ascii=False, default=str)


async def _execute_query(args: dict[str, Any]) -> str:
    from core.mcp.sql_tools import execute_query_json

    return await _sync_json(lambda: execute_query_json(str(args.get("sql", ""))))


async def _search_documents(args: dict[str, Any]) -> str:
    from core.mcp.search_tools import search_documents

    query = str(args.get("query", "")).strip()
    if not query:
        return json.dumps({"error": "query is required"}, ensure_ascii=False)
    result = await search_documents(
        query,
        top_k=int(args.get("top_k", 5)),
        include_web=bool(args.get("include_web", True)),
    )
    return json.dumps(
        {
            "backends": result.backends_used,
            "context": result.context_for_llm[:8000],
            "citation_count": len(result.citations),
        },
        ensure_ascii=False,
    )


async def _sync_json(fn: Callable[[], Any]) -> str:
    try:
        value = fn()
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def list_internal_tools(server_ids: set[str] | None = None) -> list[ToolDescriptor]:
    _init_builtin_registry()
    tools: list[ToolDescriptor] = []
    for sid, server_tools in _BUILTIN_SERVERS.items():
        if server_ids is not None and sid not in server_ids:
            continue
        tools.extend(server_tools)
    return tools


async def invoke_internal(tool_id: str, arguments: dict[str, Any]) -> "ToolCallResult":
    from core.mcp.models import ToolCallResult

    _init_builtin_registry()
    handler = _BUILTIN_HANDLERS.get(tool_id)
    if not handler:
        return ToolCallResult(tool_id=tool_id, success=False, content="", error=f"Unknown internal tool: {tool_id}")
    try:
        content = await handler(arguments)
        return ToolCallResult(tool_id=tool_id, success=True, content=content)
    except Exception as exc:
        return ToolCallResult(tool_id=tool_id, success=False, content="", error=str(exc))
