#!/usr/bin/env python3
"""Ingest một tài liệu vào knowledge base — python scripts/ingest_document.py --help"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.search.embeddings import embed_text
from core.search.pgvector_store import upsert_document


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest document into pgvector knowledge base")
    parser.add_argument("--doc-id", required=True, help="Unique document ID")
    parser.add_argument("--title", required=True, help="Document title")
    parser.add_argument("--content", required=True, help="Document content")
    parser.add_argument("--domain", default="general", help="Domain filter (general, legal, ...)")
    parser.add_argument("--source", default="manual", help="Source label")
    parser.add_argument("--no-embed", action="store_true", help="Skip embedding (FTS only)")
    args = parser.parse_args()

    embedding = None
    if not args.no_embed:
        embedding = await embed_text(f"{args.title}\n{args.content}")
        if embedding is None:
            print("Warning: no embedding API key — storing FTS-only")

    upsert_document(
        doc_id=args.doc_id,
        title=args.title,
        content=args.content,
        domain=args.domain,
        source=args.source,
        embedding=embedding,
    )
    print(f"Ingested: {args.doc_id}" + (" (with embedding)" if embedding else " (FTS only)"))


if __name__ == "__main__":
    asyncio.run(main())
