"""Ingestion + delete service: Postgres is the real dev DB, Azure and the embedder are fakes."""

from __future__ import annotations

import socket
import uuid
from types import SimpleNamespace

import pytest

from core.search import azure_index, ingestion
from core.search.pgvector_store import (
    delete_chunks_by_parent,
    get_document_with_chunks,
    list_document_row_ids,
    upsert_document,
)

VECTOR = [0.01] * 1536
# One paragraph per chunk: each is longer than half of chunk_size, so none can merge.
TEXT = "\n\n".join(c * 90 for c in "ABC")
CHUNK_SIZE = 100


class FakeSearchClient:
    def __init__(self, calls: list, store: set, *, fail_upload=False, fail_delete=False,
                 partial_upload=False, partial_delete=False):
        self.calls = calls
        self.store = store
        self.fail_upload = fail_upload
        self.fail_delete = fail_delete
        self.partial_upload = partial_upload
        self.partial_delete = partial_delete

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.calls.append(("close",))

    @staticmethod
    def _results(n, partial):
        # HTTP 207 shape: the SDK does not raise, the last key comes back rejected.
        return [
            SimpleNamespace(succeeded=not (partial and i == n - 1), status_code=503 if partial and i == n - 1 else 200)
            for i in range(n)
        ]

    def upload_documents(self, documents):
        self.calls.append(("upload", [d["id"] for d in documents]))
        if self.fail_upload:
            raise ConnectionError("boom https://secret.example")
        self.store.update(d["id"] for d in documents)
        return self._results(len(documents), self.partial_upload)

    def delete_documents(self, documents):
        self.calls.append(("delete", [d["id"] for d in documents]))
        if self.fail_delete:
            raise ConnectionError("boom")
        self.store.difference_update(d["id"] for d in documents)
        return self._results(len(documents), self.partial_delete)


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    """Only loopback (dev Postgres) may be reached; any Azure host fails the test."""
    real_connect = socket.socket.connect

    def guarded(self, address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"external network call to {address}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture
def azure(monkeypatch):
    """Fake Azure controller; disabled until .enable() is called."""
    state = SimpleNamespace(calls=[], store=set())
    monkeypatch.setattr(ingestion, "azure_search_enabled", lambda: False)
    monkeypatch.setattr(azure_index, "_search_client", lambda: FakeSearchClient(state.calls, state.store))

    def enable(**fail):
        monkeypatch.setattr(ingestion, "azure_search_enabled", lambda: True)
        monkeypatch.setattr(
            azure_index, "_search_client", lambda: FakeSearchClient(state.calls, state.store, **fail)
        )

    state.enable = enable
    return state


def _ops(azure):
    """Recorded Azure operations without the client-close markers."""
    return [c for c in azure.calls if c[0] != "close"]


@pytest.fixture
def embedder(monkeypatch):
    """Embedder fake: returns a vector unless the call number is in .fail_on."""
    state = SimpleNamespace(fail_on=set(), n=0)

    async def fake_embed(_text):
        state.n += 1
        return None if state.n in state.fail_on else VECTOR

    monkeypatch.setattr(ingestion, "embed_text", fake_embed)
    return state


@pytest.fixture
def doc_id():
    did = f"pytest-kbi-{uuid.uuid4().hex[:8]}"
    yield did
    delete_chunks_by_parent(did)


async def _ingest(doc_id, text=TEXT):
    return await ingestion.ingest_file_bytes(
        text.encode("utf-8"), "bao-cao.txt", doc_id=doc_id, chunk_size=CHUNK_SIZE, chunk_overlap=10
    )


def _ids(doc_id, n):
    return [f"{doc_id}__chunk_{i:04d}" for i in range(n)]


@pytest.mark.asyncio
async def test_all_chunks_embedded(doc_id, azure, embedder):
    result = await _ingest(doc_id)
    assert result["parent_doc_id"] == doc_id
    assert result["chunks_stored"] == 3
    assert result["embedded_count"] == 3
    assert result["has_embeddings"] is True


@pytest.mark.asyncio
async def test_partial_embedding_is_reported(doc_id, azure, embedder):
    embedder.fail_on = {2}
    result = await _ingest(doc_id)
    assert result["chunks_stored"] == 3
    assert result["embedded_count"] == 2
    assert result["has_embeddings"] is False
    assert get_document_with_chunks(doc_id)["embedded_count"] == 2


@pytest.mark.asyncio
async def test_azure_disabled_makes_no_calls(doc_id, azure, embedder):
    result = await _ingest(doc_id)
    assert result["azure"] == {"enabled": False, "indexed": 0, "total": 0, "error": None}
    assert _ops(azure) == []
    assert get_document_with_chunks(doc_id)["azure_indexed"] is None


@pytest.mark.asyncio
async def test_azure_success_uploads_new_chunk_ids(doc_id, azure, embedder):
    azure.enable()
    result = await _ingest(doc_id)
    assert result["azure"] == {"enabled": True, "indexed": 3, "total": 3, "error": None}
    assert _ops(azure) == [("upload", _ids(doc_id, 3))]
    assert get_document_with_chunks(doc_id)["azure_indexed"] is True


@pytest.mark.asyncio
async def test_azure_upload_failure_keeps_postgres(doc_id, azure, embedder):
    azure.enable(fail_upload=True)
    result = await _ingest(doc_id)
    assert result["chunks_stored"] == 3
    assert result["azure"] == {
        "enabled": True,
        "indexed": 0,
        "total": 3,
        "error": "ConnectionError: Azure sync failed",
    }
    assert list_document_row_ids(doc_id) == _ids(doc_id, 3)
    assert get_document_with_chunks(doc_id)["azure_indexed"] is False


@pytest.mark.asyncio
async def test_reingest_with_fewer_chunks_purges_stale_ids(doc_id, azure, embedder):
    azure.enable()
    await _ingest(doc_id)
    azure.calls.clear()
    result = await _ingest(doc_id, "D" * 90)
    assert result["chunks_stored"] == 1
    assert _ops(azure) == [("delete", _ids(doc_id, 3)[1:]), ("upload", _ids(doc_id, 1))]
    assert list_document_row_ids(doc_id) == _ids(doc_id, 1)


@pytest.mark.asyncio
async def test_delete_removes_rows_azure_first(doc_id, azure, embedder, monkeypatch):
    azure.enable()
    await _ingest(doc_id)
    azure.calls.clear()
    real_delete = ingestion.delete_rows_by_ids

    def recording_delete(ids):
        azure.calls.append(("pg_delete", list(ids)))
        return real_delete(ids)

    monkeypatch.setattr(ingestion, "delete_rows_by_ids", recording_delete)
    result = ingestion.delete_document(doc_id)
    assert _ops(azure) == [("delete", _ids(doc_id, 3)), ("pg_delete", _ids(doc_id, 3))]
    assert result == {
        "doc_id": doc_id,
        "deleted_rows": 3,
        "azure": {"enabled": True, "deleted": 3, "error": None},
    }
    assert list_document_row_ids(doc_id) == []


@pytest.mark.asyncio
async def test_delete_azure_failure_keeps_postgres(doc_id, azure, embedder):
    azure.enable()
    await _ingest(doc_id)
    azure.enable(fail_delete=True)
    with pytest.raises(ingestion.AzureSyncError):
        ingestion.delete_document(doc_id)
    assert list_document_row_ids(doc_id) == _ids(doc_id, 3)


def test_delete_missing_document(doc_id, azure):
    azure.enable()
    with pytest.raises(ingestion.KnowledgeDocumentNotFound):
        ingestion.delete_document(doc_id)
    assert _ops(azure) == []


@pytest.mark.asyncio
async def test_second_delete_is_not_found(doc_id, azure, embedder):
    azure.enable()
    await _ingest(doc_id)
    ingestion.delete_document(doc_id)
    azure.calls.clear()
    with pytest.raises(ingestion.KnowledgeDocumentNotFound):
        ingestion.delete_document(doc_id)
    assert _ops(azure) == []


@pytest.mark.asyncio
async def test_delete_with_azure_disabled_touches_postgres_only(doc_id, azure, embedder):
    await _ingest(doc_id)
    result = ingestion.delete_document(doc_id)
    assert result["deleted_rows"] == 3
    assert result["azure"] == {"enabled": False, "deleted": 0, "error": None}
    assert _ops(azure) == []
    assert list_document_row_ids(doc_id) == []


def test_azure_helpers_noop_on_empty_ids(azure):
    assert azure_index.delete_by_ids([]) == 0
    assert azure_index.index_chunks([]) == (0, 0)
    assert _ops(azure) == []


@pytest.mark.asyncio
async def test_delete_partial_azure_rejection_keeps_postgres(doc_id, azure, embedder):
    azure.enable()
    await _ingest(doc_id)
    azure.enable(partial_delete=True)
    with pytest.raises(ingestion.AzureSyncError):
        ingestion.delete_document(doc_id)
    assert list_document_row_ids(doc_id) == _ids(doc_id, 3)


@pytest.mark.asyncio
async def test_reingest_stale_purge_rejected_marks_not_indexed(doc_id, azure, embedder):
    azure.enable()
    await _ingest(doc_id)
    azure.calls.clear()
    azure.enable(partial_delete=True)
    result = await _ingest(doc_id, "D" * 90)
    assert result["azure"] == {
        "enabled": True, "indexed": 0, "total": 1,
        "error": "AzureBatchRejected: Azure sync failed",
    }
    assert get_document_with_chunks(doc_id)["azure_indexed"] is False
    assert _ops(azure) == [("delete", _ids(doc_id, 3)[1:])]


@pytest.mark.asyncio
async def test_partial_upload_marks_not_indexed(doc_id, azure, embedder):
    azure.enable(partial_upload=True)
    result = await _ingest(doc_id)
    assert result["azure"] == {
        "enabled": True, "indexed": 0, "total": 3,
        "error": "AzureBatchRejected: Azure sync failed",
    }
    assert get_document_with_chunks(doc_id)["azure_indexed"] is False


def test_batches_are_capped_at_1000(azure):
    azure.enable()
    ids = [f"x{i}" for i in range(1001)]
    assert azure_index.delete_by_ids(ids) == 1001
    assert [len(c[1]) for c in _ops(azure)] == [1000, 1]
    azure.calls.clear()
    docs = [{"doc_id": i, "title": "t", "content": "c", "domain": "d", "source": "s"} for i in ids]
    assert azure_index.index_chunks(docs) == (1001, 1001)
    assert [len(c[1]) for c in _ops(azure)] == [1000, 1]


@pytest.mark.asyncio
async def test_flag_write_failure_does_not_fail_upload(doc_id, azure, embedder, monkeypatch):
    azure.enable(fail_upload=True)

    def broken(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(ingestion, "set_azure_indexed", broken)
    result = await _ingest(doc_id)
    assert result["chunks_stored"] == 3
    assert result["azure"]["error"] == "ConnectionError: Azure sync failed"


@pytest.mark.asyncio
async def test_delete_removes_exactly_the_ids_sent_to_azure(doc_id, azure, embedder, monkeypatch):
    azure.enable()
    await _ingest(doc_id)
    # A row whose doc_id equals the parent id but which belongs to ANOTHER document:
    # a parent-based Postgres delete would take it, list_document_row_ids (and Azure) do not.
    other = f"{doc_id}-other"
    upsert_document(doc_id=doc_id, title="foreign", content="x", parent_doc_id=other, chunk_index=0)
    azure.calls.clear()
    pg_ids = []
    real = ingestion.delete_rows_by_ids

    def recording(ids):
        pg_ids.append(list(ids))
        return real(ids)

    monkeypatch.setattr(ingestion, "delete_rows_by_ids", recording)
    result = ingestion.delete_document(doc_id)
    assert result["deleted_rows"] == 3
    assert _ops(azure) == [("delete", _ids(doc_id, 3))]
    assert pg_ids == [_ids(doc_id, 3)]
    assert list_document_row_ids(other) == [doc_id]


@pytest.mark.asyncio
async def test_long_filename_ids_fit_the_varchar_100_column(azure, embedder):
    filename = "a" * 150 + ".txt"
    pid = ingestion.slugify_doc_id("a" * 150)
    try:
        result = await ingestion.ingest_file_bytes(
            TEXT.encode("utf-8"), filename, chunk_size=CHUNK_SIZE, chunk_overlap=10
        )
        assert result["parent_doc_id"] == pid
        assert result["chunks_stored"] == 3
        ids = list_document_row_ids(pid)
        assert len(ids) == 3
        assert max(len(i) for i in ids) <= 100
    finally:
        delete_chunks_by_parent(pid)


@pytest.mark.asyncio
async def test_reingest_under_a_chunk_id_leaves_other_document_intact(doc_id, azure, embedder):
    azure.enable()
    await _ingest(doc_id)
    colliding = f"{doc_id}__chunk_0000"
    try:
        await _ingest(colliding, "D" * 90)
        # Postgres and Azure must agree: the first document is untouched in both.
        assert list_document_row_ids(doc_id) == _ids(doc_id, 3)
        assert get_document_with_chunks(doc_id)["azure_indexed"] is True
        assert azure.store == set(_ids(doc_id, 3)) | {f"{colliding}__chunk_0000"}
    finally:
        delete_chunks_by_parent(colliding)


@pytest.mark.asyncio
async def test_flag_true_write_failure_does_not_fail_upload(doc_id, azure, embedder, monkeypatch):
    azure.enable()

    def broken(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(ingestion, "set_azure_indexed", broken)
    result = await _ingest(doc_id)
    assert result["azure"] == {"enabled": True, "indexed": 3, "total": 3, "error": None}


def test_upload_from_pg_reports_partial_rejection_without_raising(azure, monkeypatch):
    domain = f"pytest-kbi-{uuid.uuid4().hex[:8]}"
    ids = [f"{domain}-{i}" for i in range(3)]
    for i in ids:
        upsert_document(doc_id=i, title="t", content="c", domain=domain)
    try:
        azure.enable(partial_upload=True)
        monkeypatch.setattr(azure_index, "azure_search_enabled", lambda: True)
        assert azure_index.upload_documents_from_pg(domain=domain) == (2, 3)
    finally:
        for i in ids:
            delete_chunks_by_parent(i)
