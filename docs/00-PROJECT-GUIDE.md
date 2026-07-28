# Hướng dẫn dự án — Đọc file này TRƯỚC

> Mục tiêu: Giải thích **kiến trúc phân lớp**, **từng folder làm gì**, **từng file vai trò gì**.

---

## 0. Platform đa năng — KHÔNG phải AI chuyên luật

Hệ thống hoạt động **giống GPT** cho phần lớn request, nhưng có thêm khả năng:

- **Plan → chia task** → giao agent chuyên biệt
- **Query DB**, **search tài liệu**, **thực thi action** qua agents riêng
- **Domain agents plug-in** — legal, finance, HR... thêm dần mà không đổi core

```
User: "Giải thích Kubernetes là gì?"
  → general-agent (như GPT)

User: "Có bao nhiêu bản ghi trong DB?"
  → db-worker

User: "Tìm tài liệu onboarding"
  → research-worker

User: "Điều khoản chấm dứt hợp đồng lao động?"
  → legal-agent  ← CHỈ MỘT domain agent, không phải default
```

### Phân loại agent

| Loại | Ví dụ | Mô tả |
|------|-------|--------|
| **General** | `general-agent` | GPT-like — Q&A, viết, giải thích |
| **Capability** | `db-worker`, `research-worker`, `action-worker` | Theo loại tác vụ (DB, search, API) |
| **Domain** | `legal-agent`, *(finance-agent)*, *(hr-agent)* | Plug-in theo nghiệp vụ |

Cấu hình: `agents/registry.yaml` — thêm domain agent mới = thêm entry + skill.

---

## 1. So sánh với Backend thông thường

Hệ thống AI Agent **KHÔNG thay thế** backend — nó **thêm lớp AI** lên trên backend. Cấu trúc tương đương:

| Backend truyền thống | AI Agent system (PHANLAW) | Ví dụ folder |
|---------------------|---------------------------|--------------|
| **API / Controller** | Gateway nhận request từ user | `gateway/` (sẽ có) |
| **Service / Business logic** | Workflow điều phối agent | `workflows/`, `core/` |
| **Repository / Data access** | MCP servers gọi DB, API ngoài | `mcp-servers/` |
| **Model / Entity** | State schema, DB migrations | `infra/database/` |
| **Config** | Biến môi trường, settings | `config/` + `.env` |
| **Business rules** | Skills (markdown) | `skills/` |
| **Unit test** | Eval cases (test chất lượng AI) | `eval/` |
| **Docker / IaC** | Hạ tầng | `infra/`, `docker-compose.yml` |
| **Prompt / Agent definition** | Cấu hình từng agent | `agents/` |

**Điểm khác biệt lớn:** Backend gọi function cố định. AI Agent **tự quyết định** gọi tool nào, agent nào — nên cần thêm lớp **Orchestration** và **Control Plane**.

---

## 2. Sơ đồ phân lớp (Layers)

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: PRESENTATION                                      │
│  User / Web / Teams / API Client                            │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: GATEWAY (giống API Controller)                    │
│  gateway/ — auth, rate limit, nhận request, trả response    │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: CONTROL PLANE (chính sách — không có trong BE đơn)│
│  config/ + (sẽ có) router, guardrails, HITL                 │
│  — Chọn model nào, agent nào được chạy, quota, RBAC         │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 4: ORCHESTRATION (giống Service layer)               │
│  workflows/ + core/ — LangGraph chạy flow multi-agent
│  — Planner → Workers → Reviewer → Synthesizer               │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 5: AGENTS (định nghĩa "nhân viên AI")                │
│  agents/ — prompt, role, model tier (KHÔNG chứa logic DB)  │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 6: TOOLS (giống Repository / External API client)    │
│  mcp-servers/ — sql-mcp, search-mcp (code gọi DB thật)      │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 7: DATA                                              │
│  PostgreSQL (app + platform), Redis                         │
│  infra/database/migrations/                                   │
└─────────────────────────────────────────────────────────────┘

        ┌──────────────────────────────────────┐
        │  CROSS-CUTTING (xuyên suốt)          │
        │  skills/ — domain knowledge          │
        │  eval/ — kiểm tra chất lượng AI      │
        │  docs/ — tài liệu kiến trúc         │
        └──────────────────────────────────────┘
