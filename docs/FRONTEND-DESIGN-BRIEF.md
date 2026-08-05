> **English guides:** [README](../README.md) · [Local setup](12-LOCAL-SETUP.md) · [Docs index](README.md)  
> This document may still contain Vietnamese in places; prefer the English guides above for running the project.

# Enterprise Multi-Agent AI Platform — Frontend Design Brief

> **Document version:** 2.0  
> **Backend:** API-only (FastAPI v0.3.0) — no UI exists yet  
> **API:** `http://localhost:8000/docs` · OpenAPI: `/openapi.json`  
> **Audience:** UI/UX, Figma, Figma Make AI, Frontend engineers

---

## ⚠️ CRITICAL — Read before designing

| Do NOT design | DO design |
|---------------|-----------|
| A **law firm website** or legal research portal | A **general-purpose enterprise AI workspace** (like ChatGPT Enterprise + admin console) |
| Scales of justice, gavels, law books as primary visuals | Neutral tech: agents, knowledge, workflows, citations |
| Legal-only sample content | **Mixed sample content:** general Q&A, data queries, document research, HR, IT, **and occasionally** legal |
| Product name shown as "Law AI" | Product working title: **"Agent Workspace"** (internal codename: multi-agent — company name only, not product theme) |

**What this product is:** An **orchestrated multi-agent AI platform**. The user sends one message; the system automatically picks the right specialist agent (general assistant, database analyst, researcher, legal specialist, etc.), searches knowledge + web, and returns a cited answer.

**Legal is ONE optional domain agent** (~10% of use cases). The default experience is **general enterprise AI chat**.

---

## 1. Product concept

### 1.1 One-liner

> *"One chat box. Multiple AI agents behind the scenes. Every answer backed by sources."*

### 1.2 What happens when user sends a message

```
User message
    → Intent classification (greeting / general / research / database / legal / blocked)
    → Task planning (simple = direct; complex = multi-step)
    → Worker agent(s) execute (search docs, query DB, web search…)
    → Optional review step
    → Final synthesized answer + citations
    → Quality check + save for feedback loop
```

### 1.3 Agent types (show in UI as badges, NOT as separate apps)

| Agent | When used | Example user question |
|-------|-----------|----------------------|
| **General Assistant** | Explain, write, brainstorm | "Summarize this email draft" |
| **Research Worker** | Internal docs + web search | "What is our refund policy?" |
| **DB Worker** | Query business database | "How many contracts expired last month?" |
| **Legal Agent** | Legal-domain questions only | "What is the probation period under labor law?" |
| **Action Worker** | Future: send email, call API | (Phase 2 — show disabled) |

Design implication: **One chat UI** handles all agents. Show which agent(s) worked via a small **"Agents involved"** chip list in the assistant message metadata — not separate product areas per domain.

---

## 2. Personas & access

| Persona | Role | Can access |
|---------|------|------------|
| **Employee** | End user | Chat, rate answers, view own session history |
| **Knowledge Admin** | Content ops | Knowledge base upload, chunk tools |
| **Platform Admin** | IT / ops | Dashboard, audit, feedback export, models view |
| **Super Admin** | Future | SSO, API keys, tenant settings |

**Auth today:** Optional `X-API-Key` header. **Auth planned:** Microsoft Entra ID SSO — reserve **Login** page slot.

---

## 3. Information architecture (all pages)

### 3.1 Sitemap

```
PUBLIC (future)
└── /login                          Login / SSO

USER APP
├── /                               → redirect to /chat
├── /chat                           New chat
├── /chat/:sessionId                Existing session
└── /settings                       User preferences (theme, language)

ADMIN CONSOLE
├── /admin                          Dashboard overview
├── /admin/knowledge                Document library
├── /admin/knowledge/upload         Upload wizard (or modal from list)
├── /admin/knowledge/:docId         Document detail + chunks
├── /admin/knowledge/tools          Chunk preview & eval tools
├── /admin/feedback                 Q&A feedback list
├── /admin/feedback/:traceId        Feedback detail
├── /admin/audit                    Audit log
├── /admin/audit/:traceId           Audit detail (links to feedback)
└── /admin/models                   Model & agent catalog (read-only)
```

### 3.2 Global layout shells

