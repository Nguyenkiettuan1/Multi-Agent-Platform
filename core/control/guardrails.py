"""Input/output guardrails — block dangerous requests, redact sensitive data."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GUARDRAILS_PATH = ROOT / "config" / "guardrails.yaml"


@dataclass
class SecurityScan:
    blocked: bool = False
    block_reason: str = ""
    flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    lower = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", lower)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@lru_cache
def _load_config() -> dict:
    if not GUARDRAILS_PATH.exists():
        return {}
    return yaml.safe_load(GUARDRAILS_PATH.read_text(encoding="utf-8")) or {}


def scan_input(message: str) -> SecurityScan:
    cfg = _load_config().get("input", {})
    result = SecurityScan()
    texts = [message, _normalize(message)]

    for item in cfg.get("block_patterns", []):
        if any(re.search(item["pattern"], t) for t in texts):
            result.blocked = True
            result.block_reason = item.get("message", item.get("reason", "blocked"))
            result.flags.append(item.get("reason", "blocked"))
            return result

    for item in cfg.get("warn_patterns", []):
        if any(re.search(item["pattern"], t) for t in texts):
            result.flags.append(item.get("reason", "warning"))
            result.warnings.append(item.get("reason", "warning"))

    return result


def redact_output(text: str) -> tuple[str, list[str]]:
    """Redact PII/sensitive patterns from response. Returns (redacted, redacted_types)."""
    cfg = _load_config().get("output", {})
    redacted = text
    types: list[str] = []

    for item in cfg.get("redact_patterns", []):
        pattern = item["pattern"]
        if re.search(pattern, redacted):
            redacted = re.sub(pattern, item.get("replacement", "[REDACTED]"), redacted)
            types.append(item.get("name", "unknown"))

    return redacted, types
