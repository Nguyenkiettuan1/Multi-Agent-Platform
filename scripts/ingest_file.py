#!/usr/bin/env python3
"""Ingest file với chunking — python scripts/ingest_file.py path/to/doc.pdf"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.search.ingestion import ingest_file_bytes, preview_document
from core.search.parsers import parse_file


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDF/DOCX/TXT with chunking")
    parser.add_argument("file", type=Path, help="Path to document")
    parser.add_argument("--doc-id", default=None)
    parser.add_argument("--domain", default="general")
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--chunk-overlap", type=int, default=None)
    parser.add_argument("--preview", action="store_true", help="Preview chunks only, no DB write")
    parser.add_argument("--eval-query", default=None, help="Test query against chunks (preview mode)")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        sys.exit(1)

    data = args.file.read_bytes()
    parsed = parse_file(data, args.file.name)

    if args.preview or args.eval_query:
        preview = preview_document(
            parsed.content,
            title=parsed.title,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
        print(json.dumps(preview["analysis"], indent=2, ensure_ascii=False))
        for c in preview["chunks"]:
            print(f"\n--- Chunk {c['index']} ({c['char_count']} chars) ---")
            print(c["preview"])

        if args.eval_query:
            from core.search.chunking import chunk_text
            from core.search.ingestion import evaluate_chunks_for_query

            chunks = chunk_text(
                parsed.content,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
            rankings = await evaluate_chunks_for_query(chunks, args.eval_query)
            print(f"\n=== Query eval: {args.eval_query!r} ===")
            for r in rankings[:5]:
                print(f"  chunk {r['index']}: score={r.get('score')} — {r.get('preview', '')[:80]}")
        return

    result = await ingest_file_bytes(
        data,
        args.file.name,
        doc_id=args.doc_id,
        domain=args.domain,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
