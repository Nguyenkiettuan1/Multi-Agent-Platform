# Hướng dẫn chạy local — Docker hoặc cài tay

> Tài liệu đầy đủ cho dev mới: chọn **1 trong 2 cách** cài PostgreSQL, rồi làm phần chung (Python + API).

---

## Chọn cách cài đặt

| | **Cách A — Docker** (khuyến nghị) | **Cách B — Cài tay** |
|---|-----------------------------------|----------------------|
| Độ khó | Dễ — 1 lệnh | Trung bình — cài từng phần |
| PostgreSQL | Container `pgvector/pg16` | Cài PostgreSQL 16+ + extension pgvector |
| pgAdmin | Container port `5050` | Tải pgAdmin riêng |
| Redis | Container port `6379` | Tùy chọn (hoặc chỉ chạy Redis bằng Docker) |
| Port DB (host) | **`5434`** (mặc định project) | Tùy bạn (thường `5432`) |
| Phù hợp | Hầu hết dev | Máy không cài được Docker / đã có Postgres sẵn |

**Lưu ý:** API Python **luôn chạy trên máy** (không trong Docker). Chỉ DB/Redis/pgAdmin chạy Docker hoặc cài native.

---

## Kiến trúc chung

```
┌─────────────────────────────────────────────────────────────┐
│  Hạ tần (Docker HOẶC cài tay)                               │
│  ├── PostgreSQL 16 + pgvector  :5434 (Docker) / :5432 (native)│
│  ├── Redis (tùy chọn)          :6379                        │
│  └── pgAdmin (GUI xem DB)      :5050 hoặc app desktop       │
└───────────────────────────┬─────────────────────────────────┘
                            │ localhost
┌───────────────────────────▼─────────────────────────────────┐
│  Máy bạn — Python                                             │
│  ├── .env                                                     │
│  ├── python scripts/db_migrate.py                             │
│  ├── python -m gateway.main        → http://localhost:8000    │
│  └── (tùy chọn) Azure OpenAI / Azure Search / Tavily keys     │
└───────────────────────────────────────────────────────────────┘
```

### Bảng port (tránh nhầm)

| Port | Thường là gì |
|------|----------------|
| `5432` | PostgreSQL cài native trên Windows |
| `5433` | Container Postgres cũ (vd. `postgres_db`) |
| **`5434`** | **PHANLAW Docker** (`phanlaw-postgres`) |
| `5050` | pgAdmin web UI |
| `6379` | Redis |
| `8000` | API Gateway |

---

# PHẦN CHUNG — Làm sau khi DB sẵn sàng (cả 2 cách)

## 1. Python environment

```powershell
cd d:\PHANLAW\multi-agent

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Yêu cầu: **Python 3.11+** (khuyến nghị 3.11 hoặc 3.12).

---

## 2. File `.env`

```powershell
copy .env.example .env
```

### 2.1 Biến DB bắt buộc

| Biến | Mục đích | User |
|------|----------|------|
| `DATABASE_URL` | RAG search + DB worker (read-only) | `agent_reader` |
| `PLATFORM_DATABASE_URL` | Feedback, audit, LangGraph checkpoint | `phanlaw` (admin) |
| `MIGRATE_DATABASE_URL` | Chạy migration / seed | `phanlaw` (admin) |
| `REDIS_URL` | Cache (tùy chọn hiện tại) | — |

> **Quan trọng:** Cả 3 URL phải dùng driver `postgresql+psycopg://` (project chỉ cài `psycopg` v3, không dùng `postgresql://`).

**Docker mặc định (port `5434`):**

```env
DATABASE_URL=postgresql+psycopg://agent_reader:agent_reader_local@localhost:5434/phanlaw?options=-csearch_path%3Dapp
PLATFORM_DATABASE_URL=postgresql+psycopg://phanlaw:phanlaw@localhost:5434/phanlaw?options=-csearch_path%3Dplatform
MIGRATE_DATABASE_URL=postgresql+psycopg://phanlaw:phanlaw@localhost:5434/phanlaw
REDIS_URL=redis://localhost:6379/0
```

**Nếu Postgres cài tay dùng port khác** (vd. `5432`):

