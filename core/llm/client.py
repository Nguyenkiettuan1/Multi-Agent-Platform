"""LLM client — multi-provider with fallback chains."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache

from core.llm.context import get_usage_tracker
from core.llm.resolver import resolve_model
from core.llm.router import get_router
from core.observability.tracing import record_llm_generation
from workflows.state import AgentId

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    role: str
    provider: str
    model_ref: str
    model_id: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    used_llm: bool = True
    tags: list[str] | None = None
    resolve_source: str = ""
    fallback_used: bool = False


class LLMClient:
    def __init__(self) -> None:
        self._router = get_router()

    @property
    def enabled(self) -> bool:
        return self._router.any_provider_configured()

    async def chat(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        agent_id: AgentId | None = None,
        model_override: str | None = None,
    ) -> LLMResponse:
        resolution = resolve_model(role, agent_id=agent_id, model_override=model_override)
        models_to_try = [resolution.primary, *resolution.fallbacks]

        if not self._router.any_provider_configured():
            primary = resolution.primary
            resp = LLMResponse(
                content="",
                role=role,
                provider=primary.provider,
                model_ref=primary.ref,
                model_id=primary.model_id,
                used_llm=False,
                tags=primary.tags,
                resolve_source=resolution.source.value,
            )
            get_usage_tracker().record(resp)
            return resp

        last_error: Exception | None = None
        for i, model_entry in enumerate(models_to_try):
            resolved = self._router.resolve(
                role, agent_id=agent_id, model_override=model_entry.ref
            )
            if not resolved.provider_configured:
                continue

            try:
                result = await resolved.provider.complete(
                    resolved.model, messages, json_mode=json_mode
                )
                resp = LLMResponse(
                    content=result.content,
                    role=role,
                    provider=resolved.model.provider,
                    model_ref=resolved.model.ref,
                    model_id=resolved.model.model_id,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    tags=resolved.model.tags,
                    resolve_source=resolved.source.value,
                    fallback_used=i > 0,
                )
                get_usage_tracker().record(resp)
                record_llm_generation(
                    role=role,
                    model=resp.model_id,
                    messages=messages,
                    output=resp.content,
                    prompt_tokens=resp.prompt_tokens,
                    completion_tokens=resp.completion_tokens,
                    metadata={
                        "provider": resp.provider,
                        "model_ref": resp.model_ref,
                        "fallback_used": resp.fallback_used,
                    },
                )
                return resp
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM failed role=%s model=%s: %s — trying fallback",
                    role,
                    model_entry.ref,
                    exc,
                )

        primary = resolution.primary
        resp = LLMResponse(
            content="",
            role=role,
            provider=primary.provider,
            model_ref=primary.ref,
            model_id=primary.model_id,
            used_llm=False,
            tags=primary.tags,
            resolve_source=resolution.source.value,
        )
        get_usage_tracker().record(resp)
        if last_error:
            logger.warning("All models failed for role=%s: %s", role, last_error)
        return resp

    async def chat_json(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        agent_id: AgentId | None = None,
        model_override: str | None = None,
    ) -> dict | None:
        resp = await self.chat(
            role, messages, json_mode=True, agent_id=agent_id, model_override=model_override
        )
        if not resp.content:
            return None
        try:
            return json.loads(resp.content)
        except json.JSONDecodeError:
            return None


@lru_cache
def get_llm_client() -> LLMClient:
    return LLMClient()
