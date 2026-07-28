"""
Cấu hình tập trung — DUY NHẤT nơi đọc biến môi trường.

Quy tắc:
- KHÔNG hardcode password / connection string trong file .py
- Giá trị thật nằm trong .env (local) hoặc Key Vault (cloud)
- .env.example chỉ là mẫu, không chứa secret production
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Thư mục gốc project (multi-agent/)
ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Bắt buộc: phải có trong .env ---
    database_url: str = Field(
        ...,
        description="PostgreSQL app schema — DB agent read-only (agent_reader)",
    )
    platform_database_url: str | None = Field(
        default=None,
        description="PostgreSQL platform schema — bắt buộc cho LangGraph checkpointer",
    )
    migrate_database_url: str | None = Field(
        default=None,
        description="PostgreSQL admin — chỉ bắt buộc khi chạy scripts/db_migrate.py hoặc scripts/seed.py",
    )

    # --- Tùy chọn: có default an toàn (không phải secret) ---
    redis_url: str = "redis://localhost:6379/0"
    mcp_query_timeout_seconds: int = 30
    mcp_max_rows: int = 100
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    app_env: str = "local"

    # LLM providers — bật provider nào thì điền key tương ứng
    # OpenRouter: 1 key → 400+ models (OpenAI, Claude, Google, DeepSeek...)
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # Azure OpenAI (optional)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""

    # API security — để trống = tắt auth (local dev)
    api_key: str = ""

    # Embeddings — chọn provider + model rõ ràng (xem .env.example)
    # openai | openrouter | azure | auto (đoán từ key + tên model)
    embedding_provider: str = "auto"
    embedding_model: str = "text-embedding-3-small"
    embedding_deployment: str = ""  # Azure: tên deployment (nếu khác model)
    embedding_dimensions: int = 1536  # phải khớp DB vector(N) và model
    azure_openai_api_version: str = "2025-01-01-preview"

    # RAG chunking
    chunk_size: int = 800
    chunk_overlap: int = 120

    # Search quality
    search_rerank_enabled: bool = True

    # Eval — LLM-as-judge (cần LLM provider)
    eval_llm_judge_enabled: bool = False

    # Azure AI Search (optional — cloud RAG)
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index_name: str = "knowledge-index"

    # Web search (Tavily) — optional
    tavily_api_key: str = ""
    web_search_max_results: int = 5
    web_search_depth: str = "advanced"  # basic | advanced — advanced lấy nội dung trang đầy đủ hơn

    # Langfuse tracing (optional)
    langfuse_tracing_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Auto-promote rated Q&A into RAG (0 = disabled)
    feedback_auto_promote_min_rating: int = 5


@lru_cache
def get_settings() -> Settings:
    """Singleton — gọi ở mọi nơi cần config."""
    return Settings()
