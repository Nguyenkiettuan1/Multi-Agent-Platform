# Skill template

Developer documentation — explains the skill layout and how to customize.

## Files

| File | Role |
|------|------|
| `skill.yaml` | Config: triggers, agents, settings |
| `SKILL.md` | Agent instructions (markdown) |
| `README.md` | Developer docs (this file) |

## Customization

- Routing → edit `triggers` in `skill.yaml`
- Agent behavior → edit `SKILL.md`
- Metadata → edit `skill.yaml` without changing markdown

Copy this folder to `skills/<your-skill>/` and register in `agents/registry.yaml`.