```

**Các ông lớn (Anthropic, Microsoft, Google) đều tách tương tự:**
- **Control plane** — policy, routing (Mercor, Microsoft Agent Framework)
- **Execution plane** — agent runtime, workflow (LangGraph, Google ADK)
- **Data plane** — DB, vector store, cache
- **Tools** — MCP protocol (chuẩn mở, không nhét SQL vào prompt agent)

---

## 3. Từng folder — làm gì, KHÔNG làm gì

### `.cursor/mcp.json` — Chỉ cho Cursor IDE (dev)

Cursor chạy MCP server như **process riêng**, không tự đọc `.env`. File này truyền `DATABASE_URL` vào subprocess.

- **Source of truth cho Python:** `config/settings.py` + `.env`
- **mcp.json:** bản sao cho Cursor local — khi đổi password, sửa cả `.env` và `mcp.json`

---

### `config/` — Cấu hình tập trung (giống `appsettings.json` / `.env` loader)

| File | Vai trò |
|------|---------|
| `settings.py` | **DUY NHẤT** nơi đọc `.env`. Mọi module khác import từ đây. |

**Quy tắc:** Không hardcode password/URL trong file `.py` khác.

```python
# ✅ Đúng — mọi nơi dùng:
from config import get_settings
settings = get_settings()
engine = create_engine(settings.database_url)

