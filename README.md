# PHANLAW Multi-Agent Platform

**Nền tảng AI đa năng** — xử lý mọi loại yêu cầu (như GPT), điều phối nhiều agent chuyên biệt theo task.

> Pháp luật chỉ là **một domain agent** (`legal-agent`) trong hệ thống — không phải sản phẩm AI chuyên luật.

PostgreSQL local-first · Multi-task · A2A · MCP · Skills plug-in · Fine-tuning



## Tài liệu



| Tài liệu | Mô tả |

|----------|--------|

| [Kiến trúc v2](docs/01-ARCHITECTURE.md) | 3-Plane, agent roles, execution topologies |

| [Hạ tầng PostgreSQL](docs/09-INFRASTRUCTURE.md) | Local Docker → Azure cloud migration |

| [GitHub Reference Map](docs/10-GITHUB-ARCHITECTURE-MAP.md) | **Mỗi quyết định ↔ nguồn repo GitHub** |

| [Model Tiering](docs/06-MODEL-TIERING.md) | Phân cấp model T0–T3, routing |

| [Context Engineering](docs/07-CONTEXT-ENGINEERING.md) | Context isolation, token budget |

| [Reference Repos](docs/08-REFERENCE-REPOS.md) | Survey frameworks |

| [Roadmap](docs/02-ROADMAP.md) | Phase 0 → Production |

| [AI Engineering Guide](docs/03-AI-ENGINEERING-GUIDE.md) | Kiến thức nền |

| [A2A & MCP](docs/04-A2A-MCP-GUIDE.md) | Protocols |

| [Skills System](docs/05-SKILLS-SYSTEM.md) | Domain knowledge |



## Cấu trúc thư mục



```

multi-agent/

├── agents/                 # Agent definitions (orchestrator, db-worker, ...)

├── mcp-servers/            # MCP tool servers (sql-mcp → PostgreSQL)

├── core/                   # Runtime: registry, checkpointer
├── workflows/              # LangGraph pipeline
├── gateway/                # FastAPI API

├── skills/                 # Domain skills (markdown)

├── eval/                   # Eval cases

├── infra/

│   ├── database/migrations/  # PostgreSQL schemas (app + platform)

│   └── azure.yaml          # Cloud deploy (Phase 2+)

├── scripts/                # db_migrate.py, utilities

├── gateway/                # API gateway (planned)

├── docker-compose.yml      # PostgreSQL + Redis + pgAdmin

└── docs/

```



## Quick Start

**Hướng dẫn đầy đủ:** [docs/12-LOCAL-SETUP.md](docs/12-LOCAL-SETUP.md) — **Cách A: Docker** hoặc **Cách B: cài tay** PostgreSQL + pgAdmin.

**RAG, Azure Search, audit, dashboard:** [docs/13-RAG-OBSERVABILITY-GUIDE.md](docs/13-RAG-OBSERVABILITY-GUIDE.md)

**Feedback loop (Q&A → train):** [docs/15-FEEDBACK-LOOP.md](docs/15-FEEDBACK-LOOP.md)

**Backlog kỹ thuật:** [docs/16-REMAINING-ISSUES.md](docs/16-REMAINING-ISSUES.md)

**Frontend design brief (gửi team UI/UX):** [docs/FRONTEND-DESIGN-BRIEF.md](docs/FRONTEND-DESIGN-BRIEF.md)

```bash
# Xem docs/12-LOCAL-SETUP.md — Cách A (Docker) hoặc Cách B (cài tay)

# Cách A — Docker
docker compose up -d
# pgAdmin: http://localhost:5050  (admin@local.dev / admin)

# Python env
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env

# Database
python scripts/db_migrate.py
python scripts/seed.py
python scripts/seed_vectors.py

# (Tùy chọn) Azure AI Search
python scripts/setup_azure_search.py --upload

# Chạy API
python -m gateway.main
# Swagger: http://localhost:8000/docs
```



## Database



| Schema | Mục đích | Connection |

|--------|----------|------------|

| `app` | Dữ liệu nghiệp vụ (contracts, clients) | `DATABASE_URL` (agent_reader, read-only) |

| `platform` | Agent runtime (checkpoints, audit, DAG) | `PLATFORM_DATABASE_URL` |



**Local:** Docker PostgreSQL 16. **Cloud:** Azure Database for PostgreSQL — chỉ đổi env vars.



## Nguyên tắc thiết kế



1. **PostgreSQL từ đầu** — Local = Prod checkpointer (PostgresSaver), không SQLite.

2. **Role ≠ Model** — Triage (T0) → Planner (T2) → Worker (T1) → Reviewer → Synthesizer.

3. **Context isolation** — Subagent isolated context, shared state schema.

4. **4 execution modes** — Direct / Planned / Reviewed / Council.

5. **MCP + A2A** — Tools qua MCP, inter-agent qua A2A.

6. **GitHub-informed** — Mỗi quyết định có nguồn tham chiếu (`docs/10-GITHUB-ARCHITECTURE-MAP.md`).



## Tech Stack



| Layer | Local | Cloud (sau) |

|-------|-------|---------------|

| Database | PostgreSQL 16 (Docker) | Azure PostgreSQL Flexible |

| Cache | Redis 7 (Docker) | Azure Cache for Redis |

| `workflows/` + `core/` | Workflow engine | LangGraph PostgresSaver |

| Agents | Local / Foundry dev | Azure AI Foundry Hosted |

| Tools | MCP (stdio) | MCP (SSE/HTTP) |

| Inter-agent | A2A | A2A (Foundry RemoteA2A) |

| Observability | Console | App Insights + Langfuse |



## License



Proprietary — PHANLAW Enterprise


