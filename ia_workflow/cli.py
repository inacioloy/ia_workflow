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
from rich.table import Table

from . import __version__
from . import analyzer
from . import config_manager as cfg
from . import evals
from . import help_texts
from . import hooks
from . import importer
from . import notify
from . import project
from . import publish
from . import recorder
from . import runner
from . import skills as skills_mod
from . import state
from . import work_items
from . import workspace
from .engines import available_engines, build_engine
from .gitlab_client import GitLabClient, GitLabError
from .workflow_parser import WorkflowError, available_workflows

app = typer.Typer(
    name="iaw",
    help="IA Workflow: orquestrador de IA (Artifact-Driven + Graph Engineering).",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Gerencia a configuração global (~/.config/ia_workflow/config.toml).")
app.add_typer(config_app, name="config")

skill_app = typer.Typer(help="Gerencia as skills do projeto (.iaw/skills/).")
app.add_typer(skill_app, name="skill")

relatorio_app = typer.Typer(help="Gera relatórios a partir dos work items do GitLab.")
app.add_typer(relatorio_app, name="relatorio")

console = Console()


# --------------------------------------------------------------------------- #
# setup / config
# --------------------------------------------------------------------------- #
@app.command(help="Configura as credenciais globais da ferramenta (token GitLab, engine).")
def setup() -> None:
    """Configura as credenciais globais da ferramenta (uma única vez)."""
    console.print("[bold blue]=== Configuração do IA Workflow (iaw) ===[/bold blue]\n")

    token = typer.prompt("Personal Access Token do GitLab", hide_input=True, default="")
    gitlab_url = typer.prompt(
        "URL do GitLab", default="https://gitlab.com"
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
    dev_name = typer.prompt("Seu nome (para o relatório)", default="")
    relatorio_path = typer.prompt(
        "Diretório dos relatórios", default=cfg.REPORTS_DIR.as_posix()
    )

    updates = {
        "gitlab_url": gitlab_url,
        "gitlab_token": token,
        "gitlab_project": gitlab_project,
        "default_engine": engine,
        "dev_name": dev_name,
        "relatorio_path": relatorio_path,
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


@skill_app.command("create", help="Cria uma nova skill em branco em .iaw/skills/<nome>/SKILL.md.")
def skill_create(
    name: str,
    description: str = typer.Option("", "--description", help="Descrição curta da skill."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Sobrescreve a skill se já existir."),
) -> None:
    """Cria uma nova skill local (esqueleto com frontmatter) para editar."""
    try:
        path = skills_mod.create_skill(name, description=description, overwrite=overwrite)
        console.print(f"[green]✓[/green] Skill '[cyan]{name}[/cyan]' criada em {path}")
        console.print("Edite o SKILL.md e use `skill: " + name + "` no workflow para mapeá-la.")
    except FileExistsError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc


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
def init(
    analyze: bool = typer.Option(
        False,
        "--analyze",
        help="Após o init, analisa o projeto e preenche stack.md/contexto.md (IA).",
    ),
) -> None:
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
    root = Path.cwd()
    if project.is_suap_project(root):
        console.print(
            "\n[dim]Projeto SUAP detectado: importando skills/agentes existentes do legado…[/dim]"
        )
        importer.import_legacy(root)
    created = project.create_suap_defaults(root)
    console.print(
        f"\n[bold green]Sucesso![/bold green] Diretório [cyan].iaw/[/cyan] criado e configurado "
        f"para {stack}."
    )
    if created:
        console.print("\n[bold green]Skills/agentes padrão do SUAP (fallback):[/bold green]")
        for path in created:
            console.print(f"  [cyan]• {path}[/cyan]")

    if analyze:
        console.print(
            "\n[bold blue]Analisando o projeto para preencher stack.md/contexto.md…[/bold blue]"
        )
        try:
            docs = analyzer.analyze_project(Path.cwd(), iaw_dir=project.IAW_DIR)
        except Exception as exc:  # motor ausente/mal configurado → mantém templates simples
            console.print(f"[yellow]Aviso:[/yellow] análise automática falhou ({exc}).")
            docs = {}

        for name, content in docs.items():
            path = project.IAW_DIR / name
            if name == "contexto.md":
                existing = path.read_text(encoding="utf-8") if path.exists() else ""
                # Não sobrescreve um contexto já preenchido pelo usuário.
                if existing.strip() and "a preencher" not in existing and "<!-- Descreva" not in existing:
                    console.print(f"[dim]contexto.md já preenchido — mantido.[/dim]")
                    continue
            path.write_text(content, encoding="utf-8")
            console.print(f"[green]✓[/green] {name} atualizado em [cyan]{path}[/cyan]")
    else:
        console.print(
            "\n[yellow]Aviso:[/yellow] stack.md e contexto.md foram criados em versão simples. "
            "Use [cyan]iaw init --analyze[/cyan] (ou [cyan]iaw analyze[/cyan]) para preenchê-los "
            "a partir da análise do projeto."
        )

    console.print("Revise os arquivos gerados e faça commit no Git.")


@app.command("analyze", help="Analisa o projeto e preenche .iaw/stack.md e .iaw/contexto.md (usando a IA).")
def analyze(
    dry_run: bool = typer.Option(False, "--dry-run", help="Apenas mostra o que seria gerado, sem escrever."),
) -> None:
    """Analisa o repositório e gera/refina stack.md e contexto.md."""
    root = Path.cwd()
    iaw_dir = root / project.IAW_DIR
    console.print(f"\n[bold blue]=== Análise do projeto ({root}) ===[/bold blue]\n")

    try:
        docs = analyzer.analyze_project(root, iaw_dir=iaw_dir)
    except Exception as exc:  # ex.: motor não configurado / binário ausente
        console.print(f"[red]Erro ao analisar:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    for name, content in docs.items():
        path = iaw_dir / name
        if dry_run:
            console.print(f"[cyan]── {name} (preview) ──[/cyan]")
            preview = content[:2000] + ("…" if len(content) > 2000 else "")
            console.print(preview, markup=False)
        else:
            path.write_text(content, encoding="utf-8")
            console.print(f"[green]✓[/green] {name} gravado em [cyan]{path}[/cyan]")

    if dry_run:
        console.print("\n[dim](--dry-run: nada foi gravado)[/dim]")
    else:
        console.print(
            "\n[bold green]Análise concluída.[/bold green] "
            "Revise os arquivos gerados e faça commit do .iaw/."
        )


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


@app.command("create", help="Cria um work item (Task/Issue) no GitLab do projeto configurado.")
def create_work_item_cmd(
    task: bool = typer.Option(False, "--task", help="Cria uma Task."),
    issue: bool = typer.Option(False, "--issue", help="Cria uma Issue (erro/bug)."),
    demanda: bool = typer.Option(
        False, "--demanda", help="Marca a Task como demanda (label 'demandas')."
    ),
    title: str = typer.Option(None, "--title", help="Título do work item (senão será perguntado)."),
    project_id: str = typer.Option(None, "--project-id", help="Path do projeto no GitLab (ex: suap)."),
    recording: bool = typer.Option(
        False,
        "--recording",
        "--record",
        help="Inicia a gravação de atividades (encerre com `iaw finish-task`).",
    ),
) -> None:
    """Cria uma Task (--task) ou Issue (--issue) atribuída ao seu usuário."""
    if task and issue:
        console.print("[red]Erro:[/red] use apenas um de --task ou --issue.")
        raise typer.Exit(code=1)
    if not task and not issue:
        console.print("[red]Erro:[/red] informe --task ou --issue.")
        raise typer.Exit(code=1)
    if demanda and not task:
        console.print("[red]Erro:[/red] --demanda só é válido junto de --task.")
        raise typer.Exit(code=1)

    if not title or not title.strip():
        title = typer.prompt("Título do work item")

    kind = "task" if task else "issue"
    try:
        item = work_items.create_work_item(
            title=title.strip(), kind=kind, demanda=demanda, project_id=project_id
        )
    except (ValueError, GitLabError) as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    categoria = work_items.classify_work_item(item)
    console.print(
        f"[green]✓[/green] {work_items.item_type_label(item)} criada: "
        f"[cyan]{getattr(item, 'web_url', '')}[/cyan]"
    )
    console.print(f"   #{getattr(item, 'iid', '')} — {title.strip()}")
    console.print(
        f"   Categoria: [bold]{categoria}[/bold] | "
        f"Labels: {', '.join(getattr(item, 'labels', None) or [])}"
    )

    if recording:
        pid = project_id or cfg.get("gitlab_project") or ""
        try:
            recorder.start_recording(
                iid=getattr(item, "iid"),
                project_id=pid,
                title=title.strip(),
            )
        except RuntimeError as exc:
            console.print(f"[yellow]Aviso:[/yellow] {exc}")
        else:
            console.print(
                "[bold green]● Gravação iniciada.[/bold green] "
                "Ao terminar, rode [cyan]iaw finish-task[/cyan] para fechar a task."
            )


@relatorio_app.command("tasks", help="Relatório do mês dividido em task geral, erros e demandas.")
def relatorio_tasks(
    label: str = typer.Argument(None, help="Mês do relatório (ex: AGO/2026). Padrão: mês atual."),
    project_id: str = typer.Option(None, "--project-id", help="Path do projeto no GitLab (ex: suap)."),
    incluir_abertos: bool = typer.Option(
        False,
        "--incluir-abertos",
        help="Inclui itens abertos com o label do mês (status 'execução').",
    ),
) -> None:
    """Lista os work items do mês divididos em task geral, erros e demandas."""
    label = (label or work_items.current_month_label()).strip().upper()
    try:
        resultado = work_items.list_month_work_items(
            label=label, project_id=project_id, include_open=incluir_abertos
        )
    except GitLabError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    items = resultado["items"]
    username = resultado["username"]

    if not items:
        msg = (
            f"Nenhum work item no mês '[cyan]{label}[/cyan]' para o usuário "
            f"[cyan]{username}[/cyan] (autor ou assignee)."
        )
        if not incluir_abertos:
            msg += " Use [cyan]--incluir-abertos[/cyan] para incluir itens abertos."
        console.print(msg)
        return

    fechados: dict[str, list] = {
        work_items.CATEGORIA_TASK_GERAL: [],
        work_items.CATEGORIA_ERRO: [],
        work_items.CATEGORIA_DEMANDA: [],
    }
    abertos = []
    for item, categoria, papel, status in items:
        if status == work_items.STATUS_EXECUCAO:
            abertos.append((item, categoria, papel, status))
        else:
            fechados.setdefault(categoria, []).append((item, categoria, papel, status))

    icons = {
        work_items.CATEGORIA_ERRO: "🐞",
        work_items.CATEGORIA_DEMANDA: "📦",
        work_items.CATEGORIA_TASK_GERAL: "✅",
    }

    secoes = [
        ("✅ Task geral", fechados[work_items.CATEGORIA_TASK_GERAL]),
        ("🐞 Erros (issues)", fechados[work_items.CATEGORIA_ERRO]),
        ("📦 Demandas", fechados[work_items.CATEGORIA_DEMANDA]),
    ]
    if incluir_abertos:
        secoes.append(("🔄 Em execução", abertos))

    console.print(f"\n[bold blue]Relatório {label} — {username}[/bold blue]\n")

    total = 0
    contagem: dict[tuple[str, str], int] = {}
    for titulo, lista in secoes:
        if not lista:
            continue
        total += len(lista)
        table = Table(title=titulo)
        table.add_column("#", justify="right", style="cyan")
        table.add_column("Categoria")
        table.add_column("Tipo")
        table.add_column("Papel")
        table.add_column("Status")
        table.add_column("Título", overflow="fold")
        table.add_column("Link", overflow="fold")
        for item, categoria, papel, status in lista:
            contagem[(categoria, status)] = contagem.get((categoria, status), 0) + 1
            table.add_row(
                f"#{getattr(item, 'iid', '')}",
                f"{icons.get(categoria, '•')} {categoria}",
                work_items.item_type_label(item),
                papel,
                status,
                getattr(item, "title", "") or "",
                getattr(item, "web_url", "") or "",
            )
        console.print(table)

    partes = []
    for categoria in (
        work_items.CATEGORIA_TASK_GERAL,
        work_items.CATEGORIA_ERRO,
        work_items.CATEGORIA_DEMANDA,
    ):
        for status in (work_items.STATUS_FECHADO, work_items.STATUS_EXECUCAO):
            n = contagem.get((categoria, status), 0)
            if n:
                partes.append(f"{n} {categoria} ({status})")
    console.print(f"\n[bold]Total:[/bold] {total} work item(s) — {', '.join(partes)}.")


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
    create_mr: bool = typer.Option(
        False,
        "--create-mr",
        "--create_mr",
        help="Abre um Merge Request ao final do workflow (por padrão, não cria MR).",
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
            create_mr=create_mr,
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


def _finish_recording(session: dict) -> None:
    """Encerra a gravação e atualiza/fecha o work item no GitLab."""
    activity = recorder.stop_recording(session)

    console.print("[dim]Gravação encerrada.[/dim]")
    if activity:
        console.print("\n[bold]Atividades registradas:[/bold]")
        console.print(activity, markup=False)
    else:
        console.print("\n[dim]Nenhuma atividade registrada durante a gravação.[/dim]")
        err_log = Path(session.get("session_dir", "")) / "recorder.err.log"
        if err_log.exists() and err_log.stat().st_size > 0:
            console.print(
                f"[yellow]Dica:[/yellow] o gravador registrou um erro em "
                f"[cyan]{err_log}[/cyan] — veja o conteúdo para diagnosticar."
            )

    sugerido = ""
    try:
        engine = build_engine()
        prompt = (
            "Resuma em até 3 frases, em pt-BR, o que foi feito com base no "
            "histórico de janelas ativas abaixo. Seja objetivo.\n\n"
            + (activity or "(sem registro de atividades)")
        )
        result = engine.generate(prompt)
        if result.success and result.output.strip():
            sugerido = result.output.strip()
    except Exception:  # noqa: BLE001 — motor indisponível não deve travar o encerramento
        pass

    resumo = Prompt.ask("Resumo do que foi feito", default=sugerido or "").strip()

    update_title = Confirm.ask("Deseja atualizar o título da task?", default=False)
    new_title = None
    if update_title:
        new_title = Prompt.ask("Título", default=session.get("title", "")).strip()

    try:
        item = work_items.finish_work_item(
            project_id=session["project_id"],
            iid=session["iid"],
            title=new_title or None,
            description=resumo or None,
            close=True,
        )
    except GitLabError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    recorder.clear_session()
    console.print(
        f"\n[bold green]✓ Tarefa encerrada.[/bold green] "
        f"#{getattr(item, 'iid', session['iid'])} — [cyan]{getattr(item, 'web_url', '')}[/cyan]"
    )
    console.print(f"   Labels: {', '.join(getattr(item, 'labels', None) or [])}")


@app.command(
    "finish-task",
    help="Encerra a tarefa: resumo + relatório (+ MR). Fecha também a gravação de `iaw create --recording`.",
)
def finish_task(
    issue_id: int = typer.Option(None, "--issue-id", help="Id da Issue (se não puder inferir da branch)."),
    summary: str = typer.Option(None, "--summary", help="Resumo manual (pula a geração via IA)."),
    target_branch: str = typer.Option("master", "--target-branch", help="Branch de destino do MR."),
    create_mr: bool = typer.Option(
        False,
        "--create-mr",
        "--create_mr",
        help="Abre o Merge Request (por padrão, só atualiza o relatório).",
    ),
    keep_workspace: bool = typer.Option(False, "--keep-workspace", help="Mantém .iaw_workspace/ após concluir."),
) -> None:
    """Encerra a tarefa: gera resumo, atualiza o relatório e (opcionalmente) abre o MR."""
    # Fluxo de gravação (iaw create --recording) tem prioridade.
    session = recorder.load_session()
    if session is not None:
        _finish_recording(session)
        return

    try:
        result = publish.publish_task(
            issue_id=issue_id,
            summary=summary,
            target_branch=target_branch,
            create_mr=create_mr,
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
