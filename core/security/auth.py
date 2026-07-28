"""API authentication."""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(_api_key_header)) -> str | None:
    """Require X-API-Key when API_KEY is set in environment."""
    settings = get_settings()
    required = getattr(settings, "api_key", "") or ""

    if not required:
        return None  # local dev — auth disabled

    if not api_key or api_key != required:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
