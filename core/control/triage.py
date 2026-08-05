"""Triage — phân tích intent, complexity, routing path.

Ref: LangGraph router, OpenAI Agents SDK handoff, Anthropic triage pattern.

Chiến lược:
  1. Rule-based cho fast path chắc chắn (blocked, greeting, capability, DB rõ ràng)
  2. LLM triage khi có lịch sử chat hoặc intent mơ hồ (xem llm_triage.py)
  3. Rule-based fallback khi LLM tắt/lỗi
"""

from __future__ import annotations

import re
import unicodedata

from core.control.guardrails import scan_input
from workflows.state import IntentType, TriageResult


def _normalize(msg: str) -> str:
    """Chuẩn hóa tiếng Việt — hỗ trợ input không dấu."""
    lower = msg.lower().strip()
    nfkd = unicodedata.normalize("NFKD", lower)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def build_triage_result(
    intent: IntentType,
    *,
    complexity: float = 0.1,
    requires_planning: bool | None = None,
    security_flags: list[str] | None = None,
) -> TriageResult:
    """Map intent → routing flags (dùng chung rule + LLM triage)."""
    flags = security_flags or []

    if intent == IntentType.BLOCKED:
        return TriageResult(
            intent=intent,
            complexity=0.0,
            blocked=True,
            security_flags=flags,
        )

    if intent == IntentType.GREETING:
        return TriageResult(
            intent=intent,
            complexity=0.0,
            skip_review=True,
            skip_synthesize=True,
            fast_path=True,
            security_flags=flags,
        )

    if intent == IntentType.DB_ONLY:
        return TriageResult(
            intent=intent,
            complexity=min(complexity, 0.2),
            skip_review=True,
            skip_synthesize=True,
            fast_path=True,
            security_flags=flags,
        )

    if intent == IntentType.LEGAL:
        return TriageResult(
            intent=intent,
            complexity=max(complexity, 0.35),
            skip_review=True,
            skip_synthesize=False,
            fast_path=False,
            security_flags=flags,
        )

    if intent == IntentType.RESEARCH:
        return TriageResult(
            intent=intent,
            complexity=max(complexity, 0.3),
            skip_review=True,
            skip_synthesize=False,
            fast_path=False,
            security_flags=flags,
        )

    if intent == IntentType.ACTION:
        return TriageResult(
            intent=intent,
            complexity=max(complexity, 0.4),
            skip_review=False,
            skip_synthesize=True,
            fast_path=True,
            security_flags=flags,
        )

    if intent == IntentType.MULTI:
        c = max(complexity, 0.5)
        return TriageResult(
            intent=intent,
            complexity=c,
            requires_planning=requires_planning if requires_planning is not None else True,
            skip_review=c < 0.7,
            skip_synthesize=False,
            fast_path=False,
            security_flags=flags,
        )

    # GENERAL
    return TriageResult(
        intent=IntentType.GENERAL,
        complexity=min(complexity, 0.15),
        skip_review=True,
        skip_synthesize=True,
        fast_path=True,
        security_flags=flags,
    )


def _try_fast_path_rules(msg: str, security_flags: list[str]) -> TriageResult | None:
    """Chỉ các case rule chắc chắn — không cần LLM."""
    if _is_capability_question(msg):
        return build_triage_result(IntentType.GENERAL, security_flags=security_flags)

    if _is_greeting(msg):
        return build_triage_result(IntentType.GREETING, security_flags=security_flags)

    needs_db = _needs_db(msg)
    needs_legal = _needs_legal(msg)
    needs_research = _needs_research(msg)
    needs_action = _needs_action(msg)
    capability_count = sum([needs_db, needs_legal, needs_research, needs_action])

    if needs_db and capability_count == 1:
        return build_triage_result(IntentType.DB_ONLY, security_flags=security_flags)

    return None


def analyze_triage_rules(user_message: str) -> TriageResult:
    """Rule-based triage — fallback khi LLM không dùng được."""
    security = scan_input(user_message)
    if security.blocked:
        return TriageResult(
            intent=IntentType.BLOCKED,
            complexity=0.0,
            blocked=True,
            block_reason=security.block_reason,
            security_flags=security.flags,
        )

    msg = _normalize(user_message)

    fast = _try_fast_path_rules(msg, security.flags)
    if fast:
        return fast

    needs_db = _needs_db(msg)
    needs_legal = _needs_legal(msg)
    needs_research = _needs_research(msg)
    needs_action = _needs_action(msg)
    capability_count = sum([needs_db, needs_legal, needs_research, needs_action])

    if needs_legal and capability_count == 1:
        return build_triage_result(IntentType.LEGAL, security_flags=security.flags)

    if needs_research and capability_count == 1:
        return build_triage_result(IntentType.RESEARCH, security_flags=security.flags)

    if needs_action and capability_count == 1:
        return build_triage_result(IntentType.ACTION, security_flags=security.flags)

    if capability_count >= 2:
        complexity = min(0.5 + capability_count * 0.15, 1.0)
        return build_triage_result(
            IntentType.MULTI,
            complexity=complexity,
            requires_planning=True,
            security_flags=security.flags,
        )

    return build_triage_result(IntentType.GENERAL, security_flags=security.flags)


