"""Skill loader — hỗ trợ CẢ HAI: YAML config + Markdown instructions.

Cấu trúc mỗi skill:
  skills/<name>/
    skill.yaml    # Config tùy biến (triggers, agents, version, enabled...)
    SKILL.md      # Hướng dẫn cho agent (markdown + frontmatter tùy chọn)
    README.md     # Tài liệu cho developer (optional)
    reference.md  # Chi tiết bổ sung (optional)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / "skills"


@dataclass
class SkillConfig:
    """Machine-readable — từ skill.yaml (ưu tiên) hoặc frontmatter SKILL.md."""

    name: str
    description: str = ""
    version: str = "1.0"
    enabled: bool = True
    triggers: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    model_tier: str | None = None
    max_context_tokens: int | None = None
    tags: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class Skill:
    """Skill đầy đủ — config + nội dung markdown."""

    config: SkillConfig
    instructions: str  # Body SKILL.md — agent đọc
    readme: str = ""  # README.md — cho developer
    reference: str = ""  # reference.md — optional


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Tách YAML frontmatter và markdown body từ SKILL.md."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return meta, body


def _config_from_dict(data: dict, skill_name: str) -> SkillConfig:
    return SkillConfig(
        name=data.get("name", skill_name),
        description=data.get("description", ""),
        version=str(data.get("version", "1.0")),
        enabled=data.get("enabled", True),
        triggers=data.get("triggers", []) or [],
        agents=data.get("agents", []) or [],
        model_tier=data.get("model_tier"),
        max_context_tokens=data.get("max_context_tokens"),
        tags=data.get("tags", []) or [],
        extra={k: v for k, v in data.items() if k not in {
            "name", "description", "version", "enabled", "triggers",
            "agents", "model_tier", "max_context_tokens", "tags",
        }},
    )


def load_skill(skill_name: str) -> Skill | None:
    """Load skill đầy đủ: skill.yaml + SKILL.md + README.md."""
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.is_dir():
        return None

    # 1. skill.yaml — config chính (ưu tiên cao nhất)
    yaml_path = skill_dir / "skill.yaml"
    config_data: dict = {}
    if yaml_path.exists():
        config_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}

    # 2. SKILL.md — instructions
    skill_md_path = skill_dir / "SKILL.md"
    instructions = ""
    if skill_md_path.exists():
        raw = skill_md_path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(raw)
        instructions = body
        # Frontmatter bổ sung nếu skill.yaml thiếu field
        for key, value in frontmatter.items():
            if key not in config_data or config_data[key] in (None, [], ""):
                config_data[key] = value

    if not config_data and not instructions:
        return None

    config = _config_from_dict(config_data, skill_name)

    # 3. README.md — developer docs (không inject vào agent prompt)
    readme_path = skill_dir / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

    # 4. reference.md — append vào instructions nếu có
    ref_path = skill_dir / "reference.md"
    reference = ref_path.read_text(encoding="utf-8") if ref_path.exists() else ""
    full_instructions = instructions
    if reference:
        full_instructions = f"{instructions}\n\n---\n\n## Reference\n\n{reference}"

    return Skill(
        config=config,
        instructions=full_instructions,
        readme=readme,
        reference=reference,
    )


def load_skill_instructions(skill_name: str) -> str:
    """Shortcut — chỉ lấy markdown instructions cho agent."""
    skill = load_skill(skill_name)
    return skill.instructions if skill else ""


def list_skills(*, enabled_only: bool = True) -> list[Skill]:
    """Liệt kê tất cả skills trong folder."""
    skills: list[Skill] = []
    if not SKILLS_DIR.exists():
        return skills

    for path in sorted(SKILLS_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        skill = load_skill(path.name)
        if skill and (not enabled_only or skill.config.enabled):
            skills.append(skill)
    return skills


def match_skills(user_message: str, agent_id: str | None = None) -> list[Skill]:
    """Tìm skills theo trigger keywords và agent assignment."""
    msg = user_message.lower()
    matched: list[Skill] = []

    for skill in list_skills():
        cfg = skill.config
        if agent_id and cfg.agents and agent_id not in cfg.agents:
            continue
        if any(trigger.lower() in msg for trigger in cfg.triggers):
            matched.append(skill)

    return matched[:3]
