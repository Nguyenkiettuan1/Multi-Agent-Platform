# Documentation index

English documentation for the Multi-Agent Platform.

## Getting started

| Document | Description |
|----------|-------------|
| [../README.md](../README.md) | Project overview & quick start |
| [../AGENTS.md](../AGENTS.md) | Agent types, MCP, contributor map |
| [12-LOCAL-SETUP.md](12-LOCAL-SETUP.md) | **Local development** — Docker, `.env`, migrate, API & UI |
| [00-PROJECT-GUIDE.md](00-PROJECT-GUIDE.md) | Layer architecture & folder responsibilities |

## Architecture & design

| Document | Description |
|----------|-------------|
| [01-ARCHITECTURE.md](01-ARCHITECTURE.md) | 3-plane design, execution topologies (direct / planned / reviewed) |
| [07-CONTEXT-ENGINEERING.md](07-CONTEXT-ENGINEERING.md) | Context isolation, token budget |
| [08-REFERENCE-REPOS.md](08-REFERENCE-REPOS.md) | Framework survey (LangGraph, CrewAI, …) |
| [10-GITHUB-ARCHITECTURE-MAP.md](10-GITHUB-ARCHITECTURE-MAP.md) | Design decisions ↔ open-source references |

## AI & agents

| Document | Description |
|----------|-------------|
| [03-AI-ENGINEERING-GUIDE.md](03-AI-ENGINEERING-GUIDE.md) | Prompting, eval, production patterns |
| [04-A2A-MCP-GUIDE.md](04-A2A-MCP-GUIDE.md) | MCP & agent-to-agent protocols |
| [05-SKILLS-SYSTEM.md](05-SKILLS-SYSTEM.md) | Skills folder layout & loading |
| [06-MODEL-TIERING.md](06-MODEL-TIERING.md) | Model tiers T0–T3, routing |
| [17-EXTERNAL-MCP.md](17-EXTERNAL-MCP.md) | **Cursor MCP vs app runtime**, OCR, fetch, GitHub |

## Data & infrastructure

| Document | Description |
|----------|-------------|
| [09-INFRASTRUCTURE.md](09-INFRASTRUCTURE.md) | PostgreSQL schemas, Azure migration |
| [13-RAG-OBSERVABILITY-GUIDE.md](13-RAG-OBSERVABILITY-GUIDE.md) | RAG ingest, embeddings, Azure Search |
| [14-AZURE-BLOB-INDEXER.md](14-AZURE-BLOB-INDEXER.md) | Blob storage indexer |
| [15-FEEDBACK-LOOP.md](15-FEEDBACK-LOOP.md) | User feedback → training export |

## Planning & UI

| Document | Description |
|----------|-------------|
| [02-ROADMAP.md](02-ROADMAP.md) | Phase 0 → production roadmap |
| [11-COMPLETION-SCHEDULE.md](11-COMPLETION-SCHEDULE.md) | Completion checklist |
| [16-REMAINING-ISSUES.md](16-REMAINING-ISSUES.md) | Known backlog |
| [FRONTEND-DESIGN-BRIEF.md](FRONTEND-DESIGN-BRIEF.md) | UI/UX spec for chat & admin |
| [../multi-agent-frontend/README.md](../multi-agent-frontend/README.md) | Frontend dev guide |

## Quick command reference

```bash
docker compose up -d
python scripts/db_migrate.py && python scripts/seed.py
python -m gateway.main
cd multi-agent-frontend && npm run dev
pytest tests/
```
