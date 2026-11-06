# Multi-Agent Platform

A **general-purpose AI orchestration platform** — like GPT for everyday Q&A, plus specialized agents for database queries, research, document tools (OCR, translate), and optional domain plug-ins (e.g. legal).

PostgreSQL-first · LangGraph pipeline · MCP tools · Skills · Chat UI

---

## Features

| Capability | Agent / module |
|------------|----------------|
| General Q&A | `general-agent` |
| PostgreSQL read-only queries | `db-worker` |
| Knowledge base + web search | `research-worker` |
| OCR, translate, image merge | `action-worker` + MCP |
| Optional domain (legal, etc.) | `legal-agent` + skills |

**Pipeline:** Triage → Plan → Workers → (Review) → (Synthesize) → Eval

---

## Repository layout

```
multi-agent/
├── gateway/              # FastAPI API (chat, admin, MCP catalog)
├── workflows/            # LangGraph: graph, planner, workers, state
├── core/                 # Control plane, MCP hub, LLM client, checkpointer
├── agents/               # Agent registry + definitions
├── mcp-servers/          # Stdio MCP servers (SQL, search, …)
├── config/               # mcp_servers.yaml, models.yaml, media_tasks.yaml
├── skills/               # Domain instructions (markdown)
├── multi-agent-frontend/ # React chat + admin UI (Vite)
├── infra/database/       # SQL migrations (app + platform schemas)
├── scripts/              # db_migrate, seed, eval
├── fixtures/             # Sample knowledge for RAG
├── docs/                 # Architecture & guides (see docs/README.md)
└── docker-compose.yml    # PostgreSQL + Redis + pgAdmin
```

---

## Quick start

**Full guide:** [docs/12-LOCAL-SETUP.md](docs/12-LOCAL-SETUP.md)

### Prerequisites

- Python **3.11+**
- Docker Desktop (recommended) or local PostgreSQL 16 + pgvector
- At least one LLM provider key (Azure OpenAI or OpenRouter)

### 1. Infrastructure (Docker)

```bash
docker compose up -d
```

| Service | Host port | Purpose |
|---------|-----------|---------|
| `multiagent-postgres` | **5434** | PostgreSQL 16 + pgvector |
| `multiagent-redis` | 6379 | Redis (optional) |
| `multiagent-pgadmin` | 5050 | pgAdmin (`admin@local.dev` / `admin`) |

### 2. Python environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
```

Set database URLs in `.env` (Docker default port **5434**):

```env
DATABASE_URL=postgresql+psycopg://agent_reader:agent_reader_local@localhost:5434/multiagent?options=-csearch_path%3Dapp
PLATFORM_DATABASE_URL=postgresql+psycopg://multiagent:multiagent@localhost:5434/multiagent?options=-csearch_path%3Dplatform
MIGRATE_DATABASE_URL=postgresql+psycopg://multiagent:multiagent@localhost:5434/multiagent
```

Add **Azure OpenAI** or **OpenRouter** keys (see [Local Setup](docs/12-LOCAL-SETUP.md#llm-providers)).

### 3. Database

```bash
python scripts/db_migrate.py
python scripts/seed.py
python scripts/seed_vectors.py   # requires embedding provider
```

### 4. Run API

```bash
python -m gateway.main
```

| URL | Purpose |
|-----|---------|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health | Health check |
| `POST /api/v1/chat` | Chat (sync) |
| `POST /api/v1/chat/stream` | Chat (SSE) |

**Example:**

```bash
# Needs credentials: API_KEY set in .env + X-API-Key header (or a signed-in session cookie, see docs/12-LOCAL-SETUP.md)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message": "Hello"}'
```

### 5. Frontend (optional)

```bash
cd multi-agent-frontend
npm install
npm run dev
```

Open http://localhost:5173 — proxies API to `http://localhost:8000`.

---

## Database schemas

| Schema | Purpose | Connection |
|--------|---------|------------|
| `app` | Business data (contracts, clients, knowledge) | `DATABASE_URL` (`agent_reader`, read-only) |
| `platform` | LangGraph checkpoints, audit, feedback | `PLATFORM_DATABASE_URL` |

Migrations: `python scripts/db_migrate.py` only (not Docker initdb).

---

## MCP & tools

Runtime catalog: `config/mcp_servers.yaml` + `GET /api/v1/mcp/catalog`

| Server | Type | Examples |
|--------|------|----------|
| `builtin-ocr` | internal | Image OCR (Tesseract → vision LLM) |
| `builtin-translate` | internal | Text translation |
| `builtin-image` | internal | Merge images |
| `sql-server` | internal | Read-only SQL |
| `search-server` | internal | RAG + web search |
| `paddleocr` | external MCP | High-accuracy OCR (optional) |

**Cursor IDE** uses `.cursor/mcp.json` (separate from app runtime). See [docs/17-EXTERNAL-MCP.md](docs/17-EXTERNAL-MCP.md).

---

## Design principles

1. **PostgreSQL from day one** — LangGraph `PostgresSaver`, no SQLite in production paths.
2. **Role ≠ model** — Triage (cheap) → Planner → Workers → Reviewer → Synthesizer.
3. **Context isolation** — Worker results merged in state; subagents do not leak raw context.
4. **Tools via MCP** — LLM routes; Python/MCP executes (OCR, SQL, search).
5. **Plug-in domains** — New agent = `agents/registry.yaml` + skill + handler; core workflow unchanged.

---

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/README.md](docs/README.md) | **Documentation index** |
| [docs/12-LOCAL-SETUP.md](docs/12-LOCAL-SETUP.md) | Local dev (Docker / native Postgres) |
| [docs/00-PROJECT-GUIDE.md](docs/00-PROJECT-GUIDE.md) | Layer map & folder roles |
| [docs/01-ARCHITECTURE.md](docs/01-ARCHITECTURE.md) | 3-plane architecture |
| [docs/17-EXTERNAL-MCP.md](docs/17-EXTERNAL-MCP.md) | MCP for Cursor vs app |
| [AGENTS.md](AGENTS.md) | Agent types & MS course mapping |

---

## Tech stack

| Layer | Local | Cloud (future) |
|-------|-------|----------------|
| Database | PostgreSQL 16 + pgvector | Azure PostgreSQL |
| Workflow | LangGraph + PostgresSaver | Same |
| API | FastAPI | Container / App Service |
| LLM | Azure OpenAI / OpenRouter | Azure AI Foundry |
| Tools | MCP stdio + internal Python | MCP HTTP/SSE |
| UI | React + Vite | Static / CDN |

---

## License

Private — personal project.
