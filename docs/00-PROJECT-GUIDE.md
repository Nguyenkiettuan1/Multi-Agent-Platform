# Project guide — read this first

> Goal: explain **layered architecture**, **what each folder does**, and **how requests flow**.

---

## Platform scope

The system behaves like **GPT for most requests**, plus orchestration for:

- **Planning** — split work into subtasks and assign agents
- **Database** — read-only SQL via `db-worker`
- **Research** — knowledge base + web search
- **Actions** — MCP tools (OCR, translate, merge images)
- **Domain plug-ins** — e.g. `legal-agent` (optional, not the default product)

```
User: "Explain Kubernetes"
  → general-agent

User: "How many records in the database?"
  → db-worker

User: "Find onboarding documents"
  → research-worker

User: "Read text in this invoice image" (+ upload)
  → action-worker → builtin-ocr

User: "Termination clause in employment law?"
  → legal-agent  (domain plug-in only when intent matches)
```

### Agent categories

| Type | Examples | Description |
|------|----------|-------------|
| General | `general-agent` | Q&A, writing, explanation |
| Capability | `db-worker`, `research-worker`, `action-worker` | Task-type specialists |
| Domain | `legal-agent`, *(future: finance, HR)* | Business vertical plug-ins |

Configuration: `agents/registry.yaml` — add domain = new entry + skill + handler.

---

## Compared to a traditional backend

| Traditional backend | This platform | Folder |
|--------------------|---------------|--------|
| API / Controller | Gateway | `gateway/` |
| Business orchestration | LangGraph workflow | `workflows/`, `core/` |
| Data access | MCP + SQL tools | `mcp-servers/`, `core/mcp/` |
| Entities / schema | State + migrations | `workflows/state.py`, `infra/database/` |
| Config | Settings + YAML | `config/`, `.env` |
| Business rules (docs) | Skills | `skills/` |
| Quality tests | Eval cases | `eval/` |
| Infrastructure | Docker / Azure | `infra/`, `docker-compose.yml` |
| Agent definitions | Registry + prompts | `agents/` |

**Key difference:** a classic backend calls fixed functions. Here the **control plane + LLM** choose agents and tools dynamically.

---

## Layer diagram

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: PRESENTATION                                      │
│  React UI, API clients, curl                                │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: GATEWAY                                           │
│  gateway/main.py — auth, chat, admin, streaming             │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: CONTROL PLANE                                     │
│  core/control/ — triage, guardrails, evaluator              │
│  core/planning/ — media task classification                 │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 4: ORCHESTRATION (LangGraph)                         │
│  workflows/graph.py — triage → plan → workers → eval        │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 5: AGENTS / WORKERS                                  │
│  workflows/workers/ — db, research, action, general, legal  │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 6: TOOLS (MCP)                                       │
│  core/mcp/hub.py — internal tools + external MCP stdio      │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 7: DATA                                              │
│  PostgreSQL (app + platform schemas), Redis, file uploads   │
└─────────────────────────────────────────────────────────────┘
```

---

## Folder reference

| Path | Role |
|------|------|
| `gateway/` | FastAPI entrypoint, chat stream, attachments |
| `workflows/graph.py` | LangGraph node wiring |
| `workflows/nodes/pipeline.py` | Triage, plan, execute, review, synthesize, eval |
| `workflows/planner.py` | TaskPlan from triage + media binding |
| `workflows/state.py` | `GraphState`, `SubTask`, `TriageResult` |
| `workflows/workers/` | Per-agent execution |
| `core/control/triage.py` | Intent routing |
| `core/mcp/hub.py` | Tool catalog & invoke |
| `core/mcp/internal_tools.py` | OCR, translate, image merge (in-process) |
| `core/planning/` | LLM media classifier, attachment args |
| `core/checkpointer.py` | PostgresSaver for sessions |
| `config/mcp_servers.yaml` | MCP server catalog |
| `config/media_tasks.yaml` | OCR / translate / merge tool mapping |
| `agents/registry.yaml` | Agent fleet |
| `skills/` | Markdown instructions per capability |
| `mcp-servers/` | Stdio MCP servers (SQL, search) |
| `multi-agent-frontend/` | React chat + admin |
| `infra/database/migrations/` | SQL schema versions |
| `scripts/db_migrate.py` | Apply migrations |
| `fixtures/knowledge/` | Sample RAG documents |

---

## Environment variables (summary)

| Variable | Schema / use | Used by |
|----------|--------------|---------|
| `DATABASE_URL` | `app` (read-only) | DB worker, RAG search |
| `PLATFORM_DATABASE_URL` | `platform` | Checkpointer, audit, feedback |
| `MIGRATE_DATABASE_URL` | admin | `db_migrate.py`, `seed.py` |
| `AZURE_OPENAI_*` / `OPENROUTER_API_KEY` | LLM | Triage, workers, embeddings |

Details: [12-LOCAL-SETUP.md](12-LOCAL-SETUP.md)

---

## Reading order for new contributors

1. [../README.md](../README.md) — run the stack
2. [../AGENTS.md](../AGENTS.md) — agent model
3. `workflows/state.py` — shared state types
4. `workflows/graph.py` + `workflows/nodes/pipeline.py` — pipeline
5. `core/mcp/hub.py` — tools
6. [01-ARCHITECTURE.md](01-ARCHITECTURE.md) — deep architecture
7. [17-EXTERNAL-MCP.md](17-EXTERNAL-MCP.md) — MCP integration

---

## Related docs

| Doc | Topic |
|-----|-------|
| [README.md](README.md) | Documentation index |
| [12-LOCAL-SETUP.md](12-LOCAL-SETUP.md) | Install & run |
| [01-ARCHITECTURE.md](01-ARCHITECTURE.md) | Full architecture v2 |
| [09-INFRASTRUCTURE.md](09-INFRASTRUCTURE.md) | PostgreSQL & Azure |
