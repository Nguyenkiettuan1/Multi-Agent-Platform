# Infrastructure: Local PostgreSQL → Cloud

> **Principle:** PostgreSQL from day one — local via Docker, then migrate to Azure Database for PostgreSQL **without changing application code**.

References:
- [LangGraph PostgresSaver](https://langchain-ai.github.io/langgraph/reference/checkpoints/#postgressaver)
- [Deploy LangGraph Production + Postgres](https://rapidclaw.dev/blog/deploy-langgraph-production-tutorial-2026)
- [ActiveWizards — Checkpointer decision matrix](https://activewizards.com/blog/langgraph-state-management-checkpointing-recovery-and-the-persistence-layer-decision/)

---

## 1. Two PostgreSQL Layers (Separate Schemas)

```mermaid
flowchart TB
    subgraph PG["PostgreSQL (single instance local, split later on cloud)"]
        subgraph APP["Schema: app — Business Data"]
            CONTRACTS[contracts]
            CLIENTS[clients]
            DOCUMENTS[documents]
        end
        subgraph PLATFORM["Schema: platform — Agent Runtime"]
            CHECKPOINTS[checkpoints<br/>LangGraph PostgresSaver]
            TASKS[task_dag]
            AUDIT[audit_log]
            SESSIONS[sessions]
        end
    end

    DB_AGENT[DB Worker] -->|sql-mcp read-only| APP
    WORKFLOW[LangGraph Engine] -->|PostgresSaver| PLATFORM
    GATEWAY[API Gateway] -->|audit write| PLATFORM
```

| Schema | Purpose | Who accesses | Notes |
|--------|----------|-------------|---------|
| `app` | Application business data | DB Worker via sql-mcp (read-only) | User data, contracts |
| `platform` | Agent runtime system | Workflow engine, Gateway | Checkpoints, audit, DAG |

**Local:** 1 PostgreSQL instance, 2 schemas.
**Cloud:** Can be split into 2 Azure PostgreSQL Flexible Servers if isolation is needed.

---

## 2. Local Development Stack

```mermaid
flowchart LR
    subgraph Docker["docker-compose (local)"]
        PG[(PostgreSQL 16<br/>:5432)]
        REDIS[(Redis 7<br/>:6379)]
        PGADMIN[pgAdmin<br/>:5050]
    end

    subgraph Dev["Developer machine"]
        GW[API Gateway :8000]
        WF[LangGraph workflow]
        MCP[sql-mcp]
        AGENTS[Agents]
    end

    GW --> WF
    WF --> PG
    WF --> REDIS
    MCP --> PG
    AGENTS --> MCP
```

### Quick start

> Step-by-step details + how to fill in `.env`: [12-LOCAL-SETUP.md](12-LOCAL-SETUP.md)

```bash
# 1. Start infrastructure (PostgreSQL + Redis + pgAdmin)
docker compose up -d

# 2. Copy env (default values match Docker — no changes needed)
copy .env.example .env

# 3. Run migrations
python scripts/db_migrate.py

# 4. Seed sample data
python scripts/seed.py
python scripts/seed_vectors.py

# 5. Verify
docker exec multiagent-postgres psql -U multiagent -d multiagent -c "SELECT code, status FROM app.contracts;"
```

---

## 3. Connection Strings

### Local (`.env`)

```env
# Business data (app schema) — DB agent queries here
DATABASE_URL=postgresql+psycopg://multiagent:multiagent@localhost:5432/multiagent?options=-csearch_path%3Dapp

# Platform runtime (checkpoints, audit) — LangGraph PostgresSaver
PLATFORM_DATABASE_URL=postgresql://multiagent:multiagent@localhost:5432/multiagent?options=-csearch_path%3Dplatform

# Session cache
REDIS_URL=redis://localhost:6379/0
```

### Cloud (Azure — same code, different URLs)

```env
DATABASE_URL=postgresql+psycopg://user@server.postgres.database.azure.com:5432/multiagent?sslmode=require&options=-csearch_path%3Dapp
PLATFORM_DATABASE_URL=postgresql://user@server.postgres.database.azure.com:5432/multiagent?sslmode=require&options=-csearch_path%3Dplatform
REDIS_URL=rediss://:password@cache.redis.cache.windows.net:6380/0
```

**Migration rule:** Only change env vars + connection string. Do not change SQL dialect, ORM, or MCP server logic.

---

## 4. LangGraph Checkpointing (PostgreSQL)

Reference: [LangGraph checkpoint-postgres](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres)

| Environment | Checkpointer | Reason |
|-------------|--------------|-------|
| Unit test | `MemorySaver` | Zero setup |
| Local dev | `PostgresSaver` | **Same as production** — do not use SQLite |
| Production | `AsyncPostgresSaver` + pool | Horizontal scale, crash recovery |

```python
# platform/checkpointer.py
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

async def create_checkpointer() -> AsyncPostgresSaver:
    pool = AsyncConnectionPool(
        conninfo=settings.platform_database_url,
        min_size=2,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()  # create checkpoints table on first run
    return checkpointer
```

**Rule:** Use PostgresSaver in local dev from the start — avoid surprises when moving to cloud.

---

## 5. sql-mcp → PostgreSQL

The DB Worker accesses the `app` schema via a read-only role:

```sql
-- infra/database/migrations/002_roles.sql
CREATE ROLE agent_reader WITH LOGIN PASSWORD 'reader_password';
GRANT USAGE ON SCHEMA app TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA app TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT ON TABLES TO agent_reader;
```

The MCP server connects with `agent_reader` — never use a superuser.

---

## 6. Local → Cloud Migration Path

```mermaid
flowchart LR
    subgraph Phase1["Phase 1: Local"]
        D1[Docker PostgreSQL]
        D2[Docker Redis]
        D3[Agents local / Foundry dev]
    end

    subgraph Phase2["Phase 2: Staging"]
        A1[Azure PostgreSQL Flexible]
        A2[Azure Cache for Redis]
        A3[Foundry hosted agents]
    end

    subgraph Phase3["Phase 3: Production"]
        P1[Azure PostgreSQL HA]
        P2[Redis Premium]
        P3[Foundry + VNet]
        P4[API Management]
    end

    Phase1 -->|pg_dump / migrate| Phase2
    Phase2 -->|promote| Phase3
```

| Step | Local | Cloud (Azure) | Code changes |
|------|-------|---------------|--------------|
| Database | Docker Postgres 16 | Azure Database for PostgreSQL Flexible Server | Only `DATABASE_URL` |
| Cache | Docker Redis | Azure Cache for Redis | Only `REDIS_URL` |
| Checkpoints | PostgresSaver local | AsyncPostgresSaver + PgBouncer | Pool size config |
| Agents | `azd ai agent run` local | Foundry Container Apps | `azure.yaml` env |
| MCP servers | stdio local | Container App / SSE | Transport mode |
| Secrets | `.env` | Azure Key Vault | Secret provider |
| Observability | Console logs | App Insights + Langfuse | Connection string |

### Data migration

```bash
# Export local
pg_dump -h localhost -U multiagent -d multiagent -n app --data-only > app_data.sql

# Import staging
psql "postgresql://user@staging.postgres.database.azure.com/multiagent" -f app_data.sql
```

---

## 7. Docker Compose (local)

See `docker-compose.yml` at the project root.

| Service | Image | Port | Volume |
|---------|-------|------|--------|
| postgres | postgres:16-alpine | 5432 | `pgdata` |
| redis | redis:7-alpine | 6379 | `redisdata` |

---

## 8. Folder structure (infra)

```
infra/
├── azure.yaml              # Foundry / azd deploy (cloud)
├── database/
│   ├── migrations/
│   │   ├── 001_schemas.sql
│   │   ├── 002_app_tables.sql
│   │   ├── 003_platform_tables.sql
│   │   └── 004_roles.sql
│   └── README.md
└── docker/
    └── init-db.sh          # run migrations when container starts
```

---

## 9. Security (local → cloud)

| Concern | Local | Cloud |
|---------|-------|-------|
| DB credentials | `.env` (gitignored) | Key Vault + Managed Identity |
| sql-mcp access | `agent_reader` role | Same role, Azure AD auth optional |
| SSL | Optional | `sslmode=require` |
| Network | localhost only | VNet + private endpoint |
| Audit | `platform.audit_log` table | Same + App Insights export |

---

## 10. Pre-cloud Checklist

- [ ] Local runs 100% on PostgreSQL (no SQLite)
- [ ] PostgresSaver checkpointing works
- [ ] sql-mcp uses `agent_reader` role
- [ ] Migrations versioned in `infra/database/migrations/`
- [ ] Eval suite passes on local Postgres data
- [ ] `pg_dump` / restore tested
- [ ] Connection pooling configured (`min_size`, `max_size`)
- [ ] Env vars documented in `.env.example`
