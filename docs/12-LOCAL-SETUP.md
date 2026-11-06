# Local development setup

Complete guide for new developers: choose **Docker** (recommended) or **native PostgreSQL**, then configure Python and run the API.

---

## Choose your setup

| | **Option A — Docker** (recommended) | **Option B — Native Postgres** |
|---|-----------------------------------|--------------------------------|
| Difficulty | Easy — one command | Medium — install extensions manually |
| PostgreSQL | `pgvector/pgvector:pg16` container | PostgreSQL 16+ + pgvector on host |
| pgAdmin | Container on port `5050` | Desktop app or Docker pgAdmin only |
| Redis | Container `6379` | Optional Docker Redis |
| DB host port | **`5434`** (project default) | Usually `5432` |

> The Python API **always runs on the host**, not inside Docker. Only DB / Redis / pgAdmin use containers (Option A).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Infrastructure (Docker OR native)                          │
│  ├── PostgreSQL 16 + pgvector   :5434 (Docker) / :5432      │
│  ├── Redis (optional)           :6379                       │
│  └── pgAdmin                    :5050                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ localhost
┌───────────────────────────▼─────────────────────────────────┐
│  Host — Python                                                │
│  ├── .env                                                     │
│  ├── python scripts/db_migrate.py                             │
│  ├── python -m gateway.main        → http://localhost:8000    │
│  └── (optional) multi-agent-frontend → http://localhost:5173  │
└───────────────────────────────────────────────────────────────┘
```

### Port reference

| Port | Service |
|------|---------|
| `5434` | **This project** — Docker Postgres (`multiagent-postgres`) |
| `5432` | Native PostgreSQL on Windows |
| `5050` | pgAdmin web UI |
| `6379` | Redis |
| `8000` | API gateway |
| `5173` | Vite frontend dev server |

---

## Common steps (both options)

### 1. Python environment

```powershell
cd path/to/multi-agent

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

Requires **Python 3.11+**.

### 2. Environment file

```powershell
copy .env.example .env
```

#### Required database variables

| Variable | Purpose | DB user |
|----------|---------|---------|
| `DATABASE_URL` | RAG + DB worker (read-only) | `agent_reader` |
| `PLATFORM_DATABASE_URL` | Checkpoints, audit, feedback | `multiagent` |
| `MIGRATE_DATABASE_URL` | Migrations & seed | `multiagent` |

Use driver **`postgresql+psycopg://`** (psycopg v3). Do not use bare `postgresql://`.

**Docker default (port 5434):**

```env
DATABASE_URL=postgresql+psycopg://agent_reader:agent_reader_local@localhost:5434/multiagent?options=-csearch_path%3Dapp
PLATFORM_DATABASE_URL=postgresql+psycopg://multiagent:multiagent@localhost:5434/multiagent?options=-csearch_path%3Dplatform
MIGRATE_DATABASE_URL=postgresql+psycopg://multiagent:multiagent@localhost:5434/multiagent
REDIS_URL=redis://localhost:6379/0
```

#### LLM providers

Configure **at least one**:

**Azure OpenAI:**

```env
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<key>
EMBEDDING_PROVIDER=azure
EMBEDDING_DEPLOYMENT=text-embedding-ada-002
EMBEDDING_DIMENSIONS=1536
```

**OpenRouter (quick dev):**

```env
OPENROUTER_API_KEY=sk-or-v1-...
EMBEDDING_PROVIDER=openrouter
EMBEDDING_MODEL=openai/text-embedding-ada-002
```

#### Optional

```env
TAVILY_API_KEY=...              # Web search citations
AZURE_SEARCH_ENDPOINT=...       # Optional cloud search index
API_KEY=                        # Optional X-API-Key for scripts/curl. Empty = that path is off (NOT "auth disabled")
```

#### Authentication (required)

Every API route except `/health`, `POST /api/v1/auth/login` and `POST /api/v1/auth/logout` needs either a signed-in session or a valid `X-API-Key`. An empty `API_KEY` no longer opens the API.

