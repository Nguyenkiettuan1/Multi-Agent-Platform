"""Tests for eval runner."""

from __future__ import annotations

import pytest

from eval.runner import load_cases, run_case


def test_load_cases():
    cases = load_cases()
    assert len(cases) >= 5


@pytest.mark.asyncio
async def test_eval_greeting():
    case = next(c for c in load_cases() if c.id == "triage-greeting")
    result = await run_case(case)
    assert result.passed, result.failures


@pytest.mark.asyncio
async def test_eval_blocks_delete():
    case = next(c for c in load_cases() if c.id == "triage-blocks-delete")
    result = await run_case(case)
    assert result.passed, result.failures


@pytest.mark.asyncio
async def test_eval_blocks_delete_vn():
    case = next(c for c in load_cases() if c.id == "triage-blocks-delete-vn")
    result = await run_case(case)
    assert result.passed, result.failures
