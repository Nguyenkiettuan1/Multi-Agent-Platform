# Skills System — YAML config + Markdown instructions

## Nguyên tắc: nhận CẢ HAI

Mỗi skill có **2 lớp** tách biệt:

| File | Định dạng | Ai đọc | Mục đích |
|------|-----------|--------|----------|
| **`skill.yaml`** | YAML | Platform (router, loader, registry) | Tùy biến config: triggers, agents, version, enabled, settings |
| **`SKILL.md`** | Markdown | Agent (LLM) | Hướng dẫn, quy tắc, ví dụ — nội dung agent đọc |
| **`README.md`** | Markdown | Developer | Tài liệu cho người — agent **KHÔNG** đọc |
| `reference.md` | Markdown | Agent (optional) | Chi tiết bổ sung, append vào instructions |

```
skills/database-query/
├── skill.yaml      ← Config tùy biến (đổi trigger không cần sửa markdown)
├── SKILL.md        ← Agent instructions (markdown thuần hoặc + frontmatter)
├── README.md       ← Docs cho developer
└── reference.md    ← Optional deep reference
```

**Không phải "chỉ YAML" hay "chỉ README"** — cả hai phục vụ mục đích khác nhau.

---

## skill.yaml — Machine config

```yaml
name: database-query
description: Truy vấn PostgreSQL read-only
version: "1.0"
enabled: true

agents:
  - db-worker

triggers:
  - query
  - database
  - sql

model_tier: T1
max_context_tokens: 2048

tags:
  - capability

settings:           # Tùy biến riêng — platform đọc
  max_rows: 100
  read_only: true
```

**Dùng khi:** đổi routing, bật/tắt skill, gán agent, version, business settings.

---

## SKILL.md — Agent instructions

Markdown thuần (khuyến nghị) — **không bắt buộc** frontmatter nếu đã có `skill.yaml`:

```markdown
# Database Query Skill

## Quy tắc
1. CHỈ SELECT
2. Luôn LIMIT
...
```

Có thể **thêm frontmatter** làm fallback nếu thiếu `skill.yaml`:

```markdown
---
name: database-query
triggers: [query, sql]
---

# Nội dung...
```

**Loader ưu tiên:** `skill.yaml` > frontmatter SKILL.md > defaults.

---

## README.md — Developer docs

Giải thích skill cho team — **không inject vào prompt agent**.

---

## Loader API

```python
from core.skills.loader import load_skill, list_skills, match_skills

# Load đầy đủ
skill = load_skill("database-query")
skill.config.triggers      # từ skill.yaml
skill.instructions         # body SKILL.md (+ reference.md)
skill.readme               # README.md

# Match theo user message
matched = match_skills("query database", agent_id="db-worker")

# Chỉ instructions (cho worker handler)
from core.skills.loader import load_skill_instructions
text = load_skill_instructions("database-query")
```

---

## Tạo skill mới

1. Copy `skills/_template/`
2. Sửa `skill.yaml` — config
3. Viết `SKILL.md` — instructions cho agent
4. Viết `README.md` — docs cho team
5. Thêm vào `agents/registry.yaml` nếu cần
6. Test: `python -c "from core.skills.loader import load_skill; print(load_skill('my-skill'))"`

---

## Skills vs Fine-tuning

| Scenario | skill.yaml | SKILL.md | Fine-tuning |
|----------|------------|----------|-------------|
| Đổi trigger/routing | ✅ | — | — |
| Đổi quy tắc agent | — | ✅ | — |
| Đổi output format | — | ✅ | ✅ SFT |
| Học reasoning | — | ⚠️ | ✅ |