```env
# Đổi 5434 → port của bạn trong cả 3 URL
MIGRATE_DATABASE_URL=postgresql+psycopg://phanlaw:phanlaw@localhost:5432/phanlaw
```

### 2.2 LLM — chọn ít nhất 1 provider

**Azure OpenAI (production):**

```env
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<key>

EMBEDDING_PROVIDER=azure
EMBEDDING_DEPLOYMENT=text-embedding-ada-002
EMBEDDING_DIMENSIONS=1536
```

**OpenRouter (dev nhanh — 1 key cho nhiều model):**

```env
OPENROUTER_API_KEY=sk-or-v1-...
EMBEDDING_PROVIDER=openrouter
EMBEDDING_MODEL=openai/text-embedding-ada-002
```

### 2.3 Tùy chọn

```env
TAVILY_API_KEY=tvly-...                    # Web search [W1] citations
AZURE_SEARCH_ENDPOINT=https://....search.windows.net
AZURE_SEARCH_API_KEY=...
AZURE_SEARCH_INDEX_NAME=knowledge-index
API_KEY=                                   # Để trống = tắt auth khi dev
```

---

## 3. Migration & seed

```powershell
python scripts/db_migrate.py    # Tạo schema, tables, pgvector, role agent_reader
python scripts/seed.py          # Dữ liệu nghiệp vụ mẫu (app schema)
python scripts/seed_vectors.py  # Tài liệu RAG mẫu + embedding (cần LLM key)
```

> `db_migrate.py` là cách **duy nhất** chạy migration. Docker **không** mount SQL vào `initdb` (tránh chạy đôi / lỗi `already exists`).

Kết quả mong đợi:

```
Done — 9 migrations applied.
Seeded 3 clients and 3 contracts...
Seeded 4 knowledge documents.
```

---

## 4. Azure AI Search (tùy chọn)

Không bắt buộc — local dùng pgvector trong PostgreSQL.

```powershell
# Điền AZURE_SEARCH_* trong .env trước
python scripts/setup_azure_search.py --upload
```

Script tự tạo index `knowledge-index` (6 fields) + upload từ PostgreSQL.

---

## 5. Chạy API

```powershell
python -m gateway.main
```

| URL | Mục đích |
|-----|----------|
| http://localhost:8000/docs | Swagger — test API |
| http://localhost:8000/health | Health check |
| http://localhost:8000/api/v1/admin/overview | Admin dashboard data |

**Test chat:**

```powershell
curl -X POST http://localhost:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -d "{\"message\": \"Xin chào\"}"
```

---

## 6. Checklist xác nhận

- [ ] `docker compose ps` → `phanlaw-postgres` **healthy**
- [ ] `python scripts/db_migrate.py` → `Done — 9 migrations`
- [ ] `python scripts/seed_vectors.py` → `Seeded 4 knowledge documents`
- [ ] `GET /health` → `"status": "ok"`
- [ ] `GET /api/v1/models` → `llm_enabled: true` (nếu đã điền LLM key)
- [ ] `POST /api/v1/chat` → có `response`

---

# CÁCH A — Docker (khuyến nghị)

## A1. Cài Docker Desktop

- Tải: https://www.docker.com/products/docker-desktop/
- Mở Docker Desktop → đợi **Engine running** (icon xanh)

## A2. Khởi động stack

```powershell
cd d:\PHANLAW\multi-agent
docker compose up -d
docker compose ps
```

Phải thấy 3 container `running`:

| Container | Port (host) | Mục đích |
|-----------|-------------|----------|
| `phanlaw-postgres` | **`5434`** | PostgreSQL + pgvector |
| `phanlaw-redis` | `6379` | Redis |
| `phanlaw-pgadmin` | `5050` | pgAdmin web UI |

## A3. `.env`

Copy `.env.example` → `.env`. **Giữ nguyên** URL DB nếu dùng port `5434` (mặc định).

### 3 user PostgreSQL (tạo bởi migration)

| User | Password | Quyền |
|------|----------|-------|
| `phanlaw` | `phanlaw` | Admin — migrate, seed, pgAdmin |
| `agent_reader` | `agent_reader_local` | SELECT only trên schema `app` |
| — | — | Schema `platform`: chỉ `phanlaw` |

## A4. pgAdmin qua Docker

