"""Gerenciador de Skills do iaw.

As skills vivem em `.iaw/skills/<nome>/SKILL.md` (formato canônico, com
frontmatter YAML). Este módulo lista, adiciona e atualiza skills a partir de
um repositório central (local ou Git).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import config_manager as cfg
from . import project


@dataclass
class SkillInfo:
    name: str
    description: str
    path: Path


def parse_frontmatter(text: str) -> dict:
    """Extrai o frontmatter YAML de um SKILL.md (se houver)."""
    if not text.lstrip().startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _flatten(value: str | None) -> str:
    """Achata a descrição (que pode ser multi-linha) para exibição."""
    if not value:
        return ""
    return " ".join(value.split())


def list_skills(iaw_dir: Path) -> list[SkillInfo]:
    """Lista as skills presentes em `.iaw/skills/`."""
    skills_dir = iaw_dir / "skills"
    if not skills_dir.is_dir():
        return []
    result: list[SkillInfo] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if skill_dir.is_dir() and skill_file.is_file():
            fm = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
            result.append(
                SkillInfo(
                    name=fm.get("name", skill_dir.name),
                    description=_flatten(fm.get("description")),
                    path=skill_dir,
                )
            )
    return result


def _fetch_source(source: str, dest: Path) -> None:
    """Copia o repositório/fonte de skills para `dest`.

    Suporta caminho local ou URL Git (clone raso).
    """
    if source.startswith(("http://", "https://", "git@", "ssh://")):
        subprocess.run(
            ["git", "clone", "--depth", "1", source, str(dest)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        src = Path(source).expanduser()
        if not src.is_dir():
            raise FileNotFoundError(f"Fonte de skills não encontrada: {src}")
        shutil.copytree(src, dest, dirs_exist_ok=True)


def _find_skill_in_source(source_dir: Path, name: str) -> Path | None:
    """Localiza uma skill pelo nome dentro da fonte (procurando SKILL.md)."""
    for candidate in source_dir.rglob("SKILL.md"):
        fm = parse_frontmatter(candidate.read_text(encoding="utf-8"))
        if fm.get("name") == name or candidate.parent.name == name:
            return candidate.parent
    return None


def add_skill(name: str, source: str | None = None, overwrite: bool = False) -> Path:
    """Adiciona uma skill ao `.iaw/skills/` a partir da fonte central."""
    source = source or cfg.get("skill_repo", "")
    if not source:
        raise ValueError(
            "Nenhuma fonte de skills configurada. Use `--source <path|url>` ou "
            "`iaw config set skill_repo <path|url>`."
        )

    dest_skill = project.IAW_DIR / "skills" / name
    if dest_skill.exists() and not overwrite:
        raise FileExistsError(f"Skill '{name}' já existe em {dest_skill}.")

    with tempfile.TemporaryDirectory(prefix="iaw-skills-") as tmp:
        tmp_dir = Path(tmp)
        _fetch_source(source, tmp_dir / "src")
        skill_dir = _find_skill_in_source(tmp_dir / "src", name)
        if skill_dir is None:
            raise FileNotFoundError(f"Skill '{name}' não encontrada na fonte '{source}'.")
        if dest_skill.exists() and overwrite:
            shutil.rmtree(dest_skill)
        shutil.copytree(skill_dir, dest_skill)

    return dest_skill


def update_skills(source: str | None = None, overwrite: bool = True) -> list[Path]:
    """Atualiza as skills existentes a partir da fonte central."""
    source = source or cfg.get("skill_repo", "")
    if not source:
        raise ValueError(
            "Nenhuma fonte de skills configurada. Use `--source <path|url>` ou "
            "`iaw config set skill_repo <path|url>`."
        )

    updated: list[Path] = []
    for info in list_skills(project.IAW_DIR):
        updated.append(add_skill(info.name, source=source, overwrite=overwrite))
    return updated
