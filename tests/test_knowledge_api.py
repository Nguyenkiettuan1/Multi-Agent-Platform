"""Knowledge admin API: real dev Postgres for data, fake Azure and fake embedder."""

from __future__ import annotations

import socket
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from core.database.engines import get_platform_engine
from core.search import azure_index, azure_search, embeddings, ingestion
from core.search.ingestion import MAX_PARENT_DOC_ID_LEN, slugify_doc_id
from core.search.pgvector_store import delete_chunks_by_parent, upsert_document
from gateway.main import _valid_doc_id, app

VECTOR = [0.01] * 1536
BASE = "/api/v1/admin/knowledge"


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    """Best-effort guard: fail blocking socket connects to non-loopback hosts.

    asyncio's Windows ProactorEventLoop connects via IocpProactor and bypasses this patch, so the
    embedder is also replaced by a raising stub; tests that need vectors override it.
    """
    async def no_embed(_text):
        raise AssertionError("real embedder called in a test")

    monkeypatch.setattr(ingestion, "embed_text", no_embed)
    monkeypatch.setattr(embeddings, "embed_text", no_embed)
    real_connect = socket.socket.connect

    def guarded(self, address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"external network call to {address}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)


class FakeSearchClient:
    def __init__(self, calls: list, *, fail_delete=False, reject_one=False):
        self.calls = calls
        self.fail_delete = fail_delete
        self.reject_one = reject_one

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def upload_documents(self, documents):
        self.calls.append(("upload", [d["id"] for d in documents]))
        return [SimpleNamespace(succeeded=True) for _ in documents]

    def delete_documents(self, documents):
        self.calls.append(("delete", [d["id"] for d in documents]))
        if self.fail_delete:
            raise ConnectionError("boom https://secret.example")
        return [SimpleNamespace(succeeded=not (self.reject_one and i == 0), status_code=503) for i, _ in enumerate(documents)]


@pytest.fixture
def azure(monkeypatch):
    """Fake Azure, disabled until .enable() is called."""
    state = SimpleNamespace(calls=[])

    def set_enabled(value: bool):
        monkeypatch.setattr(ingestion, "azure_search_enabled", lambda: value)
        monkeypatch.setattr(azure_search, "azure_search_enabled", lambda: value)

    def enable(**fail):
        set_enabled(True)
        monkeypatch.setattr(
            azure_index, "_search_client", lambda: FakeSearchClient(state.calls, **fail)
        )

    set_enabled(False)
    monkeypatch.setattr(azure_index, "_search_client", lambda: FakeSearchClient(state.calls))
    state.enable = enable
    return state


@pytest.fixture
def client(admin_client):
    """Every knowledge route is admin-only since MA-AU-T7."""
    return admin_client


@pytest.fixture
def prefix():
    """Unique id prefix; only rows (and audit entries) under it are removed on teardown."""
    pfx = f"pytest-kba-{uuid.uuid4().hex[:8]}"
    yield pfx
    for suffix in ("-a", "-b", "-c", "-up", "-gen"):
        delete_chunks_by_parent(pfx + suffix)
    with get_platform_engine().connect() as conn:
        conn.execute(
            text("DELETE FROM platform.audit_log WHERE action = 'knowledge_delete' AND payload->>'doc_id' LIKE :p"),
            {"p": pfx + "%"},
        )
        conn.commit()


def make_doc(parent: str, *, chunks: int = 2, domain: str = "general", embedded: bool = True) -> None:
    for i in range(chunks):
        upsert_document(
            doc_id=f"{parent}__chunk_{i:04d}",
            title=f"Title {parent} (chunk {i + 1}/{chunks})",
            content=f"content {i} of {parent}",
            domain=domain,
            embedding=VECTOR if embedded else None,
            parent_doc_id=parent,
            chunk_index=i,
        )


def audit_rows(doc_id: str) -> list[dict]:
    with get_platform_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT payload FROM platform.audit_log WHERE action = 'knowledge_delete' AND payload->>'doc_id' = :d"),
            {"d": doc_id},
        ).mappings().all()
    return [r["payload"] for r in rows]


