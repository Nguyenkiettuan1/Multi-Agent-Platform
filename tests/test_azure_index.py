"""Tests for Azure Search index schema."""

from __future__ import annotations

import pytest

from core.search.azure_index import DEFAULT_INDEX_NAME, KNOWLEDGE_INDEX_FIELD_NAMES

def _azure_search_installed() -> bool:
    try:
        import azure.search.documents  # noqa: F401
        return True
    except ImportError:
        return False


_HAS_AZURE_SEARCH = _azure_search_installed()


def test_knowledge_index_field_names():
    assert KNOWLEDGE_INDEX_FIELD_NAMES == (
        "id", "doc_id", "title", "content", "domain", "source",
    )


@pytest.mark.skipif(not _HAS_AZURE_SEARCH, reason="azure-search-documents not installed")
def test_build_knowledge_index_key_field():
    from core.search.azure_index import build_knowledge_index

    index = build_knowledge_index(DEFAULT_INDEX_NAME)
    assert index.name == "knowledge-index"
    assert index.fields[0].name == "id"
    assert index.fields[0].key is True
