"""Criação e relatório de work items (Tasks/Issues) no GitLab.

Convenções usadas pelo ``iaw create`` e pelo ``iaw relatorio tasks``:

- Todo work item recebe o label do mês/ano atual (ex: ``SET/2026``).
- ``--task`` cria um work item do tipo **Task**.
    - Sem ``--demanda``: categoria **task geral** (apenas label do mês).
    - Com ``--demanda``: categoria **demanda** (label ``demandas`` + mês).
- ``--issue`` cria um work item do tipo **Issue** com label ``bug`` (categoria **erro**).

As categorias do relatório são inferidas dos labels e do ``issue_type``.

O relatório mensal filtra por **label do mês** (ex.: ``SET/2026``) **e** pela
**data de fechamento** (``closed_at``) dentro daquele mês.
"""

from __future__ import annotations

from datetime import datetime, timezone
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


def parse_month_label(label: str) -> tuple[int, int] | None:
    """Converte um label de mês (``AGO/2026``) em ``(ano, mês)``.

    Retorna ``None`` se o label não seguir o padrão ``MES/ANO``.
    """
    parts = (label or "").strip().upper().split("/")
    if len(parts) != 2 or parts[0] not in MESES_ABREV:
        return None
    try:
        year = int(parts[1])
    except ValueError:
        return None
    return year, MESES_ABREV.index(parts[0]) + 1


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """Retorna o intervalo [início, fim) do mês, em UTC."""
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _closed_at(item: Any) -> datetime | None:
    """Extrai a data de fechamento de um work item como datetime aware (UTC)."""
    raw = getattr(item, "closed_at", None)
    if not raw:
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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
    """Lista work items fechados do mês e retorna ``(item, categoria)``.

    O mês é definido pelo **label** (ex.: ``SET/2026``) e confirmado pela
    **data de fechamento** (``closed_at``) do item — ou seja, o item precisa
    ter o label do mês **e** ter sido fechado dentro daquele mês.
    """
    config = cfg.load_config()
    pid = project_id or config.get("gitlab_project") or ""
    if not pid:
        raise GitLabError(
            "Projeto GitLab não configurado. Use `--project-id <path>` ou "
            "`iaw config set gitlab_project <path>`."
        )

    parsed = parse_month_label(label)
    if parsed is None:
        raise GitLabError(
            f"Label de mês inválido: '{label}'. Use o formato MES/ANO (ex.: SET/2026)."
        )
    year, month = parsed
    start, end = _month_bounds(year, month)

    client = GitLabClient()
    items = client.list_issues(pid, state="closed", labels=label)

    resultado: list[tuple[Any, str]] = []
    for item in items:
        closed = _closed_at(item)
        if closed is not None and start <= closed < end:
            resultado.append((item, classify_work_item(item)))
    return resultado
