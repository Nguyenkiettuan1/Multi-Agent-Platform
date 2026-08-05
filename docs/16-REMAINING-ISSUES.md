> **English guides:** [README](../README.md) · [Local setup](12-LOCAL-SETUP.md) · [Docs index](README.md)  
> This document may still contain Vietnamese in places; prefer the English guides above for running the project.

# Vấn đề còn lại & Backlog kỹ thuật

> Cập nhật: v0.3.0 — sau đợt review code + P2 (RRF, Langfuse, feedback promotion).
> Dùng file này để lên kế hoạch sprint, không phải danh sách bug blocking local dev.

---

## Tóm tắt nhanh

| Mức | Số hạng mục | Ý nghĩa |
|-----|-------------|---------|
| **P0** | 3 | Ảnh hưởng production / scale trực tiếp |
| **P1** | 5 | Maintainability, kiến trúc |
| **P2** | 6 | Test, observability, feature gap |
| **P3** | 4 | Nice-to-have, cloud, UI |

**Điểm chất lượng hiện tại:** ~7.5/10 — MVP enterprise-ready, chưa high-traffic production.

---

## P0 — Production & scale

### 1. Sync DB trong async handlers (blocking event loop)

**Vấn đề:** FastAPI `async def` routes và một số workflow path gọi `engine.connect()` đồng bộ → block event loop khi concurrent cao.

**Vị trí:** `gateway/main.py`, `core/observability/audit.py`, `core/intelligence/feedback_store.py`, workers.

**Hướng xử lý:**
- Ngắn hạn: `asyncio.to_thread()` cho mọi DB call trong async route
- Dài hạn: SQLAlchemy async engine hoặc `asyncpg`

---

### 2. Dual storage feedback (in-memory vs PostgreSQL)

**Vấn đề:** `core/intelligence/feedback.py` (dict in-memory) và `feedback_store.py` (DB) có thể lệch khi chạy multi-worker uvicorn.

**Hướng xử lý:**
- Production: bắt buộc `PLATFORM_DATABASE_URL`, tắt in-memory fallback
- Hoặc Redis cache thay in-memory

---

### 3. Connection pool chưa tune

**Vấn đề:** `core/database/engines.py` đã centralize engine nhưng chưa cấu hình `pool_size`, `pool_pre_ping`, `max_overflow`.

**Hướng xử lý:** Thêm settings `DB_POOL_SIZE`, `DB_POOL_PRE_PING=true` và health check DB trong `/health`.

---

## P1 — Kiến trúc & maintainability

### 4. Layering violation: `core/` import `workflows.state`

**Vấn đề:** `AgentId`, `TriageResult`, `IntentType` nằm trong `workflows/state.py` nhưng được dùng bởi `core/control`, `core/llm`.

**Hướng xử lý:** Di chuyển sang `core/domain/state.py` hoặc `core/models/`.

---

### 5. Gateway monolithic (`gateway/main.py` ~410 dòng)

**Vấn đề:** Một file chứa chat, admin, knowledge, feedback, schemas.

**Hướng xử lý:**
```
gateway/
  main.py
  routers/chat.py, admin.py, knowledge.py, feedback.py
  schemas.py
```

---

### 6. Lazy imports trong route handlers

**Vấn đề:** `from core... import` bên trong mỗi handler — khó test, khó trace dependency.

**Hướng xử lý:** Import top-level hoặc dependency injection FastAPI.

---

### 7. Dead / stub code

| Item | Trạng thái |
|------|------------|
| `agents/db-agent/agent.py`, `agents/orchestrator/agent.py` | Foundry stub, chưa wired LangGraph |
| `platform/registry/` | Thư mục trống |
| `AgentId.CODE_WORKER` | Enum có, handler không |

**Hướng xử lý:** Xóa hoặc document rõ "planned"; tránh nhầm là đã implement.

---

### 8. Registry trùng nguồn

**Vấn đề:** `agents/registry.yaml` và `_default_registry()` trong `core/registry/agents.py` có thể lệch.

**Hướng xử lý:** YAML là single source of truth; bỏ hardcoded default hoặc generate từ YAML.

---

## P2 — Test & observability

### 9. Thiếu integration / API tests