1. Mở http://localhost:5050
2. **Đăng nhập web pgAdmin** (không phải user DB):

   | | |
   |---|---|
   | Email | `admin@local.dev` |
   | Password | `admin` |

3. Click server **PHANLAW Local** bên trái (cấu hình sẵn trong `infra/pgadmin/servers.json`)
4. Duyệt: `Databases → phanlaw → Schemas → app → Tables`

> **Hai tài khoản khác nhau:** `admin@local.dev` = login web pgAdmin; `phanlaw` = user PostgreSQL.

### pgAdmin không thấy server / lỗi kết nối

| Lỗi | Nguyên nhân | Cách xử lý |
|-----|-------------|------------|
| `Name does not resolve` | Container `phanlaw-postgres` chưa chạy | `docker compose ps` → start postgres |
| `password authentication failed for user "admin@local.dev"` | Nhầm user DB | Dùng user **`phanlaw`**, password **`phanlaw`** |
| Sidebar trống, không có server | `servers.json` lỗi hoặc volume cũ | Reset pgAdmin volume (xem bên dưới) |

**Reset pgAdmin (khi cấu hình server bị hỏng):**

```powershell
docker compose rm -sf pgadmin
docker volume rm multi-agent_pgadmin_data
docker compose up -d pgadmin
```

**Thêm server thủ công** (nếu cần): Host = `postgres`, Port = `5432`, DB = `phanlaw`, User = `phanlaw`, Password = `phanlaw`.

> Trong pgAdmin Docker: host là `postgres` (tên service Docker network), **không** phải `localhost`.

## A5. Tiếp tục phần chung

→ Mục **3. Migration & seed** trở đi ở trên.

### Lệnh Docker hữu ích

```powershell
docker compose logs -f postgres          # Xem log DB
docker exec -it phanlaw-postgres psql -U phanlaw -d phanlaw   # Vào psql
docker compose down                      # Dừng
docker compose down -v                   # Dừng + XÓA data (reset hoàn toàn)
```

### ⚠️ Xung đột port

Project map Postgres ra **`5434`** để tránh:

- `5432` — PostgreSQL native (pgAdmin/EDB cài trên Windows)
- `5433` — container Postgres cũ (vd. `postgres_db`)

Kiểm tra port đang dùng:

```powershell
docker ps --format "table {{.Names}}\t{{.Ports}}"
netstat -ano | findstr ":5434"
```

**Nếu `5434` cũng bị chiếm:** sửa `docker-compose.yml` (`"5435:5432"`) và đổi cả 3 URL trong `.env` sang port mới.

Project **phanlaw** cần image `pgvector/pgvector:pg16` — container Postgres thường **không có** pgvector.

---

# CÁCH B — Cài tay (PostgreSQL + pgAdmin native)

Dành cho khi không dùng Docker hoặc muốn cài trực tiếp trên Windows.

## B1. Cài PostgreSQL 16+

1. Tải: https://www.postgresql.org/download/windows/ (EDB installer)
2. Cài đặt:
   - Port: `5432` (hoặc ghi nhớ port bạn chọn)
   - Superuser password: đặt password admin (vd. `postgres`)
   - Locale: default

