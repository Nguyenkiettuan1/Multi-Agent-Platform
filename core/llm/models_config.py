"""Load model infrastructure from config/models.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MODELS_PATH = ROOT / "config" / "models.yaml"


@dataclass
class ProviderConfig:
    name: str
    type: str
    base_url: str = ""
    api_key_env: str = ""
    endpoint_env: str = ""
    api_version: str = "2024-10-21"
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ModelEntry:
    ref: str
    provider: str
    model_id: str
    description: str = ""
    max_tokens: int = 4096
    temperature: float = 0.3
    tags: list[str] = field(default_factory=list)
    api_version: str = ""  # Azure: per-deployment API version (overrides provider default)


@dataclass
class ModelsConfig:
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelEntry]
    profiles: dict[str, str]
    fallbacks: dict[str, list[str]]
    default_model: str


@lru_cache
def load_models_config() -> ModelsConfig:
    data = yaml.safe_load(MODELS_PATH.read_text(encoding="utf-8")) or {}

    providers: dict[str, ProviderConfig] = {}
    for name, cfg in data.get("providers", {}).items():
        providers[name] = ProviderConfig(
            name=name,
            type=cfg.get("type", "openai_compatible"),
            base_url=cfg.get("base_url", ""),
            api_key_env=cfg.get("api_key_env", ""),
            endpoint_env=cfg.get("endpoint_env", ""),
            api_version=cfg.get("api_version", "2024-10-21"),
            extra_headers=cfg.get("extra_headers", {}),
        )

    models: dict[str, ModelEntry] = {}
    for ref, cfg in data.get("models", {}).items():
        models[ref] = ModelEntry(
            ref=ref,
            provider=cfg["provider"],
            model_id=cfg["model_id"],
            description=cfg.get("description", ""),
            max_tokens=cfg.get("max_tokens", 4096),
            temperature=cfg.get("temperature", 0.3),
            tags=cfg.get("tags", []),
            api_version=cfg.get("api_version", ""),
        )

    return ModelsConfig(
        providers=providers,
        models=models,
        profiles=data.get("profiles", {}),
        fallbacks=data.get("fallbacks", {}),
        default_model=data.get("default_model", "or-gpt-4o-mini"),
    )


def resolve_model_ref(cfg: ModelsConfig, ref_or_profile: str) -> ModelEntry:
    """Profile alias → model ref → ModelEntry."""
    ref = cfg.profiles.get(ref_or_profile, ref_or_profile)
    if ref not in cfg.models:
        if cfg.default_model in cfg.models:
            return cfg.models[cfg.default_model]
        raise ValueError(f"Unknown model ref: {ref_or_profile}")
    return cfg.models[ref]