def test_list_shape_and_total(client, azure, prefix):
    make_doc(prefix + "-a", chunks=3)
    body = client.get(f"{BASE}/documents", params={"limit": 200}).json()
    assert set(body) == {"items", "total", "azure_enabled"}
    assert body["azure_enabled"] is False
    mine = next(i for i in body["items"] if i["doc_id"] == prefix + "-a")
    assert mine["chunk_count"] == 3 and mine["embedded_count"] == 3
    assert set(mine) == {
        "doc_id", "title", "domain", "source", "chunk_count", "embedded_count",
        "content_length", "azure_indexed", "created_at", "updated_at",
    }
    assert isinstance(mine["content_length"], int)
    assert isinstance(mine["created_at"], str) and isinstance(mine["updated_at"], str)
    assert body["total"] >= 1


def test_pagination_counts_documents_not_chunks(client, azure, prefix):
    for s in ("-a", "-b", "-c"):
        make_doc(prefix + s, chunks=3, domain=prefix)
    first = client.get(f"{BASE}/documents", params={"domain": prefix, "limit": 2, "offset": 0}).json()
    second = client.get(f"{BASE}/documents", params={"domain": prefix, "limit": 2, "offset": 2}).json()
    assert first["total"] == 3 and second["total"] == 3
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    ids = [i["doc_id"] for i in first["items"] + second["items"]]
    assert sorted(ids) == [prefix + s for s in ("-a", "-b", "-c")]


def test_domain_filter(client, azure, prefix):
    make_doc(prefix + "-a", domain=prefix)
    make_doc(prefix + "-b", domain="general")
    body = client.get(f"{BASE}/documents", params={"domain": prefix}).json()
    assert [i["doc_id"] for i in body["items"]] == [prefix + "-a"]
    assert body["total"] == 1


