#!/usr/bin/env python3
"""Run eval suite — python scripts/run_eval.py"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://agent_reader:agent_reader_local@localhost:5432/multiagent",
)


async def main() -> int:
    from eval.runner import run_all_cases

    results = await run_all_cases()
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.id}")
        for f in r.failures:
            print(f"       - {f}")

    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
