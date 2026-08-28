"""Instalação de hooks Git do iaw.

`iaw install-hooks` grava o hook de pre-commit que roda os evals das skills
alteradas antes de permitir o commit (bloqueia regressões).
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

from . import project

HOOK_SCRIPT = """#!/usr/bin/env bash
# Hook instalado pelo iaw (iaw install-hooks).
# Roda os evals das skills alteradas no commit e bloqueia regressões.
set -euo pipefail

changed_skills=$(git diff --cached --name-only 2>/dev/null \\
  | grep -E '^\\.iaw/skills/[^/]+/' \\
  | sed -E 's|\\.iaw/skills/([^/]+)/.*|\\1|' \\
  | sort -u || true)

if [ -z "$changed_skills" ]; then
  exit 0
fi

for skill in $changed_skills; do
  echo "iaw: rodando evals da skill '$skill'..."
  if ! iaw eval "$skill"; then
    echo "Commit bloqueado: a skill '$skill' regrediu nos evals."
    echo "Corrija a skill ou rode 'iaw eval $skill --update-baseline' se a mudança for intencional."
    exit 1
  fi
done
"""


def write_hook_source() -> Path:
    """Grava o hook-fonte em `.iaw/hooks/pre-commit-eval`."""
    project.ensure_structure()
    path = project.IAW_DIR / "hooks" / "pre-commit-eval"
    path.write_text(HOOK_SCRIPT, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def install_precommit_hook(force: bool = False) -> str:
    """Instala o hook em `.git/hooks/pre-commit`.

    :return: mensagem descrevendo o resultado.
    """
    git_dir = Path(".git")
    if not git_dir.is_dir():
        return "Não é um repositório Git (`.git/` não encontrado)."

    source = write_hook_source()
    dest = git_dir / "hooks" / "pre-commit"

    if dest.exists() and not force:
        return (
            f"Já existe um hook em {dest}. Para não sobrescrever, nada foi feito.\n"
            f"O hook-fonte está em {source}. Rode `iaw install-hooks --force` para "
            "substituir, ou integre-o manualmente ao seu pre-commit existente."
        )

    shutil.copy2(source, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return f"Hook de pre-commit instalado em {dest}."