`AUTH_SECRET_KEY` signs the session cookie. The gateway **refuses to start** without it. Generate one and put it in `.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```env
AUTH_SECRET_KEY=<paste the generated value>
# AUTH_SESSION_TTL_HOURS=12     # 1..168
# AUTH_COOKIE_SECURE=true       # see "Secure cookie" below
```

Changing `AUTH_SECRET_KEY` later signs everyone out at once.

### 3. Migrate & seed

```powershell
python scripts/db_migrate.py
python scripts/seed.py
python scripts/seed_vectors.py   # needs embedding provider
```

> Run migrations **only** via `db_migrate.py`. Docker does not mount SQL into `initdb` (avoids duplicate runs).

Expected output:

```
Done — 10 migrations applied.
Seeded 3 clients and 3 contracts...
Seeded 4 knowledge documents.
```

### 4. Create the first admin

Migration 010 creates the user tables but no login account. Create the first admin once:

```powershell
python scripts/create_admin.py --email you@example.com --name "Your Name"
```

The script prompts for the password twice (12-128 characters, not equal to the email). There is deliberately no password argument: it would end up in shell history and the process list. For non-interactive provisioning set `CREATE_ADMIN_PASSWORD` in that shell only (it is never echoed):

```powershell
$env:CREATE_ADMIN_PASSWORD = "<password>"; python scripts/create_admin.py --email you@example.com; Remove-Item Env:CREATE_ADMIN_PASSWORD
```

This admin does **not** have to change the password on first sign-in (you chose it). Admins created later from the UI or `POST /api/v1/admin/users` do. If you provision the first admin on behalf of someone else, that person should change the password after their first sign-in (Settings). Email must look like `name@domain.tld` (or `name@localhost`), at most 320 characters; the display name at most 200.

| Exit code | Meaning |
|-----------|---------|
| `0` | Admin created (prints the email and user id, never the password) |
| `1` | Refused: email already exists (nothing is changed), password violates the policy, the two entries differ, or the email is blank |
| `2` | Usage error (e.g. `--email` missing) |

### 5. Run API

```powershell
python -m gateway.main
```

| URL | Purpose |
|-----|----------|
| http://localhost:8000/docs | Swagger |
| http://localhost:8000/health | Health |
| http://localhost:8000/api/v1/admin/overview | Admin metrics (admin only) |

**Test chat.** Pick one of two ways to authenticate.

*With an API key*: set `API_KEY=<some long random value>` in `.env` and restart the gateway, then set the same value in the shell you run curl from. The key acts as an admin and needs no CSRF header:

```powershell
$env:API_KEY = '<value>'
curl -X POST http://localhost:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -H "X-API-Key: $env:API_KEY" `
  -d '{"message": "Hello"}'
```

*With a session cookie* (what the browser does). Sign in once, keep the cookie in a jar, then reuse it. Every `POST`/`PUT`/`PATCH`/`DELETE` must also send `X-Requested-With: XMLHttpRequest`, login included. Put the credentials in a temporary file instead of on the command line (they would land in shell history), and delete the file and the cookie jar when done:

```powershell
'{"email": "you@example.com", "password": "<password>"}' | Set-Content $env:TEMP\login.json
curl -c $env:TEMP\ma-cookies.txt -X POST http://localhost:8000/api/v1/auth/login `
  -H "Content-Type: application/json" -H "X-Requested-With: XMLHttpRequest" `
  -d "@$env:TEMP\login.json"
Remove-Item $env:TEMP\login.json

curl -b $env:TEMP\ma-cookies.txt -X POST http://localhost:8000/api/v1/chat `
  -H "Content-Type: application/json" -H "X-Requested-With: XMLHttpRequest" `
  -d '{"message": "Hello"}'

Remove-Item $env:TEMP\ma-cookies.txt
```

Without a key or cookie the API answers `401`. A cookie session whose account must change its password gets `403 Password change required` until it does (UI: Settings, or `POST /api/v1/auth/password`).

#### Sign-in behaviour to know about

- **Lock-out (by design):** 5 failed sign-ins for one email within 15 minutes, or 20 from one IP, return `429` with a `Retry-After` header. Wrong email, wrong password and a disabled account all return the same `401 Invalid email or password`, so the response does not reveal which accounts exist. Wait for `Retry-After` to pass; there is no unlock command.
- **Secure cookie:** the session cookie is `Secure` by default. Browsers drop it on plain `http://` except `localhost`, so opening the app by LAN IP shows a "successful" sign-in that is still `401` on the next call. For that case only, set `AUTH_COOKIE_SECURE=false` in `.env`; the gateway logs a warning when it is off and `APP_ENV` is not `local`. Keep it `true` behind HTTPS.
- **Behind a reverse proxy:** the per-IP limit sees the proxy's address unless uvicorn trusts the forwarded headers. `python -m gateway.main` calls `uvicorn.run()`, so command-line flags cannot be passed; uvicorn already has proxy headers on, and the trusted proxies come from the `FORWARDED_ALLOW_IPS` environment variable (default `127.0.0.1`). Set `$env:FORWARDED_ALLOW_IPS = '<proxy IP>'` before starting the gateway; otherwise every user shares the proxy's IP bucket.

