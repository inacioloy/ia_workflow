"""Criação e relatório de work items (Tasks/Issues) no GitLab.

Convenções usadas pelo ``iaw create`` e pelo ``iaw relatorio tasks``:

- Todo work item recebe o label do mês/ano atual (ex: ``SET/2026``).
- ``--task`` cria um work item do tipo **Task**.
    - Sem ``--demanda``: categoria **task geral** (apenas label do mês).
    - Com ``--demanda``: categoria **demanda** (label ``demandas`` + mês).
- ``--issue`` cria um work item do tipo **Issue** com label ``bug`` (categoria **erro**).

As categorias do relatório são inferidas dos labels e do ``issue_type``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import config_manager as cfg
from .gitlab_client import GitLabClient, GitLabError

LABEL_DEMANDAS = "demandas"
LABEL_BUG = "bug"

# Abreviações em português usadas no label mensal (ex: SET/2026).
MESES_ABREV = [
    "JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
    "JUL", "AGO", "SET", "OUT", "NOV", "DEZ",
]

CATEGORIA_TASK_GERAL = "task geral"
CATEGORIA_DEMANDA = "demanda"
CATEGORIA_ERRO = "erro"


def current_month_label(now: datetime | None = None) -> str:
    """Retorna o label do mês atual no formato ``SET/2026``."""
    now = now or datetime.now()
    return f"{MESES_ABREV[now.month - 1]}/{now.year}"


def classify_work_item(item: Any) -> str:
    """Classifica um work item fechado como 'task geral', 'demanda' ou 'erro'."""
    labels = {str(l).lower() for l in (getattr(item, "labels", None) or [])}
    issue_type = str(getattr(item, "issue_type", "") or "").lower()

    if LABEL_BUG in labels:
        return CATEGORIA_ERRO
    if LABEL_DEMANDAS in labels:
        return CATEGORIA_DEMANDA
    if issue_type == "issue":
        return CATEGORIA_ERRO
    return CATEGORIA_TASK_GERAL


def item_type_label(item: Any) -> str:
    """Retorna 'Task' ou 'Issue' para exibição no relatório."""
    return "Task" if str(getattr(item, "issue_type", "") or "").lower() == "task" else "Issue"


def create_work_item(
    *,
    title: str,
    kind: str,
    demanda: bool = False,
    project_id: str | None = None,
) -> Any:
    """Cria um work item no projeto GitLab com assignee = usuário atual.

    ``kind`` deve ser ``"task"`` ou ``"issue"``.
    """
    if kind not in {"task", "issue"}:
        raise ValueError("kind deve ser 'task' ou 'issue'.")

    config = cfg.load_config()
    pid = project_id or config.get("gitlab_project") or ""
    if not pid:
        raise GitLabError(
            "Projeto GitLab não configurado. Use `--project-id <path>` ou "
            "`iaw config set gitlab_project <path>`."
        )

    labels = [current_month_label()]
    issue_type = "issue"

    if kind == "task":
        issue_type = "task"
        if demanda:
            labels.append(LABEL_DEMANDAS)
    else:
        labels.append(LABEL_BUG)

    client = GitLabClient()
    return client.create_issue(
        pid,
        title=title,
        labels=labels,
        issue_type=issue_type,
    )


def list_closed_work_items(
    *,
    label: str,
    project_id: str | None = None,
) -> list[tuple[Any, str]]:
    """Lista work items fechados do mês (label) e retorna ``(item, categoria)``."""
    config = cfg.load_config()
    pid = project_id or config.get("gitlab_project") or ""
    if not pid:
        raise GitLabError(
            "Projeto GitLab não configurado. Use `--project-id <path>` ou "
            "`iaw config set gitlab_project <path>`."
        )

    client = GitLabClient()
    items = client.list_issues(pid, state="closed", labels=label)
    return [(item, classify_work_item(item)) for item in items]
