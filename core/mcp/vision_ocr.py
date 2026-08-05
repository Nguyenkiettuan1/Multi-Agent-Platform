"""OCR via LLM vision — fallback when Tesseract/PaddleOCR is not installed."""

from __future__ import annotations

import logging
from typing import Any

from core.llm.models_config import ModelEntry, load_models_config
from core.llm.providers import resolve_azure_api_version, resolve_azure_deployment
from core.llm.router import get_router
from core.llm.secrets import resolve_env
from workflows.state import AgentId

logger = logging.getLogger(__name__)

_VISION_MODEL_REFS = (
    "az-gpt-4.1",
    "az-gpt-4o-mini",
    "or-gpt-4o-mini",
    "oai-gpt-4o",
    "or-gemini-flash",
)

_OCR_PROMPT = (
    "Extract ALL text from the image (invoices, scanned documents). "
    "Preserve structure: headings, tables (columns separated by |), amounts, dates. "
    "Return only the readable content — no explanations, no software install instructions."
)


async def extract_text_from_image_base64(
    image_base64: str,
    *,
    mime_type: str = "image/png",
) -> str:
    """Call a vision model (Azure preferred) — used when Tesseract is unavailable."""
    raw = image_base64.split(",")[-1].strip()
    if not raw:
        return ""

    data_url = f"data:{mime_type};base64,{raw}"
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _OCR_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]

    router = get_router()
    cfg = load_models_config()
    last_error: Exception | None = None

    for ref in _VISION_MODEL_REFS:
        try:
            resolved = router.resolve("worker", agent_id=AgentId.ACTION_WORKER, model_override=ref)
        except Exception as exc:
            last_error = exc
            continue
        if not resolved.provider_configured:
            continue
        try:
            text = await _complete_vision(resolved.model, messages, cfg.providers[resolved.model.provider])
            if text.strip():
                logger.info("vision OCR ok model=%s len=%d", ref, len(text))
                return text.strip()
        except Exception as exc:
            last_error = exc
            logger.warning("vision OCR failed model=%s: %s", ref, exc)

    if last_error:
        logger.warning("vision OCR exhausted: %s", last_error)
    return ""


async def _complete_vision(model: ModelEntry, messages: list[dict[str, Any]], provider_cfg) -> str:
    if provider_cfg.type == "azure_openai":
        from openai import AsyncAzureOpenAI

        client = AsyncAzureOpenAI(
            api_key=resolve_env(provider_cfg.api_key_env),
            api_version=resolve_azure_api_version(model, provider_cfg),
            azure_endpoint=resolve_env(provider_cfg.endpoint_env).rstrip("/"),
        )
        deployment = resolve_azure_deployment(model)
        resp = await client.chat.completions.create(
            model=deployment,
            messages=messages,
            max_tokens=min(model.max_tokens, 4096),
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=resolve_env(provider_cfg.api_key_env),
        base_url=provider_cfg.base_url,
        default_headers=provider_cfg.extra_headers or None,
    )
    resp = await client.chat.completions.create(
        model=model.model_id,
        messages=messages,
        max_tokens=min(model.max_tokens, 4096),
        temperature=0.1,
    )
    return resp.choices[0].message.content or ""
