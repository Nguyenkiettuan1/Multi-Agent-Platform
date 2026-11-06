# Feedback Loop — Collect Q&A for Evaluation & Training

> P0 closed-loop: every chat is saved, users can rate, export dataset.

---

## Flow

```
POST /api/v1/chat
  → agent responds
  → auto-save platform.feedback (Q + A + eval_score)

POST /api/v1/feedback
  → user rates 1–5 by trace_id

GET /api/v1/admin/feedback/export
  → JSONL for fine-tune / eval
```

---

## Table `platform.feedback`

| Column | Source |
|--------|--------|
| `trace_id` | Per chat (unique) |
| `session_id` | User session |
| `user_message` | Question |
| `response` | Agent answer |
| `eval_score` | Rule evaluator (0–1) |
| `rating` | User rating later (1–5) |
| `comment` | User feedback |

---

## Migration

```powershell
python scripts/db_migrate.py   # 008: unique trace_id
```

---

## Usage

### Chat (auto-saved)

```powershell
curl -X POST http://localhost:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -H "X-API-Key: $env:API_KEY" `
  -d "{\"message\": \"Xin chào\"}"
# Get trace_id from response
```

### Rate

```powershell
curl -X POST http://localhost:8000/api/v1/feedback `
  -H "Content-Type: application/json" `
  -H "X-API-Key: $env:API_KEY" `
  -d "{\"trace_id\": \"abc123...\", \"rating\": 5, \"comment\": \"Hay\"}"
```

### View / export

```powershell
curl http://localhost:8000/api/v1/admin/feedback?limit=10 -H "X-API-Key: $env:API_KEY"

curl "http://localhost:8000/api/v1/admin/feedback/export?min_rating=4&format=openai" -H "X-API-Key: $env:API_KEY" -o train.jsonl

python scripts/export_feedback.py --min-rating 4 --format openai -o data/train.jsonl
```

### Export formats

| format | Use for |
|--------|---------|
| `jsonl` | Full metadata |
| `openai` | `{"messages": [{"role":"user"...}, {"role":"assistant"...}]}` |
| `pairs` | `{"input": "...", "output": "..."}` |

---

## Export filters

- `min_rating=4` — exclude user ratings < 4 (unrated still included if `eval_score` is sufficient)
- `min_eval_score=0.7` — only evaluator-passed entries

---

## Next steps (P1/P2)

| Task | Status |
|------|--------|
| LLM-as-judge (faithfulness) | ✅ `EVAL_LLM_JUDGE_ENABLED=true` |
| Semantic reranker | ✅ `SEARCH_RERANK_ENABLED=true` (enabled by default) |
| Rule: citations_present | ✅ In `evaluator.py` |
| Langfuse tracing | ✅ `LANGFUSE_TRACING_ENABLED=true` |
| Auto-promote Q&A → RAG | ✅ `FEEDBACK_AUTO_PROMOTE_MIN_RATING=5` |
| Manual promote | ✅ `POST /api/v1/admin/feedback/{trace_id}/promote` |

---

## P2 — Feedback → RAG promotion

When user rating ≥ `FEEDBACK_AUTO_PROMOTE_MIN_RATING` (default 5), the system automatically indexes Q&A into `app.knowledge_documents` with `source=feedback_promoted`.

Migration `009_feedback_promotion.sql` adds columns `promoted_to_rag`, `promoted_doc_id`.

```powershell
python scripts/db_migrate.py   # 009
```

Manual promote:

```http
POST /api/v1/admin/feedback/{trace_id}/promote
```
