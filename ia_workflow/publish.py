"""Publicação da tarefa (resumo + MR + relatório PGD).

Fluxo usado pelo `iaw finish-task` e pelo step `generate_summary_and_publish`
dos workflows: gera o diff, pede o resumo executivo à IA, abre o MR no GitLab
e anexa a atividade no relatório mensal.
"""

from __future__ import annotations

import subprocess

from rich.console import Console

from . import config_manager as cfg
from . import reports
from . import workspace
from .engines import build_engine
from .gitlab_client import GitLabClient, GitLabError

console = Console()

def workspace_context() -> dict:
    """Lê o contexto da tarefa salvo por `iaw start-task` (se existir)."""
    task_dir = workspace.find_task_dir()
    if task_dir is None:
        return {}
    return workspace.load_context(task_dir)


def get_current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def infer_issue_id() -> int | None:
    """Tenta inferir o id da Issue (branch `iaw/issue-4512` ou contexto salvo)."""
    return workspace.infer_issue_id()


def get_git_diff(target_branch: str = "master") -> str:
    """Retorna o diff da branch atual contra a base (fallback para `git diff HEAD`)."""
    result = subprocess.run(
        ["git", "diff", f"origin/{target_branch}...HEAD"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        result = subprocess.run(
            ["git", "diff", "HEAD"], capture_output=True, text=True
        )
    return result.stdout


def infer_module(diff: str) -> str:
    """Infere o módulo (app Django) a partir dos caminhos alterados no diff."""
    import re

    paths = re.findall(r"^diff --git a/([^/\s]+)/", diff, re.MULTILINE)
    if not paths:
        return ""
    # Módulo mais frequente, ignorando diretórios de config.
    from collections import Counter

    ignored = {".iaw", ".iaw_workspace", "docs", ".github", ".gitlab"}
    counts = Counter(p for p in paths if p not in ignored)
    return counts.most_common(1)[0][0] if counts else paths[0]


def generate_summary(diff: str) -> str:
    """Pede à IA um resumo executivo do diff."""
    if not diff.strip():
        return "(sem alterações de código detectadas)"

    engine = build_engine()
    prompt = (
        "Gere um resumo executivo em pt-BR das alterações abaixo, explicando "
        "a causa raiz resolvida, os arquivos modificados e o impacto no negócio. "
        "Seja objetivo (2 a 4 frases).\n\n"
        f"```diff\n{diff[:20000]}\n```"
    )
    result = engine.generate(prompt)
    if result.success and result.output:
        return result.output
    return "(não foi possível gerar o resumo automático)"


def create_merge_request(issue_id: int, summary: str, target_branch: str) -> str:
    """Abre o MR no GitLab e retorna a URL."""
    client = GitLabClient()
    config = cfg.load_config()
    project_id = config.get("gitlab_project") or ""
    if not project_id:
        raise GitLabError("Projeto GitLab não configurado (`iaw config set gitlab_project <path>`).")

    source_branch = get_current_branch()
    module = infer_module(get_git_diff(target_branch))
    title = f"[{module}] " if module else ""
    title += f"Issue #{issue_id}: {summary.splitlines()[0][:60]}"

    description = (
        f"# Descrição\n\n## Sumário\n{summary}\n\n"
        f"Closes #{issue_id}\n\nChangelog: fixed\n"
    )

    mr = client.create_merge_request(
        project_id,
        source_branch=source_branch,
        target_branch=target_branch,
        title=title,
        description=description,
    )
    return getattr(mr, "web_url", "")


def publish_task(
    *,
    issue_id: int | None = None,
    summary: str | None = None,
    target_branch: str = "master",
    create_mr: bool = True,
) -> dict:
    """Executa o fluxo de encerramento e retorna um resumo do que foi feito."""
    issue_id = issue_id or infer_issue_id()
    if issue_id is None:
        raise ValueError(
            "Não foi possível inferir o id da Issue. Informe com `--issue-id <id>`."
        )

    diff = get_git_diff(target_branch)
    summary = summary or generate_summary(diff)

    mr_url = ""
    if create_mr:
        mr_url = create_merge_request(issue_id, summary, target_branch)
        console.print(f"[green]✓[/green] Merge Request criado: [cyan]{mr_url}[/cyan]")

    report_path = reports.append_activity(issue_id=issue_id, summary=summary, mr_url=mr_url)
    console.print(f"[green]✓[/green] Atividade registrada em [cyan]{report_path}[/cyan]")

    return {"issue_id": issue_id, "summary": summary, "mr_url": mr_url, "report": str(report_path)}


def cleanup_workspace(keep: bool = False, issue_id: int | None = None) -> None:
    """Remove a pasta transitória da tarefa (ou todo `.iaw_workspace/`)."""
    if keep:
        return
    import shutil

    target = workspace.task_dir(issue_id) if issue_id is not None else workspace.WORKSPACE_ROOT
    if target.exists():
        shutil.rmtree(target)
        console.print(f"[dim]Workspace transitório removido ({target}).[/dim]")
