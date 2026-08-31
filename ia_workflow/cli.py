"""CLI principal do IA Workflow (iaw).

Todos os comandos possuem help text próprio (`iaw <comando> --help`) e há um
comando de ajuda detalhada (`iaw help [comando]`).
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt

from . import __version__
from . import config_manager as cfg
from . import evals
from . import help_texts
from . import hooks
from . import importer
from . import notify
from . import project
from . import publish
from . import runner
from . import skills as skills_mod
from . import state
from . import workspace
from .engines import available_engines
from .gitlab_client import GitLabClient, GitLabError
from .workflow_parser import WorkflowError, available_workflows

app = typer.Typer(
    name="iaw",
    help="IA Workflow: orquestrador de IA para o IFRN (Artifact-Driven + Graph Engineering).",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Gerencia a configuração global (~/.config/ia_workflow/config.toml).")
app.add_typer(config_app, name="config")

skill_app = typer.Typer(help="Gerencia as skills do projeto (.iaw/skills/).")
app.add_typer(skill_app, name="skill")

console = Console()


# --------------------------------------------------------------------------- #
# setup / config
# --------------------------------------------------------------------------- #
@app.command(help="Configura as credenciais globais da ferramenta (token GitLab, engine, PGD).")
def setup() -> None:
    """Configura as credenciais globais da ferramenta (uma única vez)."""
    console.print("[bold blue]=== Configuração do IA Workflow (iaw) ===[/bold blue]\n")

    token = typer.prompt("Personal Access Token do GitLab", hide_input=True, default="")
    gitlab_url = typer.prompt(
        "URL do GitLab", default="https://gitlab.ifrn.edu.br"
    )
    gitlab_project = typer.prompt(
        "Projeto padrão no GitLab (path, ex: cosinf/suap)", default=""
    )
    engine = typer.prompt(
        "Motor padrão de IA", default="pi-coding"
    )
    if engine not in available_engines():
        console.print(
            f"[yellow]Aviso:[/yellow] '{engine}' não é um motor reconhecido "
            f"({', '.join(available_engines())}). Você poderá corrigir com `iaw config set default_engine <nome>`."
        )
    dev_name = typer.prompt("Seu nome (para o relatório PGD)", default="")
    pgd_path = typer.prompt(
        "Diretório dos relatórios PGD", default=cfg.REPORTS_DIR.as_posix()
    )

    updates = {
        "gitlab_url": gitlab_url,
        "gitlab_token": token,
        "gitlab_project": gitlab_project,
        "default_engine": engine,
        "dev_name": dev_name,
        "pgd_report_path": pgd_path,
    }
    config = cfg.load_config()
    config.update(updates)
    cfg.save_config(config)

    console.print(
        f"\n[bold green]Configuração salva em[/bold green] [cyan]{cfg.CONFIG_PATH}[/cyan]\n"
    )


@config_app.command("set", help="Define uma chave na configuração global.")
def config_set(chave: str, valor: str) -> None:
    """Define uma chave na configuração global. Ex: iaw config set default_engine aider"""
    cfg.set(chave, valor)
    console.print(f"[green]✓[/green] {chave} = {valor}")


@config_app.command("get", help="Lê uma chave da configuração global.")
def config_get(chave: str) -> None:
    """Lê uma chave da configuração global."""
    valor = cfg.get(chave)
    if valor is None:
        console.print(f"[yellow]Chave '{chave}' não encontrada.[/yellow]")
        raise typer.Exit(code=1)
    # Não imprime o token completo por segurança.
    if chave == "gitlab_token" and valor:
        valor = valor[:4] + "..." + valor[-4:] if len(valor) > 8 else "***"
    console.print(f"{chave} = {valor}")


@config_app.command("list", help="Lista a configuração global (token mascarado).")
def config_list() -> None:
    """Lista a configuração global (token mascarado)."""
    config = cfg.load_config()
    for key, value in config.items():
        if key == "gitlab_token" and value:
            value = value[:4] + "..." + value[-4:] if len(str(value)) > 8 else "***"
        console.print(f"[cyan]{key}[/cyan] = {value}")


@skill_app.command("list", help="Lista as skills instaladas em .iaw/skills/.")
def skill_list() -> None:
    """Lista as skills instaladas em .iaw/skills/."""
    skills = skills_mod.list_skills(project.IAW_DIR)
    if not skills:
        console.print("Nenhuma skill encontrada em .iaw/skills/.")
        console.print("Use `iaw skill add <nome> --source <path|url>` para instalar.")
        return
    for s in skills:
        desc = s.description[:80] + "..." if len(s.description) > 80 else s.description
        console.print(f"[cyan]{s.name}[/cyan] — {desc}")


@skill_app.command("add", help="Adiciona uma skill ao projeto a partir de uma fonte central.")
def skill_add(
    name: str,
    source: str = typer.Option(None, "--source", help="Caminho ou URL Git da fonte de skills."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Sobrescreve a skill se já existir."),
) -> None:
    """Adiciona uma skill ao projeto a partir de uma fonte central."""
    try:
        dest = skills_mod.add_skill(name, source=source, overwrite=overwrite)
        console.print(f"[green]✓[/green] Skill '[cyan]{name}[/cyan]' instalada em {dest}")
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@skill_app.command("update", help="Atualiza as skills instaladas a partir da fonte central.")
def skill_update(
    source: str = typer.Option(None, "--source", help="Caminho ou URL Git da fonte de skills."),
) -> None:
    """Atualiza as skills instaladas a partir da fonte central."""
    try:
        updated = skills_mod.update_skills(source=source)
        console.print(f"[green]✓[/green] {len(updated)} skill(s) atualizada(s).")
    except ValueError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc


# --------------------------------------------------------------------------- #
# Comandos das fases seguintes (esqueleto)
# --------------------------------------------------------------------------- #
@app.command("import-legacy", help="Importa skills/agents/hooks do legado para .iaw/ (não apaga nada).")
def import_legacy(
    source: str = typer.Option(".", "--source", help="Diretório raiz do projeto legado."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Apenas lista o que será copiado, sem escrever."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Sobrescreve arquivos já existentes em .iaw/."),
) -> None:
    """Importa skills/agents/hooks do legado para .iaw/ (nunca apaga o legado)."""
    root = Path(source)
    if not root.is_dir():
        console.print(f"[red]Erro:[/red] diretório '{source}' não encontrado.")
        raise typer.Exit(code=1)
    importer.import_legacy(root, dry_run=dry_run, overwrite=overwrite)
    if not dry_run:
        console.print(
            "\n[bold green]Importação concluída.[/bold green] Os diretórios legados "
            "(.agents/, .claude/, .opencode/) foram mantidos intactos."
        )


@app.command(help="Cria/reconfigura a pasta .iaw/ no projeto atual.")
def init() -> None:
    """Inicializa/reconfigura o diretório .iaw/ no projeto atual."""
    console.print(
        "[bold blue]=== Assistente de Inicialização do IA Workflow (iaw) ===[/bold blue]\n"
    )
    if project.IAW_DIR.exists():
        console.print("[yellow]O diretório .iaw/ já existe neste projeto.[/yellow]")
        if not Confirm.ask("Deseja reconfigurar a Stack?", default=False):
            console.print("Operação cancelada.")
            raise typer.Exit()

    stack = Prompt.ask(
        "Qual a stack principal deste projeto?", default="Python, Django, PostgreSQL"
    )
    testes = Prompt.ask("Onde ficam os testes automatizados?", default="pytest")

    project.init_project(stack, testes)
    console.print(
        f"\n[bold green]Sucesso![/bold green] Diretório [cyan].iaw/[/cyan] criado e configurado "
        f"para {stack}."
    )
    console.print("Revise os arquivos gerados e faça commit no Git.")


@app.command("start-task", help="Inicia uma tarefa a partir de uma Issue do GitLab (Task-First).")
def start_task(
    issue_id: int,
    project_id: str = typer.Option(
        None, "--project-id", help="Path do projeto no GitLab (ex: cosinf/suap)."
    ),
) -> None:
    """Inicia uma tarefa a partir de uma Issue do GitLab (Task-First)."""
    config = cfg.load_config()
    pid = project_id or config.get("gitlab_project") or ""
    if not pid:
        console.print(
            "[red]Erro:[/red] projeto não informado. Use `--project-id <path>` ou "
            "configure com `iaw config set gitlab_project <path>`."
        )
        raise typer.Exit(code=1)

    client = GitLabClient()
    try:
        issue = client.get_issue(pid, issue_id)
    except GitLabError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    task_dir = workspace.task_dir(issue_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    stack = ""
    stack_path = project.IAW_DIR / "stack.md"
    if stack_path.exists():
        stack = stack_path.read_text(encoding="utf-8")

    conteudo = (
        f"# Requisitos Validados — Issue #{issue_id}\n\n"
        f"## Título\n{issue.title}\n\n"
        f"## Descrição\n{issue.description or '(sem descrição)'}\n\n"
        f"## Contexto do projeto (.iaw/stack.md)\n\n{stack}\n"
    )
    artefato = task_dir / "1_requisitos_validados.md"
    artefato.write_text(conteudo, encoding="utf-8")

    # Salva o contexto da tarefa para o finish-task/publish.
    contexto = {"issue_id": issue_id, "title": issue.title, "project_id": pid}
    (task_dir / "contexto.json").write_text(
        json.dumps(contexto, ensure_ascii=False), encoding="utf-8"
    )

    # Inicializa o progresso (state.json) para permitir `iaw run --resume`.
    workspace.save_progress(task_dir, workflow="", issue_id=issue_id, completed_steps=[])

    console.print(
        f"[green]✓[/green] Artefato inicial gerado em [cyan]{artefato}[/cyan]"
    )
    console.print("Revise o artefato e execute `iaw run` para acionar a IA.")


@app.command(help="Orquestra a IA pelo workflow YAML (.iaw/workflows).")
def run(
    workflow: str = typer.Option("nova_feature", help="Workflow YAML a executar (sem extensão)."),
    issue_id: int = typer.Option(
        None,
        "--issue-id",
        "--task",
        help="Id da Issue/tarefa a executar (senão infere da branch ou do workspace).",
    ),
    detach: bool = typer.Option(False, "--detach", help="Executa em background (Fase 4)."),
    notify: bool = typer.Option(False, "--notify", help="Notifica ao terminar."),
    resume: bool = typer.Option(False, "--resume", help="Retoma pulando etapas já concluídas (state.json)."),
    log: bool = typer.Option(False, "--log", help="Mostra o log de execução da IA (prompt, contexto e saída)."),
    no_publish: bool = typer.Option(
        False,
        "--no-publish",
        "--local",
        help="Não cria MR nem registra no PGD (pula a etapa de publicação).",
    ),
) -> None:
    """Aciona o motor de IA para rodar o fluxo definido em .iaw/workflows."""
    if not (project.IAW_DIR / "workflows" / f"{workflow}.yaml").is_file():
        console.print(f"[red]Erro:[/red] workflow '{workflow}' não encontrado em .iaw/workflows/.")
        disponiveis = available_workflows(project.IAW_DIR)
        if disponiveis:
            console.print(f"Disponíveis: {', '.join(disponiveis)}")
        raise typer.Exit(code=1)

    resolved_issue = issue_id or publish.infer_issue_id()
    store = state.TaskStore()
    task = store.add(workflow, issue_id=resolved_issue)
    try:
        exit_code = runner.run_workflow(
            workflow,
            detach=detach,
            notify=notify,
            resume=resume,
            issue_id=issue_id,
            log=log,
            no_publish=no_publish,
        )
    except WorkflowError as exc:
        store.update(task.id, status=state.STATUS_FAILED)
        console.print(f"[red]Erro no workflow:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    final_status = state.STATUS_SUCCESS if exit_code == 0 else state.STATUS_FAILED
    store.update(task.id, status=final_status)

    if notify:
        msg = f"Workflow '{workflow}' concluído." if exit_code == 0 else f"Workflow '{workflow}' falhou."
        notify.notify("iaw", msg)

    raise typer.Exit(code=exit_code)


@app.command("finish-task", help="Encerra a tarefa: resumo + MR + relatório PGD.")
def finish_task(
    issue_id: int = typer.Option(None, "--issue-id", help="Id da Issue (se não puder inferir da branch)."),
    summary: str = typer.Option(None, "--summary", help="Resumo manual (pula a geração via IA)."),
    target_branch: str = typer.Option("master", "--target-branch", help="Branch de destino do MR."),
    no_mr: bool = typer.Option(False, "--no-mr", help="Não criar MR (só atualiza o relatório)."),
    keep_workspace: bool = typer.Option(False, "--keep-workspace", help="Mantém .iaw_workspace/ após concluir."),
) -> None:
    """Encerra a tarefa: gera resumo, abre MR e atualiza o relatório PGD."""
    try:
        result = publish.publish_task(
            issue_id=issue_id,
            summary=summary,
            target_branch=target_branch,
            create_mr=not no_mr,
        )
    except (ValueError, GitLabError) as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    publish.cleanup_workspace(keep=keep_workspace, issue_id=result["issue_id"])
    console.print(f"\n[bold green]Tarefa encerrada.[/bold green] Issue #{result['issue_id']}")
    if result["mr_url"]:
        console.print(f"MR: [cyan]{result['mr_url']}[/cyan]")
    console.print(f"Relatório: [cyan]{result['report']}[/cyan]")


@app.command(help="Mostra o andamento das execuções.")
def status() -> None:
    """Mostra o andamento das execuções."""
    store = state.TaskStore()
    tasks = store.list()
    if not tasks:
        console.print("Nenhuma execução registrada ainda.")
        return

    icons = {
        state.STATUS_RUNNING: "🔄",
        state.STATUS_SUCCESS: "✅",
        state.STATUS_FAILED: "❌",
        state.STATUS_DONE: "🏁",
    }
    for t in tasks:
        icon = icons.get(t.get("status"), "•")
        issue = f"#{t['issue_id']}" if t.get("issue_id") else "—"
        console.print(f"{icon} [{t.get('status')}] {t.get('workflow')} (Issue {issue}) — {t.get('id')}")
        if t.get("mr_url"):
            console.print(f"   MR: {t['mr_url']}")


def _print_eval_report(report: evals.EvalReport) -> None:
    """Imprime o resultado de um eval no terminal."""
    if report.total == 0:
        console.print(f"[yellow]Skill '{report.skill}': sem casos de eval definidos.[/yellow]")
        return
    for r in report.results:
        icon = "✅" if r.passed else "❌"
        console.print(f"  {icon} {r.case} [{r.judge_verdict}]")
    base = f"{report.baseline:.0f}%" if report.baseline is not None else "—"
    status = "[red]REGRESSÃO[/red]" if report.regressed else "[green]OK[/green]"
    console.print(
        f"{report.skill}: {report.passed}/{report.total} "
        f"({report.score:.0f}%) baseline={base} → {status}"
    )


@app.command("eval", help="Roda os evals (Golden Dataset + LLM-as-a-Judge) de skills.")
def eval_skill(
    skill: str = typer.Argument("all", help="Nome da skill (ou 'all' para todas)."),
    update_baseline: bool = typer.Option(False, "--update-baseline", help="Atualiza o baseline para o score atual."),
    no_block: bool = typer.Option(False, "--no-block", help="Apenas reporta, sem travar regressão."),
) -> None:
    """Roda os evals (Golden Dataset + LLM-as-a-Judge) de skills."""
    iaw_dir = project.IAW_DIR

    if skill == "all":
        names = evals.skills_with_evals(iaw_dir)
        if not names:
            console.print("Nenhuma skill com Golden Dataset em .iaw/evals/.")
            return
        regressed = False
        for name in names:
            report = evals.eval_skill(iaw_dir, name, update_baseline=update_baseline, no_block=no_block)
            _print_eval_report(report)
            if report.regressed and not no_block:
                regressed = True
        if regressed:
            console.print("[red]Regressão detectada: bloqueie o merge até corrigir.[/red]")
            raise typer.Exit(code=1)
        return

    report = evals.eval_skill(iaw_dir, skill, update_baseline=update_baseline, no_block=no_block)
    _print_eval_report(report)
    if report.regressed and not no_block:
        console.print(
            f"[red]Regressão na skill '{skill}'.[/red] Corrija ou rode "
            f"`iaw eval {skill} --update-baseline` se intencional."
        )
        raise typer.Exit(code=1)


@app.command("install-hooks", help="Instala o hook pre-commit que roda os evals das skills alteradas.")
def install_hooks(
    force: bool = typer.Option(False, "--force", help="Sobrescreve o pre-commit existente."),
) -> None:
    """Instala o hook de pre-commit que roda os evals das skills alteradas."""
    console.print(hooks.install_precommit_hook(force=force))


@app.command("help")
def help_command(
    comando: str = typer.Argument(None, help="Comando para detalhar (ex: run, finish-task)."),
) -> None:
    """Mostra a ajuda detalhada de um comando (ou a lista geral)."""
    if comando is None:
        console.print("[bold]Comandos do iaw:[/bold]\n")
        for name in help_texts.all_commands():
            console.print(f"  [cyan]{name}[/cyan] — {help_texts.COMMAND_HELP[name]['resumo']}")
        console.print("\nUse [cyan]iaw help <comando>[/cyan] para detalhes.")
        return

    info = help_texts.COMMAND_HELP.get(comando)
    if info is None:
        console.print(f"[red]Comando '{comando}' desconhecido.[/red]")
        console.print("Disponíveis: " + ", ".join(help_texts.all_commands()))
        raise typer.Exit(code=1)

    console.print(f"\n[bold cyan]{comando}[/bold cyan] — {info['resumo']}\n")
    console.print(info["detalhe"])
    console.print("\n[bold]Exemplos:[/bold]")
    for ex in info["exemplos"]:
        console.print(f"  [dim]$[/dim] {ex}")
    console.print()


@app.command(help="Exibe a versão da ferramenta.")
def version() -> None:
    """Exibe a versão da ferramenta."""
    console.print(f"iaw v{__version__}")


if __name__ == "__main__":
    app()
