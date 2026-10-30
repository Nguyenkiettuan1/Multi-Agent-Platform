"""Triage rules — DB fast path must need a data-question signal on word boundaries."""

import pytest

from core.control.triage import analyze_triage, analyze_triage_rules, detect_capabilities
from workflows.state import IntentType

HISTORY = [
    {"role": "user", "content": "Hop dong ABC la gi?"},
    {"role": "assistant", "content": "Hop dong ABC la ..."},
]


@pytest.mark.parametrize(
    "msg",
    [
        "Hợp đồng là gì?",
        "Hop dong la gi?",
        "feedback của tôi",
        "feedback cua toi",
        "demo sản phẩm",
        "demo san pham",
        "bảng giá",
        "bang gia",
        "ca đêm nay ai trực",
        "ca dem nay ai truc",
        "đem hồ sơ đi nộp",
        "dem ho so di nop",
        "đem các hồ sơ đi nộp",
        "đem tất cả hồ sơ ra ngoài",
        "đêm số 3 ai trực",
        "dem cac ho so di nop",
        "dem tat ca ho so ra ngoai",
        "đem hợp đồng đi nộp",
        "đêm hợp đồng",
        "đem khách hàng đi ăn",
        "ca đêm nay ai trục",  # NFD "đêm"
    ],
)
def test_concept_or_substring_hits_are_not_db_only(msg):
    # Rule-only result is deterministic for these: no capability matches at all.
    assert analyze_triage(msg).intent == IntentType.GENERAL
    assert detect_capabilities(msg)["db"] is False


@pytest.mark.parametrize(
    "msg",
    [
        "Có bao nhiêu hợp đồng active?",
        "Co bao nhieu hop dong trong he thong?",
        "Đếm số khách hàng",
        "Đếm số hợp đồng",
        "đếm hợp đồng",
        "dem so khach hang",
        "dem hop dong",
        "dem số khách hàng",
        "đếm doanh thu",  # NFD; noun not in any list, proves the NFC step
        "đếm so khach hang",  # decomposed (NFD) "đếm"
        "ĐẾM hợp đồng",  # NFD, upper case
        "Liệt kê hợp đồng",
        "Thống kê hợp đồng theo tháng",
        "SELECT * FROM contracts",
        "chay sql de lay danh sach khach hang",
    ],
)
def test_clear_data_questions_stay_db_only(msg):
    t = analyze_triage(msg)
    assert t.intent == IntentType.DB_ONLY
    assert t.fast_path is True


def test_db_word_matches_only_as_whole_word():
    assert detect_capabilities("kiem tra db")["db"] is True
    assert detect_capabilities("feedback")["db"] is False


@pytest.mark.asyncio
async def test_ambiguous_signal_with_history_defers_to_llm():
    from unittest.mock import AsyncMock, patch

    from core.control.triage import analyze_triage_async, build_triage_result

    llm = build_triage_result(IntentType.GENERAL)
    with patch("core.control.llm_triage.triage_with_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm
        # "bao cao" is a weak signal: fine alone, ambiguous after a conversation.
        t = await analyze_triage_async("bao cao tuan nay the nao", chat_history=HISTORY)
    assert mock_llm.await_count == 1
    assert t.intent == IntentType.GENERAL


@pytest.mark.asyncio
async def test_strong_signal_with_history_still_fast_paths():
    from unittest.mock import AsyncMock, patch

    from core.control.triage import analyze_triage_async

    with patch("core.control.llm_triage.triage_with_llm", new_callable=AsyncMock) as mock_llm:
        t = await analyze_triage_async("Co bao nhieu hop dong active?", chat_history=HISTORY)
    assert mock_llm.await_count == 0
    assert t.intent == IntentType.DB_ONLY


def test_rules_fallback_on_concept_question_is_general():
    assert analyze_triage_rules("Hợp đồng là gì?").intent == IntentType.GENERAL


@pytest.mark.asyncio
async def test_weak_signal_with_history_falls_back_to_rules_when_llm_returns_none():
    from unittest.mock import AsyncMock, patch

    from core.control.triage import analyze_triage_async

    with patch("core.control.llm_triage.triage_with_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = None
        t = await analyze_triage_async("bao cao tuan nay", chat_history=HISTORY)
    assert mock_llm.await_count == 1
    assert t.intent == IntentType.DB_ONLY  # rule result, same as analyze_triage_rules
    assert t.intent == analyze_triage_rules("bao cao tuan nay").intent
