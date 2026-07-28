# Database Query Skill

> **Developer docs** — file này cho người đọc, agent KHÔNG load README.md.
> Agent đọc `SKILL.md`. Platform đọc `skill.yaml`.

## Mục đích

Hướng dẫn DB Worker truy vấn PostgreSQL an toàn (SELECT only).

## Files trong skill này

| File | Ai đọc | Nội dung |
|------|--------|----------|
| `skill.yaml` | Platform (router, loader) | triggers, agents, settings |
| `SKILL.md` | Agent (LLM) | Quy tắc SQL, schema, examples |
| `README.md` | Developer | Tài liệu này |

## Tùy biến

Sửa `skill.yaml` → đổi triggers, max_rows, agents mà không cần sửa markdown.

Sửa `SKILL.md` → đổi quy tắc, schema, ví dụ cho agent.

## Thêm schema mới

Cập nhật section Schema trong `SKILL.md` hoặc tạo `reference.md`.
