# Skills System — YAML config + Markdown instructions

## Principle: accept BOTH

Each skill has **2 separate layers**:

| File | Format | Read by | Purpose |
|------|-----------|--------|----------|
| **`skill.yaml`** | YAML | Platform (router, loader, registry) | Customizable config: triggers, agents, version, enabled, settings |
| **`SKILL.md`** | Markdown | Agent (LLM) | Instructions, rules, examples — content the agent reads |
| **`README.md`** | Markdown | Developer | Documentation for humans — agent does **NOT** read this |
| `reference.md` | Markdown | Agent (optional) | Additional details, appended to instructions |

```
skills/database-query/
├── skill.yaml      ← Customizable config (change triggers without editing markdown)
├── SKILL.md        ← Agent instructions (plain markdown or + frontmatter)
├── README.md       ← Developer docs
└── reference.md    ← Optional deep reference
```

**Not "YAML only" or "README only"** — both serve different purposes.

---

## skill.yaml — Machine config

```yaml
name: database-query
description: Read-only PostgreSQL queries
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

settings:           # Custom settings — read by platform
  max_rows: 100
  read_only: true
```

**Use when:** changing routing, enabling/disabling skills, assigning agents, versioning, business settings.

---

## SKILL.md — Agent instructions

Plain markdown (recommended) — frontmatter is **not required** if `skill.yaml` exists:

```markdown
# Database Query Skill

## Rules
1. SELECT only
2. Always use LIMIT
...
```

You may **add frontmatter** as a fallback when `skill.yaml` is missing:

```markdown
---
name: database-query
triggers: [query, sql]
---

# Content...
```

**Loader priority:** `skill.yaml` > SKILL.md frontmatter > defaults.

---

## README.md — Developer docs

Explains the skill for the team — **not injected into the agent prompt**.

---

## Loader API

```python
from core.skills.loader import load_skill, list_skills, match_skills

# Full load
skill = load_skill("database-query")
skill.config.triggers      # from skill.yaml
skill.instructions         # SKILL.md body (+ reference.md)
skill.readme               # README.md

# Match by user message
matched = match_skills("query database", agent_id="db-worker")

# Instructions only (for worker handler)
from core.skills.loader import load_skill_instructions
text = load_skill_instructions("database-query")
```

---

## Creating a new skill

1. Copy `skills/_template/`
2. Edit `skill.yaml` — config
3. Write `SKILL.md` — instructions for the agent
4. Write `README.md` — docs for the team
5. Add to `agents/registry.yaml` if needed
6. Test: `python -c "from core.skills.loader import load_skill; print(load_skill('my-skill'))"`

---

## Skills vs Fine-tuning

| Scenario | skill.yaml | SKILL.md | Fine-tuning |
|----------|------------|----------|-------------|
| Change trigger/routing | ✅ | — | — |
| Change agent rules | — | ✅ | — |
| Change output format | — | ✅ | ✅ SFT |
| Learn reasoning | — | ⚠️ | ✅ |
