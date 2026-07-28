#!/usr/bin/env python3
"""Export feedback dataset — python scripts/export_feedback.py -o dataset.jsonl"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.intelligence.feedback_store import export_training_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Q&A feedback for training/eval")
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--min-rating", type=int, default=4)
    parser.add_argument("--min-eval-score", type=float, default=0.0)
    parser.add_argument("--format", choices=["jsonl", "openai", "pairs"], default="jsonl")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    body = export_training_dataset(
        min_rating=args.min_rating,
        min_eval_score=args.min_eval_score,
        fmt=args.format,
        limit=args.limit,
    )

    if args.output:
        args.output.write_text(body + ("\n" if body else ""), encoding="utf-8")
        print(f"Exported to {args.output}")
    else:
        print(body)


if __name__ == "__main__":
    main()