def test_sorted_by_updated_at_desc(client, azure, prefix):
    make_doc(prefix + "-a", domain=prefix)
    make_doc(prefix + "-b", domain=prefix)
    upsert_document(  # touching -a makes it the most recently updated document
        doc_id=prefix + "-a__chunk_0000", title="t", content="changed", domain=prefix,
        embedding=VECTOR, parent_doc_id=prefix + "-a", chunk_index=0,
    )
    body = client.get(f"{BASE}/documents", params={"domain": prefix}).json()
    assert [i["doc_id"] for i in body["items"]] == [prefix + "-a", prefix + "-b"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_list_rejects_bad_paging(client, azure, params):
    assert client.get(f"{BASE}/documents", params=params).status_code == 422


def test_detail_includes_azure_enabled(client, azure, prefix):
    make_doc(prefix + "-a", chunks=2)
    resp = client.get(f"{BASE}/documents/{prefix}-a")
    assert resp.status_code == 200
    body = resp.json()
    assert body["doc_id"] == prefix + "-a"
    assert body["azure_enabled"] is False
    assert body["chunk_count"] == 2 and len(body["chunks"]) == 2
    assert set(body) == {
        "doc_id", "title", "domain", "source", "chunk_count", "embedded_count", "azure_indexed",
        "azure_enabled", "content", "chunks", "content_length", "created_at", "updated_at",
    }
    assert set(body["chunks"][0]) == {"doc_id", "chunk_index", "char_count", "has_embedding", "content"}
    assert body["content"].startswith("content 0")


def test_detail_reports_azure_enabled_true(client, azure, prefix):
    make_doc(prefix + "-a")
    azure.enable()
    assert client.get(f"{BASE}/documents/{prefix}-a").json()["azure_enabled"] is True


def test_detail_404_on_missing(client, azure, prefix):
    assert client.get(f"{BASE}/documents/{prefix}-missing").status_code == 404


@pytest.mark.parametrize("bad", ["has%20space", "%2e%2e", "%2e", "a" * 201, "caf%C3%A9"])
def test_bad_doc_id_is_422(client, azure, bad):
    assert client.get(f"{BASE}/documents/{bad}").status_code == 422
    assert client.delete(f"{BASE}/documents/{bad}").status_code == 422


@pytest.mark.parametrize("bad", [".", "..", "...", ""])
def test_dot_only_ids_are_rejected_by_validator(bad):
    """httpx resolves literal `..` before sending, so the HTTP test above only reaches `%2e%2e`."""
    with pytest.raises(HTTPException) as exc:
        _valid_doc_id(bad)
    assert exc.value.status_code == 422


def test_encoded_slash_never_reaches_a_handler(client, azure):
    assert client.get(f"{BASE}/documents/a%2Fb").status_code == 404
    assert client.delete(f"{BASE}/documents/a%2Fb").status_code == 404


def test_max_length_id_is_accepted(client, azure):
    assert client.get(f"{BASE}/documents/{'a' * 200}").status_code == 404


def test_delete_removes_rows_and_audits(client, azure, prefix):
    did = prefix + "-a"
    make_doc(did, chunks=3)
    resp = client.delete(f"{BASE}/documents/{did}")
    assert resp.status_code == 200
    assert resp.json() == {
        "doc_id": did, "deleted_rows": 3, "azure": {"enabled": False, "deleted": 0, "error": None},
    }
    assert client.get(f"{BASE}/documents/{did}").status_code == 404
    assert client.delete(f"{BASE}/documents/{did}").status_code == 404

    [payload] = audit_rows(did)  # the 404 attempt wrote nothing
    assert payload["deleted_rows"] == 3
    assert payload["azure"] == {"enabled": False, "deleted": 0, "error": None}
    assert "content" not in payload


def test_delete_with_azure_enabled_reports_count(client, azure, prefix):
    did = prefix + "-a"
    make_doc(did, chunks=2)
    azure.enable()
    body = client.delete(f"{BASE}/documents/{did}").json()
    assert body["azure"]["enabled"] is True and body["azure"]["deleted"] == 2
    assert audit_rows(did)[0]["azure"]["deleted"] == 2


def test_delete_azure_failure_is_502_and_keeps_postgres(client, azure, prefix):
    did = prefix + "-a"
    make_doc(did, chunks=2)
    azure.enable(fail_delete=True)
    resp = client.delete(f"{BASE}/documents/{did}")
    assert resp.status_code == 502
    assert "secret.example" not in resp.text and "ConnectionError" not in resp.text
    assert client.get(f"{BASE}/documents/{did}").status_code == 200

    [payload] = audit_rows(did)
    assert payload["deleted_rows"] == 0
    assert payload["error"] == "AzureSyncError"


def test_new_routes_are_not_shadowed(client, azure, prefix):
    """`documents` must not be captured as {parent_doc_id} of the legacy /chunks route."""
    paths = [r.path for r in app.routes if getattr(r, "path", "").startswith(BASE)]
    assert paths.index(f"{BASE}/documents") < paths.index(f"{BASE}/{{parent_doc_id}}/chunks")
    assert client.get(f"{BASE}/documents").json().keys() >= {"items", "total"}
    make_doc(prefix + "-a")
    # legacy route still works and still returns its own shape
    legacy = client.get(f"{BASE}/{prefix}-a/chunks").json()
    assert legacy["parent_doc_id"] == prefix + "-a" and legacy["count"] == 2
    # `/documents/chunks` fits both patterns; the detail route must win (404 for a missing doc "chunks"),
    # whereas the legacy route would answer 200 with an empty chunk list for parent "documents".
    assert client.get(f"{BASE}/documents/chunks").status_code == 404


def test_upload_returns_embedding_and_azure_fields(client, azure, prefix, monkeypatch):
    async def fake_embed(_text):
        return VECTOR

    monkeypatch.setattr(ingestion, "embed_text", fake_embed)
    resp = client.post(
        f"{BASE}/upload",
        files={"file": ("note.txt", b"hello knowledge api", "text/plain")},
        data={"doc_id": prefix + "-up"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["parent_doc_id"] == prefix + "-up"
    assert body["embedded_count"] == body["chunks_stored"] >= 1
    assert body["has_embeddings"] is True
    assert body["azure"] == {"enabled": False, "indexed": 0, "total": 0, "error": None}
    detail = client.get(f"{BASE}/documents/{prefix}-up").json()
    assert detail["embedded_count"] == body["embedded_count"]


def test_parentless_single_row_document(client, azure, prefix):
    did = prefix + "-a"
    upsert_document(doc_id=did, title="Solo", content="only row", embedding=VECTOR)
    body = client.get(f"{BASE}/documents/{did}").json()
    assert body["doc_id"] == did and body["chunk_count"] == 1
    assert [c["doc_id"] for c in body["chunks"]] == [did]
    assert body["chunks"][0]["chunk_index"] is None
    assert body["content"] == "only row"
    assert client.delete(f"{BASE}/documents/{did}").json()["deleted_rows"] == 1


def test_delete_partial_azure_rejection_returns_502_and_keeps_rows(client, azure, prefix):
    did = prefix + "-a"
    make_doc(did, chunks=2)
    azure.enable(reject_one=True)
    resp = client.delete(f"{BASE}/documents/{did}")
    assert resp.status_code == 502
    assert client.get(f"{BASE}/documents/{did}").json()["chunk_count"] == 2


@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize("path", ["%2e%2e", "has%20space", "pytest-kba-valid"])
def test_auth_runs_before_doc_id_validation(anon_client, user_client, api_key_client, azure, method, path):
    """No credential -> 401 and a regular user -> 403, both before doc_id is validated."""
    url = f"{BASE}/documents/{path}"
    assert anon_client.request(method, url).status_code == 401
    assert user_client.request(method, url).status_code == 403
    expected = 404 if path == "pytest-kba-valid" else 422
    assert api_key_client.request(method, url).status_code == expected


# ---- doc_id validation on the two writers (POST /admin/knowledge, POST /admin/knowledge/upload) ----

BAD_WRITE_IDS = ["has space", "tài-liệu", "..", ".", "a" * 201]


def _post_json(client, doc_id):
    return client.post(BASE, json={"doc_id": doc_id, "title": "t", "content": "c"})


def _post_upload(client, doc_id=None, filename="note.txt"):
    data = {"doc_id": doc_id} if doc_id is not None else {}
    return client.post(
        f"{BASE}/upload", files={"file": (filename, b"hello knowledge api", "text/plain")}, data=data
    )


@pytest.fixture
def fake_embedder(monkeypatch):
    async def fake_embed(_text):
        return VECTOR

    monkeypatch.setattr(ingestion, "embed_text", fake_embed)
    monkeypatch.setattr(embeddings, "embed_text", fake_embed)


def _rows_for(doc_id: str) -> int:
    from core.search.pgvector_store import list_document_row_ids

    return len(list_document_row_ids(doc_id))


@pytest.mark.parametrize("bad", BAD_WRITE_IDS)
def test_json_ingest_rejects_bad_doc_id(client, azure, fake_embedder, bad):
    try:
        resp = _post_json(client, bad)
        assert resp.status_code == 422
        assert "doc_id" in resp.text
        assert _rows_for(bad) == 0
    finally:
        delete_chunks_by_parent(bad)  # a failing assertion must not leave the row behind


@pytest.mark.parametrize("bad", BAD_WRITE_IDS)
def test_upload_rejects_bad_doc_id(client, azure, fake_embedder, bad):
    try:
        resp = _post_upload(client, bad)
        assert resp.status_code == 422
        assert "doc_id" in resp.text
        assert _rows_for(bad) == 0 and _rows_for(f"{bad}__chunk_0000") == 0
    finally:
        delete_chunks_by_parent(bad)


def test_json_ingest_accepts_valid_id(client, azure, fake_embedder, prefix):
    did = prefix + "-a"
    assert _post_json(client, did).status_code == 200
    assert client.get(f"{BASE}/documents/{did}").status_code == 200


def test_json_ingest_length_limit_matches_the_db_column(client, azure, fake_embedder, prefix):
    """doc_id is VARCHAR(100): 100 fits, 101 is a 422 instead of a DB error."""
    did = prefix + "-a"
    ok_id = did + "x" * (100 - len(did))
    try:
        assert _post_json(client, ok_id).status_code == 200
    finally:
        delete_chunks_by_parent(ok_id)
    too_long = ok_id + "x"
    try:
        assert _post_json(client, too_long).status_code == 422
    finally:
        delete_chunks_by_parent(too_long)


def test_upload_length_limit_leaves_room_for_chunk_suffix(client, azure, fake_embedder, prefix):
    did = prefix + "-up"
    ok_id = did + "x" * (MAX_PARENT_DOC_ID_LEN - len(did))
    try:
        assert _post_upload(client, ok_id).status_code == 200
    finally:
        delete_chunks_by_parent(ok_id)
    too_long = ok_id + "x"
    try:
        assert _post_upload(client, too_long).status_code == 422
    finally:
        delete_chunks_by_parent(too_long)


def test_upload_accepts_valid_id(client, azure, fake_embedder, prefix):
    resp = _post_upload(client, prefix + "-up")
    assert resp.status_code == 200 and resp.json()["parent_doc_id"] == prefix + "-up"


def test_upload_without_doc_id_generates_a_valid_one(client, azure, fake_embedder, prefix):
    """Unique filename: the generated id is its slug, so a real `note` document is never touched."""
    resp = _post_upload(client, filename=f"{prefix}-gen.txt")
    assert resp.status_code == 200
    generated = resp.json()["parent_doc_id"]
    assert generated == slugify_doc_id(f"{prefix}-gen")
    assert _valid_doc_id(generated) == generated
