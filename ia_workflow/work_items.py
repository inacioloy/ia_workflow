"""Criação e relatório de work items (Tasks/Issues) no GitLab.

Convenções usadas pelo ``iaw create`` e pelo ``iaw relatorio tasks``:

- Todo work item recebe o label do mês/ano atual (ex: ``SET/2026``).
- ``--task`` cria um work item do tipo **Task**.
    - Sem ``--demanda``: categoria **task geral** (apenas label do mês).
    - Com ``--demanda``: categoria **demanda** (label ``demandas`` + mês).
- ``--issue`` cria um work item do tipo **Issue** com label ``bug`` (categoria **erro**).

As categorias do relatório são inferidas dos labels e do ``issue_type``.

O relatório mensal restringe aos itens em que o usuário do token é **autor** ou
**assignee**. Um item pertence ao mês se **tiver o label do mês** (ex.:
``SET/2026``) — prioridade — **ou** se tiver sido **fechado** (``closed_at``)
dentro daquele mês.
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

PAPEL_AUTOR = "autor"
PAPEL_ASSIGNEE = "resolvido por"
PAPEL_AMBOS = "autor e resolvido por"


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


def _has_label(item: Any, target: str) -> bool:
    """Verifica se o item possui o label informado (case-insensitive)."""
    target = (target or "").strip().lower()
    return any(
        str(l).strip().lower() == target
        for l in (getattr(item, "labels", None) or [])
    )


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


def _user_id(value: Any) -> Any:
    """Extrai o id de um usuário (dict ou objeto do python-gitlab)."""
    if isinstance(value, dict):
        return value.get("id")
    return getattr(value, "id", None)


def user_role(item: Any, user_id: Any) -> str | None:
    """Indica o papel do usuário no item: 'autor', 'resolvido por' ou ambos.

    Retorna ``None`` se o usuário não for autor nem assignee.
    """
    author_id = _user_id(getattr(item, "author", None))
    assignee_ids = [_user_id(a) for a in (getattr(item, "assignees", None) or [])]
    if not assignee_ids:
        single = _user_id(getattr(item, "assignee", None))
        if single is not None:
            assignee_ids = [single]

    is_author = author_id == user_id
    is_assignee = user_id in assignee_ids

    if is_author and is_assignee:
        return PAPEL_AMBOS
    if is_author:
        return PAPEL_AUTOR
    if is_assignee:
        return PAPEL_ASSIGNEE
    return None


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
) -> dict[str, Any]:
    """Lista os work items do usuário do token para o mês indicado.

    Um item entra no relatório se **tiver o label do mês** (ex.: ``AGO/2026``)
    **ou** se tiver sido **fechado** dentro daquele mês (``closed_at``). O label
    tem prioridade: mesmo que o fechamento tenha ocorrido em outro mês, o item
    com o label do mês é incluído.

    Retorna um dicionário com:

    - ``items``: lista de ``(item, categoria, papel)`` — apenas itens em que o
      usuário do token é **autor** ou **assignee**;
    - ``username``: login do usuário do token (para exibição).
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
    user = client.current_user()
    user_id = user.id
    username = getattr(user, "username", "") or "você"

    # Busca apenas os itens do usuário (autor OU assignee) e faz o merge por iid.
    authored = client.list_issues(pid, state="closed", author_id=user_id)
    assigned = client.list_issues(pid, state="closed", assignee_id=user_id)
    by_iid: dict[Any, Any] = {}
    for item in authored + assigned:
        by_iid[getattr(item, "iid", None)] = item

    resultado: list[tuple[Any, str, str]] = []
    for item in by_iid.values():
        closed = _closed_at(item)
        in_month = closed is not None and start <= closed < end
        # Prioridade: label do mês; senão, data de fechamento dentro do mês.
        if not (_has_label(item, label) or in_month):
            continue
        papel = user_role(item, user_id)
        if papel is None:
            continue
        resultado.append((item, classify_work_item(item), papel))

    # Mais recentes primeiro, para facilitar a leitura.
    resultado.sort(key=lambda t: getattr(t[0], "iid", 0), reverse=True)
    return {"items": resultado, "username": username}
