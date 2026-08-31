"""Resolução de skills/agents especialistas para as etapas de um workflow.

Cada step YAML pode indicar ``skill: <nome>`` (lê ``.iaw/skills/<nome>/SKILL.md``)
ou ``agent: <nome>`` (lê ``.iaw/agents/<nome>.md`` — ou um diretório com
``AGENT.md``/``SKILL.md``). O conteúdo vira um "perfil de especialista" que é
injetado no prompt da etapa.

Se a skill/agent indicada não existir, o `iaw` **não falha**: usa a skill
padrão (``.iaw/skills/default/SKILL.md``) ou, na ausência dela, um perfil
genérico embutido — sempre com um aviso no prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_EXPERTISE_BODY = (
    "# Perfil padrão (full-stack)\n\n"
    "Você é um desenvolvedor sênior full-stack. Trabalhe de forma incremental, "
    "respeite a arquitetura existente do projeto e as diretrizes de `stack.md` "
    "e `contexto.md`. Não introduza bibliotecas/padrões externos sem aprovação. "
    "Prefira código simples, testável e em pt-BR."
)


@dataclass
class Expertise:
    """Resultado da resolução de especialista."""

    label: str
    body: str
    fallback: bool = False
    requested: str = ""


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


def _fallback(iaw_dir: Path, requested: str) -> Expertise:
    """Resolve a skill padrão (ou o perfil embutido) quando a indicada não existe."""
    default = load_skill(iaw_dir, "default")
    if default:
        return Expertise("default", default, fallback=True, requested=requested)
    return Expertise("default", DEFAULT_EXPERTISE_BODY, fallback=True, requested=requested)


def resolve_expertise(
    iaw_dir: Path,
    *,
    skill: str | None = None,
    agent: str | None = None,
) -> Expertise:
    """Resolve o especialista de um step.

    - Se ``skill``/``agent`` existir, retorna o corpo encontrado.
    - Se não existir, cai para a skill padrão com ``fallback=True``.
    - Se nenhum for indicado, retorna corpo vazio (sem especialista).
    """
    if skill:
        body = load_skill(iaw_dir, skill)
        if body:
            return Expertise(skill, body)
        return _fallback(iaw_dir, skill)
    if agent:
        body = load_agent(iaw_dir, agent)
        if body:
            return Expertise(agent, body)
        return _fallback(iaw_dir, agent)
    return Expertise("", "")
