# Remaining Issues & Technical Backlog

> Updated: v0.3.0 — after code review + P2 (RRF, Langfuse, feedback promotion).
> Use this file for sprint planning, not as a list of bugs blocking local dev.

---

## Quick summary

| Level | Count | Meaning |
|-------|-------|---------|
| **P0** | 3 | Direct production / scale impact |
| **P1** | 5 | Maintainability, architecture |
| **P2** | 6 | Tests, observability, feature gaps |
| **P3** | 4 | Nice-to-have, cloud, UI |

**Current quality score:** ~7.5/10 — MVP enterprise-ready, not yet high-traffic production.

---

## P0 — Production & scale

### 1. Sync DB in async handlers (blocking event loop)

**Issue:** FastAPI `async def` routes and some workflow paths call synchronous `engine.connect()` → blocks event loop under high concurrency.

**Location:** `gateway/main.py`, `core/observability/audit.py`, `core/intelligence/feedback_store.py`, workers.

**Approach:**
- Short term: `asyncio.to_thread()` for all DB calls in async routes
- Long term: SQLAlchemy async engine or `asyncpg`

---

### 2. Dual storage feedback (in-memory vs PostgreSQL)

**Issue:** `core/intelligence/feedback.py` (in-memory dict) and `feedback_store.py` (DB) can diverge when running multi-worker uvicorn.

**Approach:**
- Production: require `PLATFORM_DATABASE_URL`, disable in-memory fallback
- Or Redis cache instead of in-memory

---

### 3. Connection pool not tuned

**Issue:** `core/database/engines.py` centralizes engine but lacks `pool_size`, `pool_pre_ping`, `max_overflow` configuration.

**Approach:** Add settings `DB_POOL_SIZE`, `DB_POOL_PRE_PING=true` and DB health check in `/health`.

---

## P1 — Architecture & maintainability

### 4. Layering violation: `core/` imports `workflows.state`

**Issue:** `AgentId`, `TriageResult`, `IntentType` live in `workflows/state.py` but are used by `core/control`, `core/llm`.

**Approach:** Move to `core/domain/state.py` or `core/models/`.

---

### 5. Gateway monolithic (`gateway/main.py` ~410 lines)

**Issue:** One file contains chat, admin, knowledge, feedback, schemas.

**Approach:**
```
gateway/
  main.py
  routers/chat.py, admin.py, knowledge.py, feedback.py
  schemas.py
```

---

### 6. Lazy imports in route handlers

**Issue:** `from core... import` inside each handler — hard to test, hard to trace dependencies.

**Approach:** Top-level imports or FastAPI dependency injection.

---

### 7. Dead / stub code

| Item | Status |
|------|--------|
| `agents/db-agent/agent.py`, `agents/orchestrator/agent.py` | Foundry stub, not wired to LangGraph |
| `platform/registry/` | Empty directory |
| `AgentId.CODE_WORKER` | Enum exists, no handler |

**Approach:** Delete or clearly document as "planned"; avoid confusion that it's implemented.

---

### 8. Duplicate registry sources

**Issue:** `agents/registry.yaml` and `_default_registry()` in `core/registry/agents.py` can diverge.

**Approach:** YAML is single source of truth; remove hardcoded default or generate from YAML.

---

## P2 — Test & observability

### 9. Missing integration / API tests

| No test yet | Risk |
|-------------|------|
| `POST /api/v1/chat` | Chat flow regression |
| Auth `X-API-Key` | Security vulnerability |
| Admin routes | Break admin UI |
| Workflow routing (fast vs full pipeline) | Hidden routing bugs |
| `parsers.py` PDF/DOCX | Upload fail in production |
| MCP servers | Tool contract break |

**Current:** 48 unit tests pass — good for core logic, not enough for E2E.

---

### 10. No Dockerfile / containerized app

**Issue:** `docker-compose.yml` only has Postgres, Redis, pgAdmin — no image for API gateway.

**Approach:** Multi-stage `Dockerfile` + `docker compose` service `api`.

---

### 11. Metrics & alerting

**Issue:** Langfuse tracing optional; no Prometheus `/metrics`, no P95 latency alerts.

---

### 12. Rate limiting & request size

**Issue:** No rate limit per user/IP; file upload size not clearly limited in gateway.

---

### 13. Streaming chat response

**Issue:** `POST /chat` returns full response at once — slow UX for long responses.

**Approach:** SSE/WebSocket streaming from LangGraph (P2 frontend).

---

### 14. Real Azure vector search

**Issue:** Azure Search index has manual script (`scripts/index_azure.py`); no native vector search on Azure yet.

---

## P3 — Feature & cloud

### 15. Dashboard UI (React)

**Status:** Backend API ready (`/admin/overview`, stats, audit, knowledge) — **no frontend yet**.

→ See team brief: [`FRONTEND-DESIGN-BRIEF.md`](./FRONTEND-DESIGN-BRIEF.md)

---

### 16. Entra ID / OAuth2

**Status:** Only `X-API-Key` (optional local). Production needs Entra ID.

---

### 17. Background job queue

**Issue:** File ingest, embed, promote RAG run synchronously in request — timeout on large files.

**Approach:** Celery / ARQ / Azure Service Bus.

---

### 18. Azure Blob auto indexer

**Status:** Doc only — [`14-AZURE-BLOB-INDEXER.md`](./14-AZURE-BLOB-INDEXER.md)

---

## Already resolved (no need to redo)

| Item | Solution |
|------|----------|
| `create_engine()` repeated 10+ places | `core/database/engines.py` |
| `admin/stats` duplicates `overview` | Delegate to `build_admin_overview()` |
| Version mismatch 0.2.0 / 0.3.0 | `config/version.py` |
| Inline SQL list knowledge | `pgvector_store.list_documents()` |
| Duplicate hybrid tests in 2 files | Merged into `test_search.py` |
| RRF hybrid search | `fusion.py` + parallel `hybrid.py` |
| Langfuse tracing | `tracing.py` + wire LLM/workflow |
| Feedback → RAG promotion | Migration 009 + `knowledge_promotion.py` |
| `.gitignore` / `.dockerignore` | Added env, cache, data exports |

---

## Suggested sprint order

| Sprint | Focus |
|--------|-------|
| **S1** | Gateway routers + API tests + async DB wrapper |
| **S2** | Frontend MVP (chat + admin overview) — per FRONTEND brief |
| **S3** | Dockerfile + feedback DB-only mode + health check DB |
| **S4** | Streaming chat + rate limit + metrics |
| **S5** | Entra ID + background ingest queue |

---

## Related documentation

- Local setup: [`12-LOCAL-SETUP.md`](./12-LOCAL-SETUP.md)
- RAG & observability: [`13-RAG-OBSERVABILITY-GUIDE.md`](./13-RAG-OBSERVABILITY-GUIDE.md)
- Feedback loop: [`15-FEEDBACK-LOOP.md`](./15-FEEDBACK-LOOP.md)
- Frontend design brief: [`FRONTEND-DESIGN-BRIEF.md`](./FRONTEND-DESIGN-BRIEF.md)
