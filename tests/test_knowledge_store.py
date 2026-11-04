"""Integration tests for the document-level knowledge queries (real dev Postgres, no mocks).

Run with DATABASE_URL pointing at the multi-agent DB (the conftest default may point at another server).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from core.search import pgvector_store as store

EMBEDDING = [0.01] * 1536


@pytest.fixture
def kb():
    """Unique id prefix per test; removes only the documents registered through `make`."""
    prefix = f"pytest-kb-{uuid.uuid4().hex[:8]}"
    created: list[str] = []

    class Helper:
        def __init__(self) -> None:
            self.prefix = prefix
            self.domain = f"pytest-{uuid.uuid4().hex[:8]}"

        def make(self, name: str, titles_and_embeds: list[tuple[str, bool]], *, domain: str | None = None,
                 source: str = "pytest") -> str:
            parent = f"{prefix}-{name}"
            created.append(parent)
            total = len(titles_and_embeds)
            for i, (title, embedded) in enumerate(titles_and_embeds):
                store.upsert_document(
                    doc_id=f"{parent}__chunk_{i:04d}",
                    title=f"{title} (chunk {i + 1}/{total})",
                    content=f"{name} content {i}",
                    source=source,
                    domain=domain or self.domain,
                    embedding=EMBEDDING if embedded else None,
                    parent_doc_id=parent,
                    chunk_index=i,
                )
            return parent

        def register(self, doc_id: str) -> None:
            """Schedule cleanup for rows a test inserts itself; call before inserting."""
            created.append(doc_id)

        def set_updated_at(self, doc_id: str, ts: datetime) -> None:
            self.execute(
                "UPDATE app.knowledge_documents SET updated_at = :ts WHERE parent_doc_id = :p OR doc_id = :p",
                {"ts": ts, "p": doc_id},
            )

        def execute(self, sql: str, params: dict) -> None:
            with store._write_engine().connect() as conn:
                conn.execute(text(sql), params)
                conn.commit()

        def make_single(self, name: str, *, domain: str | None = None) -> str:
            doc_id = f"{prefix}-{name}"
            created.append(doc_id)
            store.upsert_document(
                doc_id=doc_id, title="Promoted answer", content="single body",
                source="feedback_promoted", domain=domain or self.domain,
            )
            return doc_id

    try:
        yield Helper()
    finally:
        for parent in created:
            store.delete_chunks_by_parent(parent)


def _by_id(items: list[dict]) -> dict[str, dict]:
    return {d["doc_id"]: d for d in items}


def test_multi_chunk_document_with_missing_embedding(kb):
    pid = kb.make("a", [("Report", True), ("Report", False), ("Report", True)])

    items = store.list_parent_documents(limit=50, offset=0, domain=kb.domain)

    assert len(items) == 1
    doc = items[0]
    assert doc["doc_id"] == pid
    assert doc["title"] == "Report"
    assert doc["domain"] == kb.domain
    assert doc["source"] == "pytest"
    assert doc["chunk_count"] == 3
    assert doc["embedded_count"] == 2
    assert doc["content_length"] == 3 * len("a content 0")
    assert doc["azure_indexed"] is None
    assert doc["created_at"] <= doc["updated_at"]


def test_single_row_document_without_parent(kb):
    did = kb.make_single("solo")

    items = store.list_parent_documents(limit=50, offset=0, domain=kb.domain)

    assert [d["doc_id"] for d in items] == [did]
    assert items[0]["title"] == "Promoted answer"
    assert items[0]["source"] == "feedback_promoted"
    assert items[0]["chunk_count"] == 1
    assert items[0]["embedded_count"] == 0
    assert items[0]["content_length"] == len("single body")

    detail = store.get_document_with_chunks(did)
    assert detail["content"] == "single body"
    assert [(c["doc_id"], c["chunk_index"]) for c in detail["chunks"]] == [(did, None)]


def test_pagination_counts_documents_not_chunks(kb):
    # 3 chunks + 2 chunks + 1 row: limit=1 must still return one whole document.
    a = kb.make("a", [("A", True)] * 3)
    b = kb.make("b", [("B", True)] * 2)
    c = kb.make_single("c")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for offset_days, pid in enumerate((a, b, c)):
        kb.set_updated_at(pid, base + timedelta(days=offset_days))
    assert store.count_parent_documents(domain=kb.domain) == 3

    page1 = store.list_parent_documents(limit=1, offset=0, domain=kb.domain)
    page2 = store.list_parent_documents(limit=1, offset=1, domain=kb.domain)
    page3 = store.list_parent_documents(limit=1, offset=2, domain=kb.domain)
    beyond = store.list_parent_documents(limit=1, offset=3, domain=kb.domain)

    assert [p[0]["doc_id"] for p in (page1, page2, page3)] == [c, b, a]
    assert page1[0]["chunk_count"] == 1
    assert page2[0]["chunk_count"] == 2
    assert page3[0]["chunk_count"] == 3
    assert beyond == []


def test_limit_and_offset_are_clamped(kb):
    kb.make_single("x")

    assert len(store.list_parent_documents(limit=0, offset=-5, domain=kb.domain)) == 1
    assert len(store.list_parent_documents(limit=10_000, offset=0, domain=kb.domain)) == 1


def test_domain_filter_for_list_and_count(kb):
    other = f"{kb.domain}-other"
    mine = kb.make("mine", [("M", True)])
    kb.make("theirs", [("T", True), ("T", True)], domain=other)

    assert [d["doc_id"] for d in store.list_parent_documents(limit=50, offset=0, domain=kb.domain)] == [mine]
    assert store.count_parent_documents(domain=kb.domain) == 1
    assert store.count_parent_documents(domain=other) == 1
    assert store.count_parent_documents(domain=f"{kb.domain}-none") == 0


def test_vietnamese_title_with_diacritics_and_suffix_stripped(kb):
    title = "Quy định về Bảo hiểm xã hội (bản sửa đổi)"
    pid = kb.make("vn", [(title, True), (title, True)])

    listed = store.list_parent_documents(limit=50, offset=0, domain=kb.domain)[0]
    detail = store.get_document_with_chunks(pid)

    # Only the trailing " (chunk i/n)" goes; the parenthesised part of the real title stays.
    assert listed["title"] == title
    assert detail["title"] == title


def test_title_comes_from_lowest_chunk_index(kb):
    pid = f"{kb.prefix}-order"
    kb.register(pid)
    # Insert chunk 1 before chunk 0 so insertion order differs from chunk order.
    for idx, title in ((1, "Second (chunk 2/2)"), (0, "First (chunk 1/2)")):
        store.upsert_document(
            doc_id=f"{pid}__chunk_{idx:04d}", title=title, content=f"body {idx}", domain=kb.domain,
            parent_doc_id=pid, chunk_index=idx,
        )

    assert store.list_parent_documents(limit=50, offset=0, domain=kb.domain)[0]["title"] == "First"
    assert store.get_document_with_chunks(pid)["title"] == "First"


def test_detail_has_full_ordered_chunks_and_joined_content(kb):
    pid = kb.make("d", [("Doc", True), ("Doc", False)])

    detail = store.get_document_with_chunks(pid)

    assert detail["doc_id"] == pid
    assert detail["chunk_count"] == 2
    assert detail["embedded_count"] == 1
    assert [c["doc_id"] for c in detail["chunks"]] == [f"{pid}__chunk_0000", f"{pid}__chunk_0001"]
    assert [c["chunk_index"] for c in detail["chunks"]] == [0, 1]
    assert [c["has_embedding"] for c in detail["chunks"]] == [True, False]
    assert [c["char_count"] for c in detail["chunks"]] == [len("d content 0"), len("d content 1")]
    assert [c["content"] for c in detail["chunks"]] == ["d content 0", "d content 1"]
    assert detail["content"] == "d content 0\n\nd content 1"


def test_chunk_id_resolves_to_nothing_but_parent_id_resolves(kb):
    pid = kb.make("p", [("P", True)])

    assert store.get_document_with_chunks(f"{pid}__chunk_0000") is None
    assert store.get_document_with_chunks(pid) is not None


def test_missing_document(kb):
    missing = f"{kb.prefix}-does-not-exist"

    assert store.get_document_with_chunks(missing) is None
    assert store.list_document_row_ids(missing) == []
    assert store.set_azure_indexed(missing, True) == 0


def test_list_document_row_ids(kb):
    pid = kb.make("ids", [("I", True), ("I", False)])
    solo = kb.make_single("solo-ids")

    assert store.list_document_row_ids(pid) == [f"{pid}__chunk_0000", f"{pid}__chunk_0001"]
    assert store.list_document_row_ids(solo) == [solo]


def test_set_azure_indexed_true_then_false(kb):
    pid = kb.make("az", [("Az", True), ("Az", True)])
    other = kb.make("az-other", [("Other", True)])

    assert store.set_azure_indexed(pid, True) == 2
    listed = _by_id(store.list_parent_documents(limit=50, offset=0, domain=kb.domain))
    assert listed[pid]["azure_indexed"] is True
    assert listed[other]["azure_indexed"] is None
    assert store.get_document_with_chunks(pid)["azure_indexed"] is True

    assert store.set_azure_indexed(pid, False) == 2
    listed = _by_id(store.list_parent_documents(limit=50, offset=0, domain=kb.domain))
    assert listed[pid]["azure_indexed"] is False
    assert listed[other]["azure_indexed"] is None
    assert store.get_document_with_chunks(pid)["azure_indexed"] is False


def test_set_azure_indexed_keeps_existing_metadata_and_handles_parent_row(kb):
    did = f"{kb.prefix}-meta"
    kb.register(did)
    store.upsert_document(doc_id=did, title="Meta", content="body", domain=kb.domain, metadata={"k": "v"})

    assert store.set_azure_indexed(did, True) == 1
    with store._read_engine().connect() as conn:
        meta = conn.execute(
            text("SELECT metadata FROM app.knowledge_documents WHERE doc_id = :d"), {"d": did}
        ).scalar()
    assert meta == {"k": "v", "azure_indexed": True}


def test_set_azure_indexed_with_chunk_id_updates_nothing(kb):
    pid = kb.make("chunkid", [("C", True), ("C", True)])

    assert store.set_azure_indexed(f"{pid}__chunk_0000", True) == 0
    assert store.get_document_with_chunks(pid)["azure_indexed"] is None


def test_azure_indexed_mixed_chunks_is_false(kb):
    pid = kb.make("mixed", [("M", True), ("M", True), ("M", True)])
    store.set_azure_indexed(pid, True)
    kb.execute(
        "UPDATE app.knowledge_documents SET metadata = metadata - 'azure_indexed' WHERE doc_id = :d",
        {"d": f"{pid}__chunk_0002"},
    )

    listed = _by_id(store.list_parent_documents(limit=50, offset=0, domain=kb.domain))
    assert listed[pid]["azure_indexed"] is False
    assert store.get_document_with_chunks(pid)["azure_indexed"] is False


def test_non_boolean_azure_flag_does_not_crash_and_counts_as_not_indexed(kb):
    pid = kb.make("garbage", [("G", True), ("G", True)])
    store.set_azure_indexed(pid, True)
    kb.execute(
        "UPDATE app.knowledge_documents "
        "SET metadata = jsonb_set(metadata, '{azure_indexed}', '\"maybe\"') WHERE doc_id = :d",
        {"d": f"{pid}__chunk_0001"},
    )

    listed = _by_id(store.list_parent_documents(limit=50, offset=0, domain=kb.domain))
    assert listed[pid]["azure_indexed"] is False
    assert store.get_document_with_chunks(pid)["azure_indexed"] is False


def _row_ids(parent: str) -> list[str]:
    """Row ids of `parent`'s chunks only; `del` must not match a sibling named `del2`."""
    pattern = (parent + "__chunk").replace("_", "!_") + "%"
    with store._read_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT doc_id FROM app.knowledge_documents WHERE doc_id LIKE :p ESCAPE '!' ORDER BY doc_id"),
            {"p": pattern},
        ).all()
    return [r[0] for r in rows]