# ❌ Sai — đã sửa:
database_url = "postgresql://phanlaw:phanlaw@localhost..."
```

---

### `agents/` — Định nghĩa agent (giống "job description", KHÔNG phải business code)

| File | Vai trò |
|------|---------|
| `orchestrator/agent.yaml` | Cấu hình: role, model tier, A2A connections |
| `orchestrator/agent.py` | System prompt của orchestrator |
| `db-agent/agent.py` | System prompt của DB worker |

**KHÔNG làm ở đây:** Query SQL, connect DB, gọi API. Agent chỉ có **instructions + danh sách tools**.

---

### `mcp-servers/` — Tool servers (giống Repository / DAO)

| Folder | Vai trò |
|--------|---------|
| `sql-server/server.py` | Expose tools: `list_tables`, `execute_query` — agent gọi qua MCP |
| `sql-server/_bootstrap.py` | Helper import `config` từ project root |

**Đây là nơi code chạm DB** — nhưng connection string lấy từ `config/settings.py` → `.env`, không hardcode.

Agent **không biết** connection string. Agent chỉ gọi tool `execute_query(sql)`.

---

### `core/` — Runtime dùng chung

| File | Vai trò |
|------|---------|
| `checkpointer.py` | Lưu LangGraph state vào PostgreSQL |
| `registry/agents.py` | Đọc `agents/registry.yaml` + load skills |

### `workflows/` — Orchestration (giống Service layer)

| File | Vai trò |
|------|---------|
| `state.py` | TaskPlan, SubTask, GraphState (Lesson 07 structured output) |
| `planner.py` | Phân rã user message → subtasks + assigned_agent |
| `graph.py` | LangGraph: triage → plan → execute → review → synthesize |
| `runner.py` | Entry point gọi từ Gateway |
| `nodes/pipeline.py` | Logic từng bước |
| `workers/handlers.py` | Code chạy từng agent chuyên biệt |

### `gateway/` — API HTTP (giống Controller)

| File | Vai trò |
|------|---------|
| `main.py` | FastAPI — `POST /api/v1/chat`, `GET /health` |

---

### `infra/` — Hạ tầng (giống DevOps / DBA)

| Path | Vai trò |
|------|---------|
| `database/migrations/*.sql` | Tạo bảng PostgreSQL (schema `app`, `platform`) |
| `azure.yaml` | Deploy lên cloud (Phase 2+) |
| `docker-compose.yml` (ở root) | PostgreSQL + Redis local |

**SQL schema nằm ở đây** — không nằm trong Python agent code.

---

### `skills/` — Domain knowledge (YAML config + Markdown)

| File | Vai trò |
|------|---------|
| `<skill>/skill.yaml` | **Config** — triggers, agents, version, settings (platform đọc) |
| `<skill>/SKILL.md` | **Instructions** — quy tắc cho agent (LLM đọc) |
| `<skill>/README.md` | **Docs** — cho developer (agent không đọc) |
| `_template/` | Mẫu tạo skill mới |

Loader: `core/skills/loader.py`

---

### `eval/` — Kiểm tra chất lượng AI (giống test suite)

| File | Vai trò |
|------|---------|
| `cases/basic.yaml` | Input → expected behavior (agent gọi đúng tool không?) |

Backend có unit test. AI system có **eval** vì output không deterministic.

---

### `scripts/` — Script vận hành (chạy tay, không phải service)

| File | Vai trò |
|------|---------|
| `db_migrate.py` | Chạy SQL migrations |
| `seed.py` | Nạp dữ liệu mẫu |

Dùng `MIGRATE_DATABASE_URL` (user admin), **không** dùng `agent_reader`.

---

### `docs/` — Tài liệu kiến trúc

| File | Đọc khi |
|------|---------|
| `00-PROJECT-GUIDE.md` | **Bắt đầu** — file này |
| `01-ARCHITECTURE.md` | Hiểu kiến trúc chi tiết |
| `09-INFRASTRUCTURE.md` | PostgreSQL local → cloud |
| `10-GITHUB-ARCHITECTURE-MAP.md` | Tham chiếu repo GitHub |

---

## 4. Luồng 1 request — đi qua folder nào?

Ví dụ user hỏi: *"Có bao nhiêu hợp đồng active?"*

```
1. gateway/main.py          → Nhận HTTP POST /chat
2. workflows/supervisor.py  → Triage: complexity thấp → Mode Direct
3. agents/db-agent/         → LLM quyết định gọi tool execute_query
4. mcp-servers/sql-server/  → Chạy SELECT ... FROM app.contracts
5. config/settings.py       → database_url từ .env (agent_reader)
6. PostgreSQL app schema    → Trả rows
7. agents/db-agent/         → LLM format câu trả lời tiếng Việt
8. gateway/main.py          → Trả JSON cho user
```

**Config/DB URL chỉ xuất hiện ở bước 5** — agent không thấy password.

---

## 5. PostgreSQL — 3 connection, 3 mục đích

| Biến `.env` | User DB | Dùng ở đâu | Quyền |
|-------------|---------|------------|-------|
| `DATABASE_URL` | `agent_reader` | `mcp-servers/sql-server` | SELECT only |
| `PLATFORM_DATABASE_URL` | `phanlaw` | `core/checkpointer.py` | Read/write platform schema |
| `MIGRATE_DATABASE_URL` | `phanlaw` (admin) | `scripts/db_migrate.py`, `scripts/seed.py` | DDL + seed |

**Tại sao 3 URL?** Principle of least privilege — agent chỉ được đọc data, không được sửa schema.

---

## 6. Cấu trúc hiện tại vs sẽ có (roadmap folder)

```
multi-agent/
├── config/              ✅ Có — settings tập trung
├── agents/              ✅ Có — định nghĩa agent
├── mcp-servers/         ✅ Có — tools (sql-mcp)
├── core/                 ✅ Có — registry, checkpointer
├── workflows/            ✅ Có — plan → workers → synthesize
├── gateway/              ✅ Có — FastAPI
├── core/                 ✅ Có — registry, checkpointer
├── skills/              ✅ Có
├── eval/                ✅ Có
├── infra/               ✅ Có — migrations, azure.yaml
├── scripts/             ✅ Có — migrate, seed
├── docs/                ✅ Có
├── docker-compose.yml   ✅ Có
└── .env                 ✅ Bạn tạo từ .env.example (KHÔNG commit)
```

**Hiện tại project mới ở Phase 0** — đã có docs + config + DB + MCP. Chưa có `gateway/` và `workflows/` vì chưa implement runtime.

---

## 7. Lỗi kiến trúc cần tránh (các ông lớn đã học)

| Lỗi | Hậu quả | Cách PHANLAW tránh |
|-----|---------|-------------------|
| SQL trong agent prompt | Injection, không audit | MCP sql-server + read-only role |
| Connection string trong .py | Lộ secret, khó đổi env | `config/settings.py` + `.env` only |
| 1 model cho mọi agent | Đắt, chậm | Model tier T0/T1/T2 (`docs/06`) |
| Agent ôm hết việc | Hallucination | Tách Planner / Worker / Reviewer |
| Không có eval | Deploy mù, regression | `eval/cases/` |
| SQLite local, PG prod | Surprise khi lên cloud | PostgreSQL từ đầu |
| Full history mọi agent | Context blowup | Isolated context (`docs/07`) |

---

## 8. Đọc tiếp theo thứ tự

1. **File này** — hiểu folder và layers
2. `docs/01-ARCHITECTURE.md` — kiến trúc chi tiết
3. `docs/09-INFRASTRUCTURE.md` — chạy PostgreSQL local
4. `docs/10-GITHUB-ARCHITECTURE-MAP.md` — tham chiếu GitHub
