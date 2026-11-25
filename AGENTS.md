# Multi-Agent Platform — AGENTS.md

> Architecture map aligned with [Microsoft AI Agents for Beginners](https://github.com/microsoft/ai-agents-for-beginners)

## Request flow

```
User message (+ optional attachments)
  → Gateway (FastAPI)
  → Triage (intent + security)
  → Planner (subtasks + assigned_agent + tool binding for media)
  → Workers (db, research, action, general, legal, …)
  → Reviewer (optional)
  → Synthesizer (optional)
  → Eval → response
```

## Agent types

| Type | Location | Example |
|------|----------|---------|
| General | `agents/` + `skills/general-assistant/` | GPT-like Q&A |
| Capability | `agents/` + `skills/database-query/` | `db-worker`, `research-worker`, `action-worker` |
| Domain plug-in | `agents/` + `skills/legal-research/` | `legal-agent` (one of many) |

**Add a new domain:** `agents/registry.yaml` + skill under `skills/` + worker handler in `workflows/workers/` — do not fork core graph logic.

## Registry

`agents/registry.yaml` — fleet list, models, allowed MCP servers per agent.

| Agent ID | Role |
|----------|------|
| `general-agent` | Default Q&A |
| `db-worker` | SQL read-only |
| `research-worker` | RAG + web search |
| `action-worker` | MCP tools (OCR, translate, images) |
| `legal-agent` | Legal domain (optional) |
| `code-worker` | Disabled by default |

## Microsoft course mapping

| Lesson | Project location |
|--------|------------------|
| 07 Planning | `workflows/planner.py`, `workflows/state.py` |
| 08 Multi-Agent | `workflows/graph.py`, `workflows/workers/` |
| 04 Tool Use | `mcp-servers/`, `core/mcp/internal_tools.py` |
| 11 MCP / A2A | `config/mcp_servers.yaml`, `core/mcp/hub.py` |
| 12 Context Engineering | `workflows/state.py` (isolated worker results) |
| Skills | `skills/` |
| 10 Production | `gateway/`, `core/checkpointer.py` |

## MCP vs skills

| Mechanism | Purpose |
|-----------|---------|
| **Skills** | Markdown instructions loaded into worker prompts |
| **MCP tools** | Executable functions (SQL, OCR, search) via `ToolHub` |
| **Cursor `mcp.json`** | IDE-only; not used by chat runtime |

App runtime reads `config/mcp_servers.yaml`. Action worker tools are filtered by `agents/registry.yaml`.

## Media / OCR path

1. `gateway/main.py` — `materialize_attachments()` → `data/chat-uploads/`
2. `core/control/triage.py` — image attachment → `ACTION`
3. `core/planning/llm_media_classifier.py` — LLM classifies `ocr` / `translate` / `merge_images`
4. `workflows/planner.py` — `SubTask` with `tool_id` + `file_path`
5. `workflows/workers/action_worker.py` — `hub.call_tool()`
6. `core/mcp/internal_tools.py` — `_ocr_extract` (Tesseract → vision LLM)

Config: `config/media_tasks.yaml` (descriptions + tool mapping, no hardcoded keywords).

## Local run

```bash
docker compose up -d
cp .env.example .env          # Windows: copy .env.example .env
pip install -r requirements.txt
python scripts/db_migrate.py
python scripts/seed.py
python -m gateway.main
```

```bash
# Chat
# Needs credentials: API_KEY set in .env + X-API-Key header (or a signed-in session cookie, see docs/12-LOCAL-SETUP.md)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message": "How many active contracts?"}'

# With image OCR (via frontend or attachments in JSON)
```

Frontend: `cd multi-agent-frontend && npm run dev` → http://localhost:5173

## Key files for contributors

| Task | Files |
|------|-------|
| Change routing | `core/control/triage.py`, `workflows/planner.py` |
| Add MCP server | `config/mcp_servers.yaml`, optional `mcp-servers/` |
| Add agent | `agents/registry.yaml`, `workflows/workers/handlers.py` |
| Graph nodes | `workflows/nodes/pipeline.py`, `workflows/graph.py` |
| State schema | `workflows/state.py` |

## Tests

```bash
pytest tests/test_control_plane.py tests/test_ocr_routing.py tests/test_mcp_hub.py
```
