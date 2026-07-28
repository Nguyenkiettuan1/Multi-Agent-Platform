"""Resolve API keys — từ os.environ hoặc pydantic Settings (.env)."""

from __future__ import annotations

import os

from config import get_settings

# Map env var name → Settings field
_ENV_TO_SETTINGS: dict[str, str] = {
    "OPENROUTER_API_KEY": "openrouter_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "GOOGLE_API_KEY": "google_api_key",
    "AZURE_OPENAI_API_KEY": "azure_openai_api_key",
    "AZURE_OPENAI_ENDPOINT": "azure_openai_endpoint",
    "AZURE_OPENAI_API_VERSION": "azure_openai_api_version",
    "AZURE_OPENAI_DEPLOYMENT": "azure_openai_deployment",
    "TAVILY_API_KEY": "tavily_api_key",
    "LANGFUSE_PUBLIC_KEY": "langfuse_public_key",
    "LANGFUSE_SECRET_KEY": "langfuse_secret_key",
}


def resolve_env(env_key: str) -> str:
    if not env_key:
        return ""
    direct = os.getenv(env_key, "")
    if direct:
        return direct
    field = _ENV_TO_SETTINGS.get(env_key)
    if field:
        return getattr(get_settings(), field, "") or ""
    return ""
