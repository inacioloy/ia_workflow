"""Workspace transitório por tarefa e progresso de execução.

Centraliza onde o `iaw` grava os artefatos de uma tarefa e o ``state.json`` que
permite retomar um workflow de onde parou (``iaw run --resume``).

Layout (por tarefa = 1 Issue):

    .iaw_workspace/
      issue-4512/
        contexto.json        # issue_id, title, project_id (escrito pelo start-task)
        state.json           # workflow + passos concluídos + alvo de testes
        1_requisitos_validados.md
        1_diagnostico_bug.md
        ...

A pasta `.iaw_workspace/` é transitória e deve ficar no `.gitignore`.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(".iaw_workspace")
STATE_FILE = "state.json"
CONTEXT_FILE = "contexto.json"


def _read_json(path: Path) -> dict:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def get_current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def infer_issue_id() -> int | None:
    """Inferir o id da Issue pela branch (`iaw/issue-4512`) ou pelo contexto salvo."""
    branch = get_current_branch()
    match = re.search(r"issue[-_]?(\d+)", branch, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # Layout por tarefa: issue-<id>/contexto.json
    for ctx in sorted(WORKSPACE_ROOT.glob("*/contexto.json")):
        data = _read_json(ctx)
        if data.get("issue_id"):
            return int(data["issue_id"])

    # Layout legado (flat): .iaw_workspace/contexto.json
    data = _read_json(WORKSPACE_ROOT / CONTEXT_FILE)
    if data.get("issue_id"):
        return int(data["issue_id"])
    return None


def task_dir(issue_id: int) -> Path:
    """Diretório transitório da tarefa."""
    return WORKSPACE_ROOT / f"issue-{issue_id}"


def find_task_dir() -> Path | None:
    """Localiza o diretório da tarefa atual (branch → contexto)."""
    issue_id = infer_issue_id()
    if issue_id is not None:
        candidate = task_dir(issue_id)
        if candidate.is_dir():
            return candidate

    # Se só existir uma tarefa no workspace, assume-a.
    candidates = sorted(WORKSPACE_ROOT.glob("issue-*/"))
    if len(candidates) == 1:
        return candidates[0]
    return None


def load_context(task_dir: Path) -> dict:
    """Lê o contexto da tarefa (`contexto.json`)."""
    return _read_json(task_dir / CONTEXT_FILE)


def load_progress(task_dir: Path) -> dict:
    """Lê o progresso da tarefa (`state.json`)."""
    return _read_json(task_dir / STATE_FILE)


def save_progress(
    task_dir: Path,
    *,
    workflow: str,
    issue_id: int | None,
    completed_steps: list[str],
    next_step: str | None = None,
    test_target: str = "",
) -> None:
    """Grava o progresso da tarefa para permitir `iaw run --resume`."""
    task_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "issue_id": issue_id,
        "workflow": workflow,
        "completed_steps": completed_steps,
        "next_step": next_step,
        "test_target": test_target,
    }
    (task_dir / STATE_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