3. **Cài extension pgvector** (bắt buộc cho RAG):

   **Option 1 — prebuilt Windows (nhanh):**
   - Tải release PG16/17: https://github.com/andreiramani/pgvector_pgsql_windows/releases
   - Copy `vector.dll` → `PostgreSQL\XX\lib\`
   - Copy `vector.control`, `vector--*.sql` → `PostgreSQL\XX\share\extension\`
   - Restart service PostgreSQL

   **Option 2 — build từ source:** https://github.com/pgvector/pgvector#installation-notes---windows

   **Option 3 — hybrid (khuyến nghị nếu pgvector khó cài):**
   ```powershell
   docker compose up -d postgres redis pgadmin
   ```
   Chỉ chạy hạ tầng Docker, API vẫn chạy trên máy.

## B2. Tạo database và user

Mở **pgAdmin** hoặc `psql` với superuser:

```sql
CREATE USER phanlaw WITH PASSWORD 'phanlaw' CREATEDB;
CREATE DATABASE phanlaw OWNER phanlaw;
```

> Schema `app` / `platform`, extension `vector`, role `agent_reader` được tạo bởi `python scripts/db_migrate.py`.

## B3. Cài pgAdmin (GUI)

1. Tải: https://www.pgadmin.org/download/pgadmin-4-windows/
2. **Register → Server:**

| Tab | Giá trị |
|-----|---------|
| Name | `PHANLAW Local` |
| Host | `localhost` |
| Port | `5432` (hoặc port bạn chọn) |
| Database | `phanlaw` |
| Username | `phanlaw` |
| Password | `phanlaw` |

## B4. Redis (tùy chọn)

```powershell
docker compose up -d redis
```

## B5. Cấu hình `.env`

```env
DATABASE_URL=postgresql+psycopg://agent_reader:agent_reader_local@localhost:5432/phanlaw?options=-csearch_path%3Dapp
PLATFORM_DATABASE_URL=postgresql+psycopg://phanlaw:phanlaw@localhost:5432/phanlaw?options=-csearch_path%3Dplatform
MIGRATE_DATABASE_URL=postgresql+psycopg://phanlaw:phanlaw@localhost:5432/phanlaw
```

## B6. Tiếp tục phần chung

```powershell
python scripts/db_migrate.py
python scripts/seed.py
python scripts/seed_vectors.py
python -m gateway.main
```

---

# FAQ & xử lý lỗi

### `connection refused` khi migrate

- Docker chưa chạy: `docker compose up -d`
- Sai port: `.env` phải trùng port host (Docker = `5434`)
- Postgres native chưa start: Services → PostgreSQL → Start

### `ModuleNotFoundError: No module named 'psycopg2'`

URL DB thiếu driver. Đổi `postgresql://` → `postgresql+psycopg://` trong cả 3 biến DB.

### `role "agent_reader" does not exist`

```powershell
python scripts/db_migrate.py
```

### `extension "vector" does not exist`

pgvector chưa cài. Dùng Docker image `pgvector/pgvector:pg16` hoặc cài extension thủ công (Cách B).

### Migration báo `already exists` / DB lộn xộn

Reset DB Docker và migrate lại:

```powershell
docker compose stop postgres
docker compose rm -sf postgres
docker volume rm multi-agent_pgdata
docker compose up -d postgres
python scripts/db_migrate.py
python scripts/seed.py
python scripts/seed_vectors.py
```

### `llm_enabled: false` / chat trả lời rỗng

Chưa điền `AZURE_OPENAI_API_KEY` hoặc `OPENROUTER_API_KEY` trong `.env`.

### `seed_vectors.py` lỗi embedding

```env
EMBEDDING_PROVIDER=azure
EMBEDDING_DEPLOYMENT=text-embedding-ada-002
EMBEDDING_DIMENSIONS=1536
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
```

### Khi nào dùng host `postgres` thay `localhost`?

| Ứng dụng | Host |
|----------|------|
| Python API trên máy | `localhost:5434` |
| pgAdmin trong Docker | `postgres:5432` |
| App trong Docker network | `postgres:5432` (chưa hỗ trợ API trong Docker) |

---

# Tóm tắt lệnh nhanh

### Docker (đầy đủ)

```powershell
cd d:\PHANLAW\multi-agent
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

Mở: http://localhost:8000/docs | pgAdmin: http://localhost:5050

### Cài tay (tóm tắt)

```powershell
# 1. Cài PostgreSQL + pgvector + pgAdmin (xem Cách B)
# 2. Tạo DB phanlaw, user phanlaw
# 3. .env dùng port native (5432) + postgresql+psycopg://
# 4. migrate + seed như trên
```

---

## Tài liệu liên quan

| Doc | Nội dung |
|-----|----------|
| [13-RAG-OBSERVABILITY-GUIDE.md](./13-RAG-OBSERVABILITY-GUIDE.md) | RAG, embedding, Azure Search |
| [15-FEEDBACK-LOOP.md](./15-FEEDBACK-LOOP.md) | Feedback & export |
| [FRONTEND-DESIGN-BRIEF.md](./FRONTEND-DESIGN-BRIEF.md) | UI design handoff |
| [16-REMAINING-ISSUES.md](./16-REMAINING-ISSUES.md) | Backlog kỹ thuật |