def should_use_llm_triage(
    user_message: str,
    chat_history: list[dict] | None,
    rule_result: TriageResult,
) -> bool:
    """Khi nào gọi LLM thay vì tin rule thuần."""
    if chat_history:
        return True

    if rule_result.intent == IntentType.GENERAL:
        return True

    caps = detect_capabilities(user_message)
    if sum(caps.values()) >= 2:
        return True

    return False


async def analyze_triage_async(
    user_message: str,
    chat_history: list[dict] | None = None,
    *,
    attachments: list[dict] | None = None,
) -> TriageResult:
    """Triage chính — rule fast path → LLM (có context) → rule fallback."""
    attachment_result = _triage_from_attachments(attachments)
    if attachment_result:
        security = scan_input(user_message)
        attachment_result.security_flags = security.flags
        if security.blocked:
            return TriageResult(
                intent=IntentType.BLOCKED,
                complexity=0.0,
                blocked=True,
                block_reason=security.block_reason,
                security_flags=security.flags,
            )
        return attachment_result

    security = scan_input(user_message)
    if security.blocked:
        return TriageResult(
            intent=IntentType.BLOCKED,
            complexity=0.0,
            blocked=True,
            block_reason=security.block_reason,
            security_flags=security.flags,
        )

    msg = _normalize(user_message)
    fast = _try_fast_path_rules(msg, security.flags)
    if fast:
        return fast

    rule_result = analyze_triage_rules(user_message)

    if should_use_llm_triage(user_message, chat_history, rule_result):
        from core.control.llm_triage import triage_with_llm

        llm_result = await triage_with_llm(user_message, chat_history=chat_history)
        if llm_result:
            llm_result.security_flags = security.flags
            return llm_result

    return rule_result


def analyze_triage(
    user_message: str,
    chat_history: list[dict] | None = None,
    *,
    attachments: list[dict] | None = None,
) -> TriageResult:
    """Sync API — rule-only (tests, planner không có history)."""
    _ = chat_history
    attachment_result = _triage_from_attachments(attachments)
    if attachment_result:
        return attachment_result
    return analyze_triage_rules(user_message)


def _is_greeting(msg: str) -> bool:
    return bool(re.match(r"^(xin chao|chao|hello|hi|hey)\b", msg))


def _is_capability_question(msg: str) -> bool:
    """Meta-questions about agent abilities — not a research/search task."""
    patterns = [
        r"\b(ban|may|anh|chi|em)\s+co\s+the\b",
        r"\bco\s+the\b.+\b(khong|khong\?|ko)\b",
        r"\bcan you\b",
        r"\bdo you\b",
        r"\bare you able\b",
        r"\bco\s+(search|tim kiem|tra cuu)\b.+\b(khong|ko)\b",
        r"\b(search|tim kiem)\s+web\b.+\b(khong|ko)\b",
    ]
    return any(re.search(p, msg) for p in patterns)


def detect_capabilities(msg: str) -> dict[str, bool]:
    """Public API — dùng cho planner multi-task (sync heuristic)."""
    lower = _normalize(msg)
    return {
        "db": _needs_db(lower),
        "legal": _needs_legal(lower),
        "research": _needs_research(lower),
        "action": _needs_action(lower),
        "tools": False,
    }


def _needs_db(msg: str) -> bool:
    data_signals = [
        "bao nhieu", "dem", "danh sach", "thong ke", "so lieu", "bao cao",
        "count", "select", "liet ke", "hop dong", "khach hang",
    ]
    system_signals = [
        "database", "db", "sql", "bang", "query", "truy van",
        "records", "du lieu trong he thong", "trong he thong",
    ]
    return any(k in msg for k in data_signals) or any(k in msg for k in system_signals)


def _needs_legal(msg: str) -> bool:
    keywords = [
        "phap luat", "luat", "nghi dinh", "thong tu", "dieu khoan",
        "tranh chap", "thua kien", "soan hop dong", "legal", "compliance",
        "quy dinh phap", "phan tich hop dong",
    ]
    return any(k in msg for k in keywords)


def _needs_research(msg: str) -> bool:
    keywords = [
        "tim kiem", "tra cuu", "search", "tai lieu", "tim hieu",
        "research", "nguon", "reference", "wiki",
    ]
    return any(k in msg for k in keywords)


def _needs_action(msg: str) -> bool:
    keywords = [
        "gui email", "gui thong bao", "tao ticket", "schedule", "notify",
        "call api", "thuc hien", "execute action",
    ]
    return any(k in msg for k in keywords)


def _triage_from_attachments(attachments: list[dict] | None) -> TriageResult | None:
    """Ảnh đính kèm chat → action-worker OCR."""
    from core.planning.media_tasks import has_image_attachments

    if has_image_attachments(attachments):
        return build_triage_result(IntentType.ACTION, complexity=0.35)
    return None
