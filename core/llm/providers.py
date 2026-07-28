"""LLM provider adapters — OpenRouter, Azure, OpenAI, Google..."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from config import get_settings
from core.llm.models_config import ModelEntry, ProviderConfig
from core.llm.secrets import resolve_env


@dataclass
class CompletionResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class BaseProvider(ABC):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def complete(
        self,
        model: ModelEntry,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> CompletionResult: ...


class OpenAICompatibleProvider(BaseProvider):
    """OpenRouter, OpenAI, Google Gemini (OpenAI-compat), v.v."""

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def _api_key(self) -> str:
        return resolve_env(self.config.api_key_env)

    async def complete(
        self,
        model: ModelEntry,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> CompletionResult:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self._api_key(),
            base_url=self.config.base_url,
            default_headers=self.config.extra_headers or None,
        )

        kwargs: dict[str, Any] = {
            "model": model.model_id,
            "messages": messages,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message
        usage = resp.usage

        return CompletionResult(
            content=choice.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )


def resolve_azure_api_version(model: ModelEntry, provider: ProviderConfig) -> str:
    """Azure AI Foundry / cognitiveservices — dùng 2025-01-01-preview cho chat deployments."""
    env_ver = resolve_env("AZURE_OPENAI_API_VERSION")
    if env_ver:
        return env_ver
    settings = get_settings()
    if settings.azure_openai_api_version:
        return settings.azure_openai_api_version
    if model.api_version:
        return model.api_version
    return provider.api_version


def resolve_azure_deployment(model: ModelEntry) -> str:
    """Deployment name trên Azure — khớp model_id trong catalog (gpt-4o-mini, gpt-4.1, …)."""
    return model.model_id


class AzureOpenAIProvider(BaseProvider):
    def is_configured(self) -> bool:
        return bool(self._api_key() and self._endpoint())

    def _api_key(self) -> str:
        return resolve_env(self.config.api_key_env)

    def _endpoint(self) -> str:
        endpoint = resolve_env(self.config.endpoint_env).rstrip("/")
        return endpoint

    async def complete(
        self,
        model: ModelEntry,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> CompletionResult:
        from openai import AsyncAzureOpenAI

        api_version = resolve_azure_api_version(model, self.config)
        deployment = resolve_azure_deployment(model)

        client = AsyncAzureOpenAI(
            api_key=self._api_key(),
            api_version=api_version,
            azure_endpoint=self._endpoint(),
        )

        kwargs: dict[str, Any] = {
            "model": deployment,
            "messages": messages,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message
        usage = resp.usage

        return CompletionResult(
            content=choice.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )


def create_provider(config: ProviderConfig) -> BaseProvider:
    if config.type == "azure_openai":
        return AzureOpenAIProvider(config)
    return OpenAICompatibleProvider(config)
