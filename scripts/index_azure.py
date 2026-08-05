#!/usr/bin/env python3
"""Push knowledge_documents from PostgreSQL to Azure AI Search index.

Usage:
  python scripts/index_azure.py
  python scripts/index_azure.py --domain legal
  python scripts/index_azure.py --setup-index   # create index before upload
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload PG knowledge docs to Azure Search")
    parser.add_argument("--domain", default=None, help="Filter by domain")
    parser.add_argument(
        "--setup-index",
        action="store_true",
        help="Create/update index before upload (same as setup_azure_search.py)",
    )
    args = parser.parse_args()

    from core.search.azure_index import (
        create_or_update_knowledge_index,
        upload_documents_from_pg,
    )
    from core.search.azure_search import azure_search_enabled

    if not azure_search_enabled():
        print("Error: set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY in .env")
        sys.exit(1)

    if args.setup_index:
        name = create_or_update_knowledge_index()
        print(f"Index ready: {name}")

    ok, total = upload_documents_from_pg(domain=args.domain)
    if total == 0:
        print("No documents found in knowledge_documents.")
        sys.exit(1)

    from config import get_settings

    index_name = get_settings().azure_search_index_name or "knowledge-index"
    print(f"Uploaded {ok}/{total} documents to Azure index '{index_name}'.")
    if ok < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
