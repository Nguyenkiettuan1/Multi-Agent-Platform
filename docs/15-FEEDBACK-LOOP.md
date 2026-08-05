> **English guides:** [README](../README.md) · [Local setup](12-LOCAL-SETUP.md) · [Docs index](README.md)  
> This document may still contain Vietnamese in places; prefer the English guides above for running the project.

# Feedback Loop — Thu thập Q&A để đánh giá & train

> P0 closed-loop: mọi chat được lưu, user có thể rate, export dataset.

---

## Flow

```
POST /api/v1/chat
  → agent trả lời
  → auto-save platform.feedback (Q + A + eval_score)

POST /api/v1/feedback
  → user rate 1–5 theo trace_id

GET /api/v1/admin/feedback/export
  → JSONL cho fine-tune / eval
```

---

## Bảng `platform.feedback`

| Cột | Nguồn |
|-----|-------|
| `trace_id` | Mỗi chat (unique) |
| `session_id` | Session user |
| `user_message` | Câu hỏi |
| `response` | Câu trả lời agent |
| `eval_score` | Rule evaluator (0–1) |
| `rating` | User chấm sau (1–5) |
| `comment` | Góp ý user |

---

## Migration

```powershell
python scripts/db_migrate.py   # 008: unique trace_id
```

---

## Sử dụng

### Chat (tự lưu)

```powershell
curl -X POST http://localhost:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -d "{\"message\": \"Xin chào\"}"
# Lấy trace_id từ response
```

### Rate

```powershell
curl -X POST http://localhost:8000/api/v1/feedback `
  -H "Content-Type: application/json" `
  -d "{\"trace_id\": \"abc123...\", \"rating\": 5, \"comment\": \"Hay\"}"
```

### Xem / export

```powershell
curl http://localhost:8000/api/v1/admin/feedback?limit=10

curl "http://localhost:8000/api/v1/admin/feedback/export?min_rating=4&format=openai" -o train.jsonl

python scripts/export_feedback.py --min-rating 4 --format openai -o data/train.jsonl
```

### Export formats

| format | Dùng cho |
|--------|----------|
| `jsonl` | Full metadata |
| `openai` | `{"messages": [{"role":"user"...}, {"role":"assistant"...}]}` |
| `pairs` | `{"input": "...", "output": "..."}` |

---

## Lọc export

- `min_rating=4` — bỏ câu user chấm < 4 (chưa rate vẫn included nếu `eval_score` đủ)
- `min_eval_score=0.7` — chỉ câu evaluator pass

---

## Tiếp theo (P1/P2)

| Task | Trạng thái |
|------|------------|
| LLM-as-judge (faithfulness) | ✅ `EVAL_LLM_JUDGE_ENABLED=true` |
| Semantic reranker | ✅ `SEARCH_RERANK_ENABLED=true` (mặc định bật) |
| Rule: citations_present | ✅ Trong `evaluator.py` |
| Langfuse tracing | ✅ `LANGFUSE_TRACING_ENABLED=true` |
| Auto-promote Q&A → RAG | ✅ `FEEDBACK_AUTO_PROMOTE_MIN_RATING=5` |
| Manual promote | ✅ `POST /api/v1/admin/feedback/{trace_id}/promote` |

---

## P2 — Feedback → RAG promotion

Khi user rate ≥ `FEEDBACK_AUTO_PROMOTE_MIN_RATING` (mặc định 5), hệ thống tự động index Q&A vào `app.knowledge_documents` với `source=feedback_promoted`.

Migration `009_feedback_promotion.sql` thêm cột `promoted_to_rag`, `promoted_doc_id`.

```powershell
python scripts/db_migrate.py   # 009
```

Promote thủ công:

```http
POST /api/v1/admin/feedback/{trace_id}/promote
```
