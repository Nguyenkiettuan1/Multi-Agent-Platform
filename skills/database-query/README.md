# Database Query Skill

> **Developer docs** — agents do **not** load `README.md`. The agent reads `SKILL.md`; the platform reads `skill.yaml`.

## Purpose

Guide the DB worker to query PostgreSQL safely (SELECT only).

## Files

| File | Consumer | Content |
|------|----------|---------|
| `skill.yaml` | Platform | triggers, agents, settings |
| `SKILL.md` | Agent | SQL rules, schema, examples |
| `README.md` | Developer | This document |

## Customization

- Edit `skill.yaml` — change triggers, `max_rows`, assigned agents
- Edit `SKILL.md` — change SQL rules, schema documentation, examples

## Add a new table

Update the Schema section in `SKILL.md` or add `reference.md`.