| Chưa có test | Rủi ro |
|--------------|--------|
| `POST /api/v1/chat` | Regression chat flow |
| Auth `X-API-Key` | Lỗ hổng bảo mật |
| Admin routes | Break admin UI |
| Workflow routing (fast vs full pipeline) | Bug routing ẩn |
| `parsers.py` PDF/DOCX | Upload fail production |
| MCP servers | Tool contract break |

**Hiện tại:** 48 unit tests pass — tốt cho core logic, chưa đủ cho E2E.

---

### 10. Không có Dockerfile / containerize app

**Vấn đề:** `docker-compose.yml` chỉ có Postgres, Redis, pgAdmin — chưa có image cho API gateway.

**Hướng xử lý:** `Dockerfile` multi-stage + `docker compose` service `api`.

---

### 11. Metrics & alerting

**Vấn đề:** Langfuse tracing optional; chưa có Prometheus `/metrics`, chưa alert P95 latency.

---

### 12. Rate limiting & request size

**Vấn đề:** Chưa rate limit per user/IP; upload file chưa giới hạn size rõ trong gateway.

---

### 13. Streaming chat response

**Vấn đề:** `POST /chat` trả full response một lần — UX chat chậm khi response dài.

**Hướng xử lý:** SSE/WebSocket streaming từ LangGraph (P2 frontend).

---

### 14. Azure vector search thật

**Vấn đề:** Azure Search index có script manual (`scripts/index_azure.py`); chưa vector search native trên Azure.

---

## P3 — Feature & cloud

### 15. Dashboard UI (React)

**Trạng thái:** Backend API sẵn (`/admin/overview`, stats, audit, knowledge) — **chưa có frontend**.

→ Xem brief cho team: [`FRONTEND-DESIGN-BRIEF.md`](./FRONTEND-DESIGN-BRIEF.md)

---

### 16. Entra ID / OAuth2

**Trạng thái:** Chỉ `X-API-Key` (optional local). Production cần Entra ID.

---

### 17. Background job queue

**Vấn đề:** Ingest file, embed, promote RAG chạy sync trong request — timeout khi file lớn.

**Hướng xử lý:** Celery / ARQ / Azure Service Bus.

---

### 18. Azure Blob indexer tự động

**Trạng thái:** Doc only — [`14-AZURE-BLOB-INDEXER.md`](./14-AZURE-BLOB-INDEXER.md)

---

## Đã xử lý (không cần làm lại)

| Item | Giải pháp |
|------|-----------|
| `create_engine()` lặp 10+ chỗ | `core/database/engines.py` |
| `admin/stats` trùng `overview` | Delegate sang `build_admin_overview()` |
| Version lệch 0.2.0 / 0.3.0 | `config/version.py` |
| SQL inline list knowledge | `pgvector_store.list_documents()` |
| Test hybrid trùng 2 file | Gộp vào `test_search.py` |
| RRF hybrid search | `fusion.py` + parallel `hybrid.py` |
| Langfuse tracing | `tracing.py` + wire LLM/workflow |
| Feedback → RAG promotion | Migration 009 + `knowledge_promotion.py` |
| `.gitignore` / `.dockerignore` | Bổ sung env, cache, data exports |

---

## Gợi ý thứ tự sprint

| Sprint | Focus |
|--------|-------|
| **S1** | Gateway routers + API tests + async DB wrapper |
| **S2** | Frontend MVP (chat + admin overview) — theo FRONTEND brief |
| **S3** | Dockerfile + feedback DB-only mode + health check DB |
| **S4** | Streaming chat + rate limit + metrics |
| **S5** | Entra ID + background ingest queue |

---

## Liên hệ tài liệu liên quan

- Setup local: [`12-LOCAL-SETUP.md`](./12-LOCAL-SETUP.md)
- RAG & observability: [`13-RAG-OBSERVABILITY-GUIDE.md`](./13-RAG-OBSERVABILITY-GUIDE.md)
- Feedback loop: [`15-FEEDBACK-LOOP.md`](./15-FEEDBACK-LOOP.md)
- Frontend design brief: [`FRONTEND-DESIGN-BRIEF.md`](./FRONTEND-DESIGN-BRIEF.md)
