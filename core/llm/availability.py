"""Pick LLM model refs whose provider is actually configured."""

from __future__ import annotations

from functools import lru_cache

from core.llm.models_config import ModelsConfig, load_models_config
from core.llm.providers import create_provider

# When OpenRouter/OpenAI keys are missing but Azure is set — use these equivalents.
_PROVIDER_ALTERNATES: dict[str, str] = {
    "or-claude-sonnet": "az-gpt-4.1",
    "or-gpt-4o-mini": "az-gpt-4o-mini",
    "or-gemini-flash": "az-gpt-4o-mini",
    "or-deepseek": "az-gpt-4o-mini",
}


@lru_cache
def _provider_ready(provider_name: str) -> bool:
    cfg = load_models_config()
    pcfg = cfg.providers.get(provider_name)
    if not pcfg:
        return False
    return create_provider(pcfg).is_configured()


def _resolve_ref(cfg: ModelsConfig, ref: str) -> str:
    return cfg.profiles.get(ref, ref)


def pick_available_model_ref(ref: str, *, cfg: ModelsConfig | None = None) -> str:
    """Return model ref (or profile alias resolved) with a configured provider."""
    cfg = cfg or load_models_config()
    resolved = _resolve_ref(cfg, ref)
    entry = cfg.models.get(resolved)
    if not entry:
        return ref

    if _provider_ready(entry.provider):
        return ref if ref in cfg.models or ref in cfg.profiles else resolved

    alt = _PROVIDER_ALTERNATES.get(resolved)
    if alt:
        alt_entry = cfg.models.get(alt)
        if alt_entry and _provider_ready(alt_entry.provider):
            return alt

    return ref if ref in cfg.models or ref in cfg.profiles else resolved
