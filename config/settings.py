"""
Centralized configuration — the ONLY place to read environment variables.

Rules:
- Do NOT hardcode passwords / connection strings in .py files
- Real values live in .env (local) or Key Vault (cloud)
- .env.example is a template only — no production secrets
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (multi-agent/)
ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Required: must be set in .env ---
    database_url: str = Field(
        ...,
        description="PostgreSQL app schema — DB agent read-only (agent_reader)",
    )
    platform_database_url: str | None = Field(
        default=None,
        description="PostgreSQL platform schema — required for LangGraph checkpointer",
    )
    migrate_database_url: str | None = Field(
        default=None,
        description="PostgreSQL admin — only required when running scripts/db_migrate.py or scripts/seed.py",
    )

    # --- Optional: safe defaults (not secrets) ---
    redis_url: str = "redis://localhost:6379/0"
    mcp_query_timeout_seconds: int = 30
    mcp_max_rows: int = 100
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    app_env: str = "local"

    # LLM providers — set keys for providers you enable
    # OpenRouter: one key → 400+ models (OpenAI, Claude, Google, DeepSeek...)
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # Azure OpenAI (optional)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""

    # API security. api_key = optional X-API-Key for scripts/CI (empty = that path is
    # off, NOT "auth disabled": every API route needs a login or a valid key).
    api_key: str = ""
    # Signs the ma_session cookie (HMAC). Empty = login/session calls fail fast;
    # changing it logs everyone out at once.
    auth_secret_key: str = ""
    auth_session_ttl_hours: int = Field(default=12, ge=1, le=168)  # 1h..7 days
    # Keep True outside plain-http local dev; browsers drop Secure cookies on http
    # (except localhost).
    auth_cookie_secure: bool = True

    # Embeddings — choose provider + model explicitly (see .env.example)
    # openai | openrouter | azure | auto (infer from key + model name)
    embedding_provider: str = "auto"
    embedding_model: str = "text-embedding-3-small"
    embedding_deployment: str = ""  # Azure: deployment name (if different from model)
    embedding_dimensions: int = 1536  # must match DB vector(N) and model
    azure_openai_api_version: str = "2025-01-01-preview"

    # RAG chunking
    chunk_size: int = 800
    chunk_overlap: int = 120

    # Search quality
    search_rerank_enabled: bool = True

    # Eval — LLM-as-judge (requires LLM provider)
    eval_llm_judge_enabled: bool = False

    # Azure AI Search (optional — cloud RAG)
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index_name: str = "knowledge-index"

    # Web search (Tavily) — optional
    tavily_api_key: str = ""
    web_search_max_results: int = 5
    web_search_depth: str = "advanced"  # basic | advanced — advanced fetches fuller page content

    # Langfuse tracing (optional)
    langfuse_tracing_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Auto-promote rated Q&A into RAG (0 = disabled)
    feedback_auto_promote_min_rating: int = 5


@lru_cache
def get_settings() -> Settings:
    """Singleton — call from anywhere config is needed."""
    return Settings()
