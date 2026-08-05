"""Text embeddings — OpenAI / OpenRouter / Azure OpenAI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from config import get_settings
from core.llm.secrets import resolve_env

logger = logging.getLogger(__name__)

EmbeddingProvider = Literal["auto", "openai", "openrouter", "azure"]

# Known OpenAI embedding models → dimensions (for validation / docs)
KNOWN_EMBEDDING_DIMS: dict[str, int] = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}


@dataclass(frozen=True)
class EmbeddingRoute:
    provider: EmbeddingProvider
    model: str
    api_key: str
    base_url: str | None = None
    azure_endpoint: str | None = None
    azure_api_version: str = "2024-02-01"


def embeddings_enabled() -> bool:
    route = resolve_embedding_route()
    return route is not None


def resolve_embedding_route() -> EmbeddingRoute | None:
    """Pick provider + model from EMBEDDING_PROVIDER / keys in .env."""
    settings = get_settings()
    provider = (settings.embedding_provider or "auto").lower()

    openai_key = resolve_env("OPENAI_API_KEY")
    openrouter_key = resolve_env("OPENROUTER_API_KEY")
    azure_key = resolve_env("AZURE_OPENAI_API_KEY")
    azure_endpoint = resolve_env("AZURE_OPENAI_ENDPOINT")

    if provider == "auto":
        if "/" in settings.embedding_model and openrouter_key:
            provider = "openrouter"
        elif openai_key:
            provider = "openai"
        elif azure_key and azure_endpoint:
            provider = "azure"
        elif openrouter_key:
            provider = "openrouter"
        else:
            return None

    if provider == "openai":
        if not openai_key:
            return None
        return EmbeddingRoute(
            provider="openai",
            model=_openai_model_id(settings.embedding_model),
            api_key=openai_key,
            base_url="https://api.openai.com/v1",
        )

    if provider == "openrouter":
        if not openrouter_key:
            return None
        return EmbeddingRoute(
            provider="openrouter",
            model=_openrouter_model_id(settings.embedding_model),
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
        )

    if provider == "azure":
        if not azure_key or not azure_endpoint:
            return None
        deployment = settings.embedding_deployment or _openai_model_id(settings.embedding_model)
        return EmbeddingRoute(
            provider="azure",
            model=deployment,
            api_key=azure_key,
            azure_endpoint=azure_endpoint.rstrip("/"),
            azure_api_version=settings.azure_openai_api_version,
        )

    logger.warning("Unknown EMBEDDING_PROVIDER=%s", provider)
    return None


def _openai_model_id(model: str) -> str:
    """OpenAI API: text-embedding-ada-002 (no openai/ prefix)."""
    if model.startswith("openai/"):
        return model.split("/", 1)[1]
    return model


def _openrouter_model_id(model: str) -> str:
    """OpenRouter: openai/text-embedding-ada-002 (with prefix)."""
    bare = _openai_model_id(model)
    if "/" in model:
        return model
    return f"openai/{bare}"


async def embed_text(text: str) -> list[float] | None:
    """Embed document/chunk text at ingest time."""
    return await _create_embedding(text, purpose="document")


async def embed_query(query: str) -> list[float] | None:
    """Embed user query at search time — called by vector_search()."""
    return await _create_embedding(query, purpose="query")


async def _create_embedding(text: str, *, purpose: str) -> list[float] | None:
    route = resolve_embedding_route()
    if route is None:
        logger.debug("Embedding skipped (%s): no provider configured", purpose)
        return None

    settings = get_settings()

    try:
        from openai import AsyncAzureOpenAI, AsyncOpenAI

        if route.provider == "azure":
            client = AsyncAzureOpenAI(
                api_key=route.api_key,
                api_version=route.azure_api_version,
                azure_endpoint=route.azure_endpoint or "",
            )
        else:
            client = AsyncOpenAI(api_key=route.api_key, base_url=route.base_url)

        resp = await client.embeddings.create(
            model=route.model,
            input=text[:8000],
        )
        vec = resp.data[0].embedding

        expected = KNOWN_EMBEDDING_DIMS.get(_openai_model_id(route.model)) or settings.embedding_dimensions
        if len(vec) != settings.embedding_dimensions:
            logger.warning(
                "Embedding dims mismatch (%s): got %d, EMBEDDING_DIMENSIONS=%d (model %s expects %d). "
                "Re-index documents if you changed model.",
                purpose, len(vec), settings.embedding_dimensions, route.model, expected,
            )

        logger.info(
            "Embedded %s via %s: model=%s dims=%d chars=%d",
            purpose, route.provider, route.model, len(vec), len(text),
        )
        return vec
    except Exception as exc:
        logger.warning("Embedding failed (%s) provider=%s model=%s: %s", purpose, route.provider, route.model, exc)
        return None
