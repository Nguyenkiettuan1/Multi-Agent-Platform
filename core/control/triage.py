"""Triage — analyze intent, complexity, routing path.

Ref: LangGraph router, OpenAI Agents SDK handoff, Anthropic triage pattern.

Strategy:
  1. Rule-based for certain fast paths (blocked, greeting, capability, clear DB)
  2. LLM triage when chat history exists or intent is ambiguous (see llm_triage.py)
  3. Rule-based fallback when LLM is off or fails
"""

from __future__ import annotations

import re
import unicodedata

from core.control.guardrails import scan_input
from workflows.state import IntentType, TriageResult


_ASCII_DEM_COUNT = re.compile(
    r"(?<!\w)dem(?=\s+(?:s[oố]\s+)?(?:l[ưu][ơo]ng\s+)?"
    r"(?:h[oợ]p\s+[dđ][oồ]ng|kh[aá]ch\s+h[aà]ng|b[aả]n\s+ghi|records?)(?!\w))"
)


def _normalize(msg: str) -> str:
    """Normalize Vietnamese text — supports input without diacritics."""
    # NFC first so a decomposed "đếm" (NFD input) is seen as one accented word.
    lower = unicodedata.normalize("NFC", msg.lower().strip())
    # "đếm" (count), "đêm" (night) and "đem" (bring) all collapse to "dem" once
    # diacritics go, so the verb must be recognised here while accents still exist.
    lower = re.sub(r"(?<!\w)đếm(?!\w)", "count", lower)
    # Plain-ASCII "dem" (typed without diacritics) is ambiguous, so accept it only
    # before a data noun. Must run before "đ"->"d" so accented "đem/đêm" never matches.
    lower = _ASCII_DEM_COUNT.sub("count", lower)
    # "đ" has no Unicode decomposition, so map it explicitly ("hợp đồng" -> "hop dong").
    lower = lower.replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", lower)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def build_triage_result(
    intent: IntentType,
    *,
    complexity: float = 0.1,
    requires_planning: bool | None = None,
    security_flags: list[str] | None = None,
) -> TriageResult:
    """Map intent → routing flags (shared by rule + LLM triage)."""
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


def _try_fast_path_rules(
    msg: str,
    security_flags: list[str],
    chat_history: list[dict] | None = None,
) -> TriageResult | None:
    """Only rule-certain cases — no LLM needed."""
    if _is_capability_question(msg):
        return build_triage_result(IntentType.GENERAL, security_flags=security_flags)

    if _is_greeting(msg):
        return build_triage_result(IntentType.GREETING, security_flags=security_flags)

    needs_db = _needs_db(msg)
    needs_legal = _needs_legal(msg)
    needs_research = _needs_research(msg)
    needs_action = _needs_action(msg)
    capability_count = sum([needs_db, needs_legal, needs_research, needs_action])

    # With chat history a weak signal ("bao cao", "danh sach") may be a follow-up
    # about something else, so leave it to LLM triage.
    if needs_db and capability_count == 1 and (not chat_history or _has_strong_db_signal(msg)):
        return build_triage_result(IntentType.DB_ONLY, security_flags=security_flags)

    return None


def analyze_triage_rules(user_message: str) -> TriageResult:
    """Rule-based triage — fallback when LLM is unavailable."""
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
    """When to call LLM instead of trusting rules alone."""
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
    """Primary triage — rule fast path → LLM (with context) → rule fallback."""
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
    fast = _try_fast_path_rules(msg, security.flags, chat_history)
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
    """Sync API — rule-only (tests, planner without history)."""
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
    """Public API — used by multi-task planner (sync heuristic)."""
    lower = _normalize(msg)
    return {
        "db": _needs_db(lower),
        "legal": _needs_legal(lower),
        "research": _needs_research(lower),
        "action": _needs_action(lower),
        "tools": False,
    }


# Matched on word boundaries: "db" must not hit "feedback", "dem" must not hit "demo".
# Entity nouns alone ("hop dong", "khach hang") are deliberately absent — a concept
# question like "hop dong la gi?" is not a data question.
# "đếm", and ASCII "dem" before a data noun, are rewritten to "count" by _normalize
# (see there why this cannot be done after diacritics are stripped).
_STRONG_DB_SIGNALS = re.compile(
    r"\b(bao nhieu|count|select|liet ke|sql|database|db|query|truy van|records|trong he thong)\b"
)
# Data-ish but ambiguous ("bao cao" may be a report to write, not to query).
_WEAK_DB_SIGNALS = re.compile(r"\b(danh sach|thong ke|so lieu|bao cao)\b")


def _has_strong_db_signal(msg: str) -> bool:
    return bool(_STRONG_DB_SIGNALS.search(msg))


def _needs_db(msg: str) -> bool:
    return _has_strong_db_signal(msg) or bool(_WEAK_DB_SIGNALS.search(msg))


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
    """Chat image attachment → action-worker OCR."""
    from core.planning.media_tasks import has_image_attachments

    if has_image_attachments(attachments):
        return build_triage_result(IntentType.ACTION, complexity=0.35)
    return None