def test_delete_rows_by_ids_deletes_exactly_the_given_ids(kb):
    target = kb.make("del", [("D", True), ("D", True), ("D", True)])
    sibling = kb.make("del2", [("S", True), ("S", True)])
    ids = store.list_document_row_ids(target)

    assert store.delete_rows_by_ids(ids[:2]) == 2

    assert _row_ids(target) == [ids[2]]
    assert _row_ids(sibling) == [f"{sibling}__chunk_0000", f"{sibling}__chunk_0001"]


def test_delete_rows_by_ids_leaves_foreign_chunk_of_same_parent_pattern(kb):
    # A standalone row whose id equals another document's chunk id: only the exact ids go.
    pid = kb.make("own", [("O", True)])
    foreign = f"{pid}__chunk_0000-foreign"
    kb.register(foreign)
    store.upsert_document(doc_id=foreign, title="F", content="f", domain=kb.domain, parent_doc_id=pid, chunk_index=5)

    assert store.delete_rows_by_ids([f"{pid}__chunk_0000"]) == 1

    assert _row_ids(pid) == [foreign]


def test_delete_rows_by_ids_empty_and_unknown(kb):
    pid = kb.make("keep", [("K", True)])

    assert store.delete_rows_by_ids([]) == 0
    assert store.delete_rows_by_ids([f"{kb.prefix}-nope", f"{kb.prefix}-nope2"]) == 0
    assert _row_ids(pid) == [f"{pid}__chunk_0000"]
