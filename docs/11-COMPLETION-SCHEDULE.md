# Lịch hoàn thiện platform — PHANLAW Multi-Agent

> Cập nhật: sau sprint RAG + Control Plane

## Quyết định kiến trúc RAG

| Câu hỏi | Quyết định |
|---------|------------|
| Vector DB? | **PostgreSQL + pgvector** — cùng DB, local = prod |
| Azure Search? | **Bổ sung** — hybrid search, cloud scale |
| Qdrant? | **Không cần** — trừ khi >10M vectors |

```
Query → Azure AI Search (nếu có key)
      → pgvector semantic (nếu có embedding API)
      → PostgreSQL FTS (fallback, luôn chạy được)
```

---

## Trạng thái hiện tại

### ✅ Hoàn thành

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

### 🔄 Cần config (không phải code)

```bash
docker compose up -d
python scripts/db_migrate.py
python scripts/seed.py
python scripts/seed_vectors.py
# .env: DATABASE_URL, OPENROUTER_API_KEY, AZURE_SEARCH_*
uvicorn gateway.main:app --reload
```

---

## Lịch tiếp theo

### Tuần 1 — Chạy production local

| Ngày | Task | Exit criteria |
|------|------|---------------|
| 1 | Docker + migrate + seed | DB + vectors có data |
| 2 | OpenRouter API key | Chat LLM thật |
| 3 | Azure Search index | Hybrid search trả kết quả cloud |
| 4 | End-to-end test | 6/6 eval pass với DB live |
| 5 | Load test 50 requests | P95 < 10s |

### Tuần 2 — Enterprise hardening

| Task | Mô tả |
|------|-------|
| Entra ID auth | Thay API key bằng OAuth2 |
| Langfuse tracing | ✅ Trace LLM + workflow span (`core/observability/tracing.py`) |
| LLM-as-judge eval | Eval score bằng model |
| action-worker HITL | Human approval flow |
| A2A protocol | Agent gọi agent qua HTTP |

### Tuần 3–4 — Self-improvement (MLOps)

| Task | Mô tả |
|------|-------|
| Feedback → dataset | ✅ Export `platform.feedback` — `docs/15-FEEDBACK-LOOP.md` |
| Prompt optimizer | DSPy / Foundry optimizer |
| Fine-tune (optional) | SFT trên domain legal |
| Dynamic model routing | RouteLLM pattern |

### Tuần 5–6 — Cloud deploy

| Task | Mô tả |
|------|-------|
| Azure Container Apps | Deploy gateway |
| Azure PostgreSQL Flexible | Migrate từ local |
| Azure AI Search production index | Sync documents |
| Key Vault | Secrets management |
| CI/CD GitHub Actions | pytest + eval on PR |

---

## Checklist trước go-live

- [ ] `pytest tests/` — all pass
- [ ] `python scripts/run_eval.py` — all pass
- [ ] `API_KEY` set production
- [ ] `PLATFORM_DATABASE_URL` set
- [ ] Azure Search index populated
- [ ] pgvector embeddings seeded
- [ ] Backup strategy cho PostgreSQL
- [ ] Rate limiting trên gateway
