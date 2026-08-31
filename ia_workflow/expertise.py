"""Resolução de skills/agents especialistas para as etapas de um workflow.

Cada step YAML pode indicar ``skill: <nome>`` (lê ``.iaw/skills/<nome>/SKILL.md``)
ou ``agent: <nome>`` (lê ``.iaw/agents/<nome>.md`` — ou um diretório com
``AGENT.md``/``SKILL.md``). O conteúdo vira um "perfil de especialista" que é
injetado no prompt da etapa.
"""

from __future__ import annotations

from pathlib import Path


def strip_frontmatter(text: str) -> str:
    """Remove o frontmatter YAML (``---``) e devolve apenas o corpo do documento."""
    if not text.lstrip().startswith("---"):
        return text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text.strip()
    return parts[2].strip()


def load_skill(iaw_dir: Path, name: str) -> str | None:
    """Lê o corpo do SKILL.md de uma skill (``.iaw/skills/<name>/SKILL.md``)."""
    skill_file = iaw_dir / "skills" / name / "SKILL.md"
    if skill_file.is_file():
        return strip_frontmatter(skill_file.read_text(encoding="utf-8"))
    return None


def load_agent(iaw_dir: Path, name: str) -> str | None:
    """Lê o corpo de um agente (``.iaw/agents/<name>.md`` ou diretório)."""
    agents_dir = iaw_dir / "agents"
    candidates = [
        agents_dir / f"{name}.md",
        agents_dir / name / "AGENT.md",
        agents_dir / name / "SKILL.md",
        agents_dir / name / "agent.md",
    ]
    for path in candidates:
        if path.is_file():
            return strip_frontmatter(path.read_text(encoding="utf-8"))
    return None


def resolve_expertise(
    iaw_dir: Path,
    *,
    skill: str | None = None,
    agent: str | None = None,
) -> tuple[str | None, str | None]:
    """Retorna ``(rótulo, instrução)`` do especialista indicado no step.

    :raises FileNotFoundError: se a skill/agent referenciada não existir.
    """
    if skill:
        body = load_skill(iaw_dir, skill)
        if body is None:
            raise FileNotFoundError(
                f"Skill '{skill}' não encontrada em .iaw/skills/{skill}/SKILL.md."
            )
        return skill, body
    if agent:
        body = load_agent(iaw_dir, agent)
        if body is None:
            raise FileNotFoundError(
                f"Agent '{agent}' não encontrado em .iaw/agents/ (procure por "
                f"{agent}.md ou {agent}/AGENT.md)."
            )
        return agent, body
    return None, None
