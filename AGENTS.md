# PHANLAW Multi-Agent — AGENTS.md

> Mapping kiến trúc project ↔ [Microsoft AI Agents for Beginners](https://github.com/microsoft/ai-agents-for-beginners)

## Agent types

| Type | Folder | Example |
|------|--------|---------|
| General | `agents/` + `skills/general-assistant/` | GPT-like Q&A |
| Capability | `agents/` + `skills/database-query/` | db-worker, research-worker |
| Domain plug-in | `agents/` + `skills/legal-research/` | legal-agent (one of many) |

Thêm domain mới: registry.yaml + skill + handler — không sửa core workflow.

```
User message
    → Gateway (API)
    → Planner (chia subtasks + assigned_agent)
    → Workers chuyên biệt (db-worker, research-worker, ...)
    → Reviewer (nếu cần)
    → Synthesizer (tổng hợp response)
```

## Lesson mapping

| Microsoft Lesson | PHANLAW folder |
|------------------|----------------|
| 07 Planning Design | `workflows/planner.py`, `workflows/state.py` |
| 08 Multi-Agent | `workflows/graph.py`, `workflows/workers/` |
| 04 Tool Use | `mcp-servers/` |
| 11 MCP / A2A | `mcp-servers/`, `agents/registry.yaml` (A2A Phase 1) |
| 12 Context Engineering | `workflows/state.py` (isolated worker results) |
| Skills | `skills/` (giống `.agents/skills` trong MS repo) |
| 10 Production | `gateway/`, `core/checkpointer.py` |

## Chạy local

```bash
docker compose up -d
copy .env.example .env
pip install -r requirements.txt
python scripts/db_migrate.py
python scripts/seed.py
python -m gateway.main
# POST http://localhost:8000/api/v1/chat  {"message": "Có bao nhiêu hợp đồng active?"}
```
