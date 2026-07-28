# Hạ tầng: Local PostgreSQL → Cloud

> **Nguyên tắc:** PostgreSQL từ ngày đầu — local qua Docker, sau đó migrate lên Azure Database for PostgreSQL mà **không đổi application code**.

Tham chiếu:
- [LangGraph PostgresSaver](https://langchain-ai.github.io/langgraph/reference/checkpoints/#postgressaver)
- [Deploy LangGraph Production + Postgres](https://rapidclaw.dev/blog/deploy-langgraph-production-tutorial-2026)
- [ActiveWizards — Checkpointer decision matrix](https://activewizards.com/blog/langgraph-state-management-checkpointing-recovery-and-the-persistence-layer-decision/)

---

## 1. Hai lớp PostgreSQL (tách schema)

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

| Schema | Mục đích | Ai truy cập | Ghi chú |
|--------|----------|-------------|---------|
| `app` | Dữ liệu nghiệp vụ PHANLAW | DB Worker qua sql-mcp (read-only) | User data, contracts |
| `platform` | Runtime agent system | Workflow engine, Gateway | Checkpoints, audit, DAG |

**Local:** 1 PostgreSQL instance, 2 schemas.
**Cloud:** Có thể tách thành 2 Azure PostgreSQL Flexible Server nếu cần isolation.

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

> Chi tiết từng bước + cách điền `.env`: [12-LOCAL-SETUP.md](12-LOCAL-SETUP.md)

```bash
# 1. Start infrastructure (PostgreSQL + Redis + pgAdmin)
docker compose up -d

# 2. Copy env (giá trị mặc định khớp Docker — không cần sửa)
copy .env.example .env

# 3. Run migrations
python scripts/db_migrate.py

# 4. Seed sample data
python scripts/seed.py
python scripts/seed_vectors.py

# 5. Verify
docker exec phanlaw-postgres psql -U phanlaw -d phanlaw -c "SELECT code, status FROM app.contracts;"
```

---

## 3. Connection Strings

### Local (`.env`)

```env
# Business data (app schema) — DB agent queries here
DATABASE_URL=postgresql+psycopg://phanlaw:phanlaw@localhost:5432/phanlaw?options=-csearch_path%3Dapp

# Platform runtime (checkpoints, audit) — LangGraph PostgresSaver
PLATFORM_DATABASE_URL=postgresql://phanlaw:phanlaw@localhost:5432/phanlaw?options=-csearch_path%3Dplatform

# Session cache
REDIS_URL=redis://localhost:6379/0
```

### Cloud (Azure — same code, different URLs)

```env
DATABASE_URL=postgresql+psycopg://user@server.postgres.database.azure.com:5432/phanlaw?sslmode=require&options=-csearch_path%3Dapp
PLATFORM_DATABASE_URL=postgresql://user@server.postgres.database.azure.com:5432/phanlaw?sslmode=require&options=-csearch_path%3Dplatform
REDIS_URL=rediss://:password@cache.redis.cache.windows.net:6380/0
```

**Migration rule:** Chỉ đổi env vars + connection string. Không đổi SQL dialect, ORM, hay MCP server logic.

---

## 4. LangGraph Checkpointing (PostgreSQL)

Tham chiếu: [LangGraph checkpoint-postgres](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres)

| Environment | Checkpointer | Lý do |
|-------------|--------------|-------|
| Unit test | `MemorySaver` | Zero setup |
| Local dev | `PostgresSaver` | **Giống production** — không dùng SQLite |
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
    await checkpointer.setup()  # tạo bảng checkpoints lần đầu
    return checkpointer
```

**Quy tắc:** Local dev dùng PostgresSaver ngay từ đầu — tránh surprise khi lên cloud.

---

## 5. sql-mcp → PostgreSQL

DB Worker truy cập schema `app` qua role read-only:

```sql
-- infra/database/migrations/002_roles.sql
CREATE ROLE agent_reader WITH LOGIN PASSWORD 'reader_password';
GRANT USAGE ON SCHEMA app TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA app TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT ON TABLES TO agent_reader;
```

MCP server connect với `agent_reader` — không bao giờ dùng superuser.

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

| Bước | Local | Cloud (Azure) | Thay đổi code |
|------|-------|---------------|---------------|
| Database | Docker Postgres 16 | Azure Database for PostgreSQL Flexible Server | Chỉ `DATABASE_URL` |
| Cache | Docker Redis | Azure Cache for Redis | Chỉ `REDIS_URL` |
| Checkpoints | PostgresSaver local | AsyncPostgresSaver + PgBouncer | Pool size config |
| Agents | `azd ai agent run` local | Foundry Container Apps | `azure.yaml` env |
| MCP servers | stdio local | Container App / SSE | Transport mode |
| Secrets | `.env` | Azure Key Vault | Secret provider |
| Observability | Console logs | App Insights + Langfuse | Connection string |

### Data migration

```bash
# Export local
pg_dump -h localhost -U phanlaw -d phanlaw -n app --data-only > app_data.sql

# Import staging
psql "postgresql://user@staging.postgres.database.azure.com/phanlaw" -f app_data.sql
```

---

## 7. Docker Compose (local)

Xem `docker-compose.yml` ở root project.

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
    └── init-db.sh          # chạy migrations khi container start
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

## 10. Checklist trước khi lên cloud

- [ ] Local chạy 100% trên PostgreSQL (không SQLite)
- [ ] PostgresSaver checkpointing hoạt động
- [ ] sql-mcp dùng `agent_reader` role
- [ ] Migrations versioned trong `infra/database/migrations/`
- [ ] Eval suite pass trên local Postgres data
- [ ] `pg_dump` / restore tested
- [ ] Connection pooling configured (`min_size`, `max_size`)
- [ ] Env vars documented trong `.env.example`
