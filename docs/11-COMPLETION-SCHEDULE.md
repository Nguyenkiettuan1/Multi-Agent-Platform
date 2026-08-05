# Platform Completion Schedule — Multi-Agent Platform

> Updated: after RAG + Control Plane sprint

## RAG Architecture Decisions

| Question | Decision |
|---------|------------|
| Vector DB? | **PostgreSQL + pgvector** — same DB, local = prod |
| Azure Search? | **Supplement** — hybrid search, cloud scale |
| Qdrant? | **Not needed** — unless >10M vectors |

```
Query → Azure AI Search (if key available)
      → pgvector semantic (if embedding API available)
      → PostgreSQL FTS (fallback, always works)
```

---

## Current Status

### ✅ Completed

| Module | File |
|--------|------|
| Multi-agent pipeline | `workflows/` |
| Triage + fast path | `core/control/triage.py` |
| Guardrails + PII redact | `core/control/guardrails.py` |
| Response evaluator | `core/control/evaluator.py` |
| Model registry 3-layer | `config/models.yaml`, `agents/registry.yaml` |
| SQL MCP | `core/mcp/sql_tools.py`, `mcp-servers/sql-server/` |
| Search MCP + RAG | `core/search/`, `mcp-servers/search-server/` |
| pgvector migration | `infra/database/migrations/005_pgvector.sql` |
| Azure Search client | `core/search/azure_search.py` |
| Hybrid search | `core/search/hybrid.py` |
| Research worker | `workflows/workers/research_worker.py` |
| PostgresSaver | `core/checkpointer.py` |
| API auth | `core/security/auth.py` |
| Eval CI | `eval/runner.py`, `scripts/run_eval.py` |
| Feedback auto-save Q+A | `workflows/runner.py` → `platform.feedback` |
| Feedback export JSONL | `scripts/export_feedback.py`, `GET /admin/feedback/export` |
| Web search (Tavily) + citations | `core/search/web_search.py`, `citations.py` |
| Semantic reranker | `core/search/rerank.py` |
| LLM-as-judge eval | `core/control/llm_judge.py` |
| Upload + chunking | `scripts/ingest_file.py`, `POST /admin/knowledge/upload` |

### 🔄 Configuration needed (not code)

```bash
docker compose up -d
python scripts/db_migrate.py
python scripts/seed.py
python scripts/seed_vectors.py
# .env: DATABASE_URL, OPENROUTER_API_KEY, AZURE_SEARCH_*
uvicorn gateway.main:app --reload
```

---

## Upcoming Schedule

### Week 1 — Run production locally

| Day | Task | Exit criteria |
|------|------|---------------|
| 1 | Docker + migrate + seed | DB + vectors have data |
| 2 | OpenRouter API key | Real LLM chat |
| 3 | Azure Search index | Hybrid search returns cloud results |
| 4 | End-to-end test | 6/6 eval pass with live DB |
| 5 | Load test 50 requests | P95 < 10s |

### Week 2 — Enterprise hardening

| Task | Description |
|------|-------|
| Entra ID auth | Replace API key with OAuth2 |
| Langfuse tracing | ✅ Trace LLM + workflow span (`core/observability/tracing.py`) |
| LLM-as-judge eval | Eval score via model |
| action-worker HITL | Human approval flow |
| A2A protocol | Agent calls agent over HTTP |

### Week 3–4 — Self-improvement (MLOps)

| Task | Description |
|------|-------|
| Feedback → dataset | ✅ Export `platform.feedback` — `docs/15-FEEDBACK-LOOP.md` |
| Prompt optimizer | DSPy / Foundry optimizer |
| Fine-tune (optional) | SFT on legal domain |
| Dynamic model routing | RouteLLM pattern |

### Week 5–6 — Cloud deploy

| Task | Description |
|------|-------|
| Azure Container Apps | Deploy gateway |
| Azure PostgreSQL Flexible | Migrate from local |
| Azure AI Search production index | Sync documents |
| Key Vault | Secrets management |
| CI/CD GitHub Actions | pytest + eval on PR |

---

## Pre go-live Checklist

- [ ] `pytest tests/` — all pass
- [ ] `python scripts/run_eval.py` — all pass
- [ ] `API_KEY` set production
- [ ] `PLATFORM_DATABASE_URL` set
- [ ] Azure Search index populated
- [ ] pgvector embeddings seeded
- [ ] Backup strategy for PostgreSQL
- [ ] Rate limiting on gateway
