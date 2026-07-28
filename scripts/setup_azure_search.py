#!/usr/bin/env python3
"""Setup Azure AI Search index + optional upload from PostgreSQL.

Usage:
  python scripts/setup_azure_search.py              # create/update index only
  python scripts/setup_azure_search.py --upload       # index + upload from PG
  python scripts/setup_azure_search.py --upload --domain legal
  python scripts/setup_azure_search.py --verify       # check index exists

Requires in .env:
  AZURE_SEARCH_ENDPOINT=https://<name>.search.windows.net
  AZURE_SEARCH_API_KEY=<admin-key>
  AZURE_SEARCH_INDEX_NAME=knowledge-index   # optional, default knowledge-index
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup Azure AI Search knowledge index")
    parser.add_argument(
        "--index-name",
        default=None,
        help="Override AZURE_SEARCH_INDEX_NAME (default: knowledge-index)",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload documents from app.knowledge_documents after creating index",
    )
    parser.add_argument("--domain", default=None, help="Filter PG upload by domain")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify index exists and print field list",
    )
    args = parser.parse_args()

    from core.search.azure_index import (
        create_or_update_knowledge_index,
        describe_index,
        index_exists,
        upload_documents_from_pg,
    )

    if args.verify:
        if not index_exists(args.index_name):
            print("Index not found. Run without --verify to create it.")
            sys.exit(1)
        info = describe_index(args.index_name)
        print(f"Index OK: {info['name']} ({info['field_count']} fields)")
        print("Fields:", ", ".join(info["fields"]))
        return

    name = create_or_update_knowledge_index(args.index_name)
    print(f"Index created/updated: {name}")
    print("Fields: id, doc_id, title, content, domain, source")

    if args.upload:
        ok, total = upload_documents_from_pg(domain=args.domain)
        if total == 0:
            print("No documents in app.knowledge_documents — run: python scripts/seed_vectors.py")
            sys.exit(1)
        print(f"Uploaded {ok}/{total} documents to '{name}'.")
        if ok < total:
            sys.exit(1)


if __name__ == "__main__":
    main()