### 6. Frontend (optional)

```powershell
cd multi-agent-frontend
npm install
npm run dev
```

Open http://localhost:5173/login — Vite proxies `/api` to port `8000`. Sign in with the admin from step 4.

### 7. Verification checklist

- [ ] `docker compose ps` → `multiagent-postgres` **healthy**
- [ ] `python scripts/db_migrate.py` → `Done — 10 migrations`
- [ ] `GET /health` → `"status": "ok"`
- [ ] `GET /api/v1/models` → `llm_enabled: true` (if LLM configured)
- [ ] `python scripts/create_admin.py ...` → `Created admin ...`, then sign-in at `/login` works
- [ ] `POST /api/v1/chat` without key or cookie → `401`; with `X-API-Key` or a session → a response
- [ ] Image upload in UI triggers OCR (see gateway logs: `Plan media task kind=ocr`)

---

## Option A — Docker (recommended)

### Start stack

```powershell
docker compose up -d
docker compose ps
```

| Container | Host port |
|-----------|-----------|
| `multiagent-postgres` | **5434** |
| `multiagent-redis` | 6379 |
| `multiagent-pgadmin` | 5050 |

### pgAdmin

1. Open http://localhost:5050
2. Login: `admin@local.dev` / `admin` (pgAdmin UI — not the DB user)
3. Browse: `Databases → multiagent → Schemas → app → Tables`

Inside Docker network, Postgres host is **`postgres`**, not `localhost`.

### PostgreSQL users (created by migration)

| User | Password | Access |
|------|----------|--------|
| `multiagent` | `multiagent` | Admin — migrate, seed |
| `agent_reader` | `agent_reader_local` | SELECT on schema `app` only |

### Useful Docker commands

```powershell
docker compose logs -f postgres
docker exec -it multiagent-postgres psql -U multiagent -d multiagent
docker compose down
docker compose down -v    # WARNING: deletes all DB data
```

### Port conflict

Project uses host port **5434** to avoid clashing with native Postgres (`5432`). To change: edit `docker-compose.yml` ports and all three `.env` URLs.

---

## Option B — Native PostgreSQL

1. Install PostgreSQL 16+ and **pgvector** extension.
2. Create database and user:

```sql
CREATE USER multiagent WITH PASSWORD 'multiagent' CREATEDB;
CREATE DATABASE multiagent OWNER multiagent;
```

3. Set `.env` URLs to port `5432` (or your port).
4. Optionally run only Redis via Docker: `docker compose up -d redis`
5. Run migrate + seed as in [Common steps](#common-steps-both-options).

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `connection refused` on migrate | Start Docker: `docker compose up -d`; check port in `.env` |
| `No module named 'psycopg2'` | Use `postgresql+psycopg://` in all DB URLs |
| `role "agent_reader" does not exist` | Run `python scripts/db_migrate.py` |
| `extension "vector" does not exist` | Use Docker image `pgvector/pgvector:pg16` or install pgvector |
| `llm_enabled: false` | Add Azure or OpenRouter keys to `.env` |
| LangGraph serde warnings | Harmless for now; register types in checkpointer later |
| OCR returns empty | Ensure image uploaded; check logs for `OCR args file=True` |

### Reset Docker database

```powershell
docker compose stop postgres
docker compose rm -sf postgres
docker volume rm multi-agent_pgdata
docker compose up -d postgres
python scripts/db_migrate.py
python scripts/seed.py
python scripts/seed_vectors.py
```

---

## Quick copy-paste (Docker full stack)

```powershell
cd path/to/multi-agent
copy .env.example .env
docker compose up -d
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/db_migrate.py
python scripts/seed.py
python scripts/seed_vectors.py
python -m gateway.main
```

API: http://localhost:8000/docs · pgAdmin: http://localhost:5050

---

## Related docs

| Doc | Topic |
|-----|-------|
| [13-RAG-OBSERVABILITY-GUIDE.md](13-RAG-OBSERVABILITY-GUIDE.md) | RAG, embeddings, Azure Search |
| [17-EXTERNAL-MCP.md](17-EXTERNAL-MCP.md) | MCP tools for chat & Cursor |
| [15-FEEDBACK-LOOP.md](15-FEEDBACK-LOOP.md) | Feedback export |
| [../multi-agent-frontend/README.md](../multi-agent-frontend/README.md) | React UI |