**A. User App Shell** (pages under `/chat`, `/settings`)

```
┌─────────────────────────────────────────────────────────────┐
│ Top bar: [Logo] Agent Workspace    [Admin ↗] [User ▾] [⚙]  │
├──────────────┬──────────────────────────────────────────────┤
│ Session      │  Main content (chat thread)                  │
│ sidebar      │                                              │
│              │                                              │
│ [+ New chat] │                                              │
│ Session list │                                              │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

**B. Admin Console Shell** (pages under `/admin/*`)

```
┌─────────────────────────────────────────────────────────────┐
│ Top bar: [Logo] Admin Console      [← Back to Chat] [User] │
├──────────────┬──────────────────────────────────────────────┤
│ Admin nav    │  Page content                                │
│ · Dashboard  │                                              │
│ · Knowledge  │                                              │
│ · Feedback   │                                              │
│ · Audit      │                                              │
│ · Models     │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

---

## 4. Navigation & page link matrix

| From page | Button / link | Goes to |
|-----------|---------------|---------|
| Any user page | **Admin** (top bar) | `/admin` |
| Any admin page | **Back to Chat** | `/chat` |
| `/chat` sidebar | Session item click | `/chat/:sessionId` |
| `/chat` sidebar | **+ New chat** | `/chat` (clear thread) |
| `/chat` top bar | **Settings** ⚙ | `/settings` |
| Assistant message | **View trace** (debug) | Copy `trace_id` (no page) |
| Assistant message | Citation `[D1]` click | Opens **Sources panel** (drawer, same page) |
| `/admin` KPI card "Documents" | click | `/admin/knowledge` |
| `/admin` KPI card "Feedback" | click | `/admin/feedback` |
| `/admin` KPI card "Audit" | click | `/admin/audit` |
| `/admin` recent feedback row | click | `/admin/feedback/:traceId` |
| `/admin` recent audit row | click | `/admin/audit/:traceId` |
| `/admin/knowledge` row | click doc title | `/admin/knowledge/:docId` |
| `/admin/knowledge` | **Upload document** | `/admin/knowledge/upload` or modal |
| `/admin/knowledge` | **Chunk tools** | `/admin/knowledge/tools` |
| `/admin/knowledge/:docId` | **Back** | `/admin/knowledge` |
| `/admin/feedback` row | click | `/admin/feedback/:traceId` |
| `/admin/feedback/:traceId` | **Promote to Knowledge** | Stays, shows success toast |
| `/admin/audit/:traceId` | **View Q&A** | `/admin/feedback/:traceId` |
| `/admin/feedback/:traceId` | **View audit** | `/admin/audit/:traceId` |

---

## 5. User flows (clickable prototype paths)

### Flow 1 — General chat (most common)

```
/chat → type "Explain REST API in simple terms"
      → [Send]
      → loading skeleton (5–30s)
      → assistant reply (markdown, no citations required)
      → agent badge: "General Assistant"
      → rate 1–5 stars → [Submit rating]
```

### Flow 2 — Research with citations

```
/chat → "What is our remote work policy?"
      → loading: "Searching knowledge base & web..."
      → reply with [D1] [D2] inline badges
      → click [D1] → Sources panel opens
      → agent badges: "Research Worker"
      → expand "Sources" section at bottom
```

### Flow 3 — Database question

```
/chat → "How many active users registered this week?"
      → agent badge: "DB Worker"
      → reply includes data summary (table in markdown)
      → optional: "View SQL" debug expand (future)
```

### Flow 4 — Legal question (minority case)

```
/chat → "Maximum probation period under labor law?"
      → agent badge: "Legal Agent" + "Research Worker"
      → reply with [D1] [W1] citations
      → same citation UX as Flow 2
```

### Flow 5 — Admin uploads document

```
/admin/knowledge → [Upload document]
                 → drag PDF → set domain "hr"
                 → [Preview chunks] → modal shows chunks
                 → [Confirm ingest] → toast success
                 → redirect /admin/knowledge/:docId
```

### Flow 6 — Admin reviews feedback → promotes to knowledge

```
/admin/feedback → filter rating ≥ 4
                → click row → /admin/feedback/:traceId
                → [Promote to Knowledge] → confirm dialog → success badge
```

---

## 6. Page specifications (detailed)

---

### PAGE: `/chat` and `/chat/:sessionId`

**Purpose:** Primary product — multi-agent chat.

**Layout:** User App Shell with session sidebar.

#### 6.1.1 Session sidebar (left)

| Element | Type | Behavior |
|---------|------|----------|
| **+ New chat** | Button (primary outline) | Clears thread, new `session_id` on next send |
| Session list | Scrollable list | Each item: first user message preview (truncated), relative time |
| Active session | Highlighted row | Current `sessionId` |
| Empty state | Illustration + text | "No conversations yet. Start by typing below." |
| Collapse toggle | Icon button (mobile) | Hides sidebar → hamburger in top bar |

#### 6.1.2 Chat thread (center)

| Element | Type | Behavior |
|---------|------|----------|
| User message bubble | Right-aligned | Plain text, timestamp |
| Assistant message bubble | Left-aligned | Markdown rendered |
| **Agent chips** | Badge row under assistant header | e.g. `General Assistant` `Research Worker` — from `worker_results[].agent` |
| **Topology badge** | Small tag | `direct` / `planned` / `reviewed` — from `topology_mode` |
| **Quality badge** | Optional | Green ✓ or amber ⚠ from `eval.passed` |
| Inline citations | Clickable badges `[D1]` `[W2]` | Knowledge=blue, Web=orange |
| **Sources** accordion | Below message body | Lists all `citations[]` |
| **Rating widget** | 1–5 stars + optional comment textarea | Visible after each assistant reply |
| **Submit rating** | Button | `POST /api/v1/feedback` |
| **Copy trace ID** | Icon in message menu (⋯) | Copies `trace_id` for support |
| **Regenerate** | Button (future) | Disabled / hidden for v1 |
| Loading state | Skeleton bubble + text | "Analyzing your request…" |
| Blocked state | Warning banner in bubble | Shows `triage.block_reason`, no rating |
| Error state | Red banner | "Something went wrong" + trace_id + **Retry** |

#### 6.1.3 Sources panel (right drawer — opens on citation click)

| Field | Source |
|-------|--------|
| ref_id | `D1`, `W1` |
| title | citation.title |
| excerpt | citation.excerpt (scrollable) |
| type badge | knowledge / web |
| link button | citation.url (web only) — **Open source** |
| doc_id | citation.doc_id (knowledge only) — copyable |
| relevance score | citation.score (optional %) |

#### 6.1.4 Message input area (bottom, sticky)

| Element | Type | Behavior |
|---------|------|----------|
| Textarea | Multi-line, auto-grow | Max 8000 chars, placeholder: "Ask anything — general questions, data, documents, research…" |
| **Send** | Button (primary) | Disabled when empty or loading |
| Char counter | Subtle text | Shows when > 7000 chars |
| Keyboard | Enter = send, Shift+Enter = newline | |

**API:** `POST /api/v1/chat` — body: `{ message, session_id?, user_id }`

---

### PAGE: `/settings`

**Purpose:** User preferences (minimal v1).

| Section | Controls |
|---------|----------|
| Appearance | Theme: Light / Dark / System |
| Language | UI language: Vietnamese / English |
| API key (dev only) | Text input + **Save** — for local `X-API-Key` |
| About | Version from `GET /health` |

**Buttons:** **Save changes** · **Cancel**

---

### PAGE: `/admin` (Dashboard)

**Purpose:** Platform health snapshot for admins.

**API:** `GET /api/v1/admin/overview`

#### 6.3.1 Capability status row (top)

| Badge | Data field | States |
|-------|------------|--------|
| LLM | `capabilities.llm` | ✓ Connected / ✗ Not configured |
| Embeddings | `capabilities.embeddings` | ✓ / ✗ |
| Web Search | `capabilities.web_search` | ✓ / ✗ |
| Azure Search | `capabilities.azure_search` | ✓ / ✗ |
| Tracing | `capabilities.tracing` | ✓ / ✗ |
| Hybrid Search (RRF) | `capabilities.rrf_fusion` | always ✓ |

#### 6.3.2 KPI cards (clickable → respective pages)

| Card | Count field | Link |
|------|-------------|------|
| Knowledge documents | `counts.knowledge_documents` | `/admin/knowledge` |
| With embeddings | `counts.knowledge_with_embedding` | `/admin/knowledge` |
| Feedback entries | `counts.feedback` | `/admin/feedback` |
| Rated | `counts.feedback_rated` | `/admin/feedback` |
| Promoted to RAG | `counts.feedback_promoted` | `/admin/feedback` |
| Audit events | `counts.audit_log` | `/admin/audit` |

#### 6.3.3 Recent tables (bottom, two columns)

**Recent feedback** (10 rows): question preview · rating · eval_score · time → row click → `/admin/feedback/:traceId`

**Recent audit** (10 rows): action badge · trace_id · user_id · time → row click → `/admin/audit/:traceId`

**Buttons on page:** **Refresh** (reload overview)

---

### PAGE: `/admin/knowledge`

**Purpose:** Manage RAG document library (any domain — HR, IT, sales, legal, general).

**API:** `GET /api/v1/admin/knowledge?domain=&limit=`

#### 6.4.1 Toolbar

| Element | Behavior |
|---------|----------|
| **Upload document** | Primary button → upload page/modal |
| **Chunk tools** | Secondary → `/admin/knowledge/tools` |
| Domain filter | Dropdown: All / general / hr / legal / it / … |
| Search box | Client-side filter by title (v1) |
| **Refresh** | Reload table |

#### 6.4.2 Document table

| Column | Field |
|--------|-------|
| Title | `title` (link) |
| Domain | `domain` (color tag — NOT law-themed; use neutral category colors) |
| Source | `source` |
| Chunks | `chunk_index` / parent grouping |
| Embedding | `has_embedding` ✓/✗ |
| Size | `content_length` |
| Updated | `updated_at` |
| Actions | **View chunks** · **⋮** menu (future: delete) |

**Empty state:** "No documents yet" + **Upload document** CTA

**Row click (title):** → `/admin/knowledge/:docId`

---

### PAGE: `/admin/knowledge/upload`

**Purpose:** Upload and ingest documents.

**API:** `POST /api/v1/admin/knowledge/upload` (multipart)

| Field | Type | Required |
|-------|------|----------|
| File | Drag-drop zone | Yes — PDF, DOCX, TXT |
| Document ID | Text input | No — auto-generated if empty |
| Domain | Select | Default `general` |
| Chunk size | Number | No — default 800 |
| Chunk overlap | Number | No — default 120 |
| Preview only | Checkbox | If checked: preview without saving |

**Buttons:**

| Button | Action |
|--------|--------|
| **Preview chunks** | Upload with `preview_only=true` → show preview modal |
| **Ingest** | Upload and index to knowledge base |
| **Cancel** | Back to `/admin/knowledge` |

**Preview modal:** chunk list with char count, quality warnings, **Close** · **Proceed to ingest**

---

### PAGE: `/admin/knowledge/:docId`

**Purpose:** View one document and its chunks.

**API:** `GET /api/v1/admin/knowledge/{parent_doc_id}/chunks`

| Section | Content |
|---------|---------|
| Header | Title, domain tag, source, doc_id (copy) |
| Stats | Chunk count, embedding status |
| Chunk table | `chunk_index`, title, `has_embedding`, content preview (truncated) |

**Buttons:** **← Back to library** · **Re-upload** (future) · **Delete** (future, disabled v1)

---

### PAGE: `/admin/knowledge/tools`

**Purpose:** Chunk quality tools (no DB write).

#### Tab A — Chunk Preview

**API:** `POST /api/v1/admin/knowledge/chunk-preview`

| Field | Type |
|-------|------|
| Content | Large textarea (paste text) |
| Title | Text |
| Chunk size / overlap | Numbers |

**Button:** **Preview** → shows analysis: chunk count, avg size, warnings

#### Tab B — Chunk Eval

**API:** `POST /api/v1/admin/knowledge/chunk-eval`

| Field | Type |
|-------|------|
| Content | Textarea |
| Test query | Text — "What question should retrieve the best chunk?" |
| Chunk settings | size / overlap |

**Button:** **Evaluate** → ranked chunks with similarity scores + recommendation text

---

### PAGE: `/admin/feedback`

**Purpose:** Review saved Q&A pairs for quality and training export.

**API:** `GET /api/v1/admin/feedback?min_rating=&limit=`

#### Toolbar

| Element | Behavior |
|---------|----------|
| Min rating filter | Dropdown: All / ≥3 / ≥4 / ≥5 |
| **Export dataset** | Opens export dialog |
| **Refresh** | Reload list |

#### Export dialog

| Field | Options |
|-------|---------|
| Format | jsonl / openai / pairs |
| Min rating | Number |
| Min eval score | Number |
| Limit | Number |

**Button:** **Download** → `GET /api/v1/admin/feedback/export?format=...`

#### Table columns

| Column | Field |
|--------|-------|
| Question | `user_message` (truncated) |
| Answer preview | `response` (truncated) |
| Rating | `rating` stars or "—" |
| Eval score | `eval_score` |
| Promoted | badge if promoted |
| Time | `created_at` |
| Actions | **View** · **Promote** (if rating ≥ threshold & not promoted) |

**Row click:** → `/admin/feedback/:traceId`

---

### PAGE: `/admin/feedback/:traceId`

**Purpose:** Single Q&A detail.

| Section | Content |
|---------|---------|
| Question | Full `user_message` |
| Answer | Full `response` (markdown) |
| Metadata | trace_id, session_id, rating, comment, eval_score |
| Quality checks | `eval.checks[]` if available |

**Buttons:**

| Button | API | Condition |
|--------|-----|-----------|
| **← Back** | — | → `/admin/feedback` |
| **Promote to Knowledge** | `POST /admin/feedback/{trace_id}/promote` | Not yet promoted |
| **View audit log** | — | → `/admin/audit/:traceId` |
| **Copy trace ID** | — | Always |

**After promote:** show badge "In knowledge base" + `promoted_doc_id`

---

### PAGE: `/admin/audit`

**Purpose:** Operational trace log.

**API:** `GET /api/v1/admin/audit?trace_id=&limit=`

#### Toolbar

| Element | Behavior |
|---------|----------|
| Trace ID search | Text filter |
| Action filter | All / chat_start / chat_complete / chat_error |
| **Refresh** | Reload |

#### Table

| Column | Field |
|--------|-------|
| Time | `created_at` |
| Action | badge colored by type |
| Trace ID | link → `/admin/audit/:traceId` |
| User | `user_id` |
| Agent | `agent_name` |

---

### PAGE: `/admin/audit/:traceId`

| Section | Content |
|---------|---------|
| Trace ID | copyable |
| Events timeline | All audit rows for this trace_id |
| Payload | JSON viewer (collapsible) |

**Buttons:** **← Back** · **View Q&A** → `/admin/feedback/:traceId`

---

### PAGE: `/admin/models`

**Purpose:** Read-only ops view of model routing.

**API:** `GET /api/v1/models`

| Section | Content |
|---------|---------|
| LLM status | `llm_enabled` banner |
| Model catalog | Table: ref, provider, model_id, tags |
| Agent mapping | Which agent uses which model |
| Pipeline mapping | triage, planner, reviewer, synthesizer, evaluator |

No edit controls in v1.

---

## 7. Citation system (UI spec)

Citations appear for **research** and **legal** answers — not every message.

| Prefix | Meaning | Color | Icon suggestion |
|--------|---------|-------|-----------------|
| `[D1]` `[D2]` | Internal knowledge (RAG) | Blue `#2563EB` | Document |
| `[W1]` `[W2]` | Web search | Orange `#EA580C` | Globe |

**Interaction:** click badge → highlight in Sources panel + scroll to entry.

**Do not** use legal-specific iconography for knowledge docs — use generic document icon.

---

## 8. Visual & brand guidelines

| Guideline | Direction |
|-----------|-----------|
| Product personality | **Smart, neutral, enterprise** — think Microsoft Copilot / Notion AI, not Westlaw |
| Primary color | Slate/navy tech palette — NOT gold/maroon law colors |
| Sample avatars | Generic business users |
| Sample domains in knowledge table | `general`, `hr`, `it`, `sales`, `legal` — legal is one tag among many |
| Sample chat questions in mocks | 60% general/research, 25% data/ops, 15% legal |
| Typography | Clean sans-serif (Inter, SF Pro, Segoe UI) |
| Icons | Lucide / Heroicons — agent, database, search, document, settings |

---

## 9. Responsive behavior

| Breakpoint | Chat | Admin |
|------------|------|-------|
| Desktop ≥1280px | Sidebar + thread + sources drawer | Sidebar nav + full tables |
| Tablet 768–1279px | Collapsible sidebar | Stacked KPI cards |
| Mobile ≤767px | Full-screen thread, hamburger sessions | Horizontal scroll tables, simplified nav |

---

## 10. States catalogue (all pages)

| State | Pattern |
|-------|---------|
| Loading | Skeleton / spinner |
| Empty | Illustration + primary CTA |
| Error 401 | "Authentication required" + login/key prompt |
| Error 500 | Toast + retry + trace_id |
| Success | Toast notification (3s auto-dismiss) |
| Offline | Banner "No connection" |

---

## 11. Out of scope (v1 — do not design)

| Feature | Status |
|---------|--------|
| Streaming chat (token-by-token) | Backend not ready |
| User registration / SSO UI | Planned |
| Edit/delete knowledge documents | API not ready |
| Real-time multi-user chat | Not supported |
| Time-series analytics charts | Counts only |
| Mobile native app | Web responsive only |
| Per-agent separate chat apps | Single chat only |

---

## 12. API quick reference (all endpoints)

| Method | Path | Used on page |
|--------|------|--------------|
| GET | `/health` | Settings, status |
| POST | `/api/v1/chat` | Chat |
| POST | `/api/v1/feedback` | Chat rating |
| GET | `/api/v1/models` | Admin models |
| GET | `/api/v1/admin/overview` | Dashboard |
| GET | `/api/v1/admin/stats` | Dashboard (subset) |
| GET | `/api/v1/admin/knowledge` | Knowledge list |
| POST | `/api/v1/admin/knowledge` | Manual ingest |
| POST | `/api/v1/admin/knowledge/upload` | Upload |
| POST | `/api/v1/admin/knowledge/chunk-preview` | Chunk tools |
| POST | `/api/v1/admin/knowledge/chunk-eval` | Chunk tools |
| GET | `/api/v1/admin/knowledge/{id}/chunks` | Doc detail |
| GET | `/api/v1/admin/feedback` | Feedback list |
| GET | `/api/v1/admin/feedback/export` | Export dialog |
| POST | `/api/v1/admin/feedback/{id}/promote` | Feedback detail |
| GET | `/api/v1/admin/audit` | Audit list |

---

## 13. Figma Make AI — suggested prompt

> Design an **enterprise multi-agent AI workspace** (NOT a law app). Product name: "Agent Workspace". Main screen: chat with session sidebar, agent badges (General, Research, DB, Legal), markdown messages, blue document citations [D1] and orange web citations [W1], sources drawer, 5-star rating. Separate admin console: dashboard KPIs, knowledge document table with domain tags (hr, it, sales, legal), upload wizard, feedback Q&A table, audit log. Neutral navy/slate tech aesthetic. Vietnamese UI labels. No legal imagery.

---

## 14. Deliverables checklist

- [ ] User app: Chat (all states), Settings
- [ ] Admin: Dashboard, Knowledge list/upload/detail/tools, Feedback list/detail, Audit list/detail, Models
- [ ] Navigation map + clickable prototype (6 flows in Section 5)
- [ ] Component library (Section 6 + message/citation/rating components)
- [ ] Mobile chat layout
- [ ] Design tokens (colors, spacing, typography)
- [ ] Mock data: **mixed domains**, not law-only

---

## 15. Related backend docs

| Doc | Topic |
|-----|-------|
| [12-LOCAL-SETUP.md](./12-LOCAL-SETUP.md) | Run API locally |
| [13-RAG-OBSERVABILITY-GUIDE.md](./13-RAG-OBSERVABILITY-GUIDE.md) | RAG & citations |
| [15-FEEDBACK-LOOP.md](./15-FEEDBACK-LOOP.md) | Feedback & export |
| [16-REMAINING-ISSUES.md](./16-REMAINING-ISSUES.md) | Technical backlog |

---

*Internal codename: Multi-Agent Platform · Backend v0.3.0 · Design brief v2.0*
