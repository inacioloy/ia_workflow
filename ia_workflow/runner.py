"""Orquestrador do iaw (`iaw run`).

Executa os passos de um workflow YAML na ordem topológica, chamando o motor de
IA configurado e respeitando os gates de aprovação humana (`require_human_approval`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.markup import escape

from . import browser_harness
from . import expertise
from . import project
from . import publish
from . import workspace
from .engines import AIEngine, EngineResult, build_engine
from .gitlab_client import GitLabError
from .workflow_parser import Step, Workflow, load_workflow, resolve_order

console = Console()

# Marcador que a IA deve devolver quando uma etapa opcional não tem trabalho.
NO_CHANGE_MARKER = "SEM_ALTERACOES_NECESSARIAS"

# Ações implementadas nesta fase.
ENGINE_ACTIONS = {"ask_clarifying_questions", "generate_artifact", "execute_ai_coding"}
TERMINAL_ACTIONS = {"run_terminal_command"}
BROWSER_ACTIONS = {"run_browser_harness"}
PUBLISH_ACTIONS = {"generate_summary_and_publish"}


def run_terminal_command(command: str) -> EngineResult:
    """Executa um comando de terminal e devolve o resultado."""
    console.print(f"[cyan]$[/cyan] {command}")
    try:
        proc = subprocess.run(
            command, shell=True, capture_output=True, text=True
        )
    except OSError as exc:
        return EngineResult(success=False, error=str(exc))

    if proc.stdout.strip():
        console.print(proc.stdout.rstrip())
    if proc.stderr.strip():
        console.print(f"[yellow]{proc.stderr.rstrip()}[/yellow]")

    return EngineResult(
        success=proc.returncode == 0,
        output=proc.stdout,
        error=proc.stderr,
    )


def _step_prompt(step: Step, iaw_dir: Path) -> str:
    """Monta a instrução do step, injetando o perfil da skill/agent (se houver)."""
    if step.prompts:
        base = "\n".join(step.prompts)
    else:
        fallback = {
            "ask_clarifying_questions": (
                "Com base nos artefatos e no contexto fornecidos, analise os requisitos "
                "e faça até 3 perguntas para esclarecer ambiguidades da regra de negócio. "
                "Se estiver claro, resuma o entendimento."
            ),
            "generate_artifact": (
                "Com base nos artefatos e no contexto fornecidos, gere o artefato desta "
                "etapa seguindo as diretrizes do projeto."
            ),
            "execute_ai_coding": (
                "Implemente o código exatamente conforme os artefatos e especificações "
                "fornecidos, respeitando as diretrizes do projeto (stack.md)."
            ),
        }
        base = fallback.get(step.action, f"Execute a etapa '{step.id}' ({step.action}).")

    label, perfil = expertise.resolve_expertise(
        iaw_dir, skill=step.skill, agent=step.agent
    )
    if perfil:
        base = (
            f"## Perfil do especialista: {label}\n\n"
            f"{perfil}\n\n"
            f"--- INSTRUÇÃO DA ETAPA ---\n\n{base}"
        )

    if step.allow_no_change:
        base += (
            f"\n\nIMPORTANTE: se esta etapa não for aplicável à tarefa (nenhuma "
            f"alteração deste tipo é necessária), NÃO modifique arquivos e responda "
            f"exatamente: {NO_CHANGE_MARKER}."
        )
    return base


def _resolve_artifact_path(rel: str, working_dir: Path, task_dir: Path) -> Path:
    """Resolve um caminho de artefato: `.iaw_workspace/...` aponta para a pasta da tarefa."""
    prefix = f"{workspace.WORKSPACE_ROOT.name}/"
    rel = str(rel)
    if rel.startswith(prefix):
        return task_dir / rel[len(prefix):]
    if rel == workspace.WORKSPACE_ROOT.name:
        return task_dir
    return working_dir / rel


def _step_context_files(step: Step, working_dir: Path, task_dir: Path) -> list[Path]:
    """Reúne os arquivos de contexto (inputs + context + artefatos do workspace)."""
    files: list[Path] = []
    for rel in step.input_files() + step.context:
        path = _resolve_artifact_path(rel, working_dir, task_dir)
        if path.is_file() and path not in files:
            files.append(path)

    # Auto-inclui os artefatos gerados por etapas anteriores (start-task/run),
    # para que o motor sempre enxergue o contexto acumulado da tarefa.
    if task_dir.is_dir():
        for artifact in sorted(task_dir.glob("*.md")):
            if artifact not in files:
                files.append(artifact)

    return files


def _write_outputs(step: Step, working_dir: Path, task_dir: Path, text: str) -> None:
    """Escreve a saída do motor nos arquivos declarados em `outputs`."""
    for rel in step.output_files():
        path = _resolve_artifact_path(rel, working_dir, task_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        console.print(f"[green]✓[/green] Artefato gravado em [cyan]{path}[/cyan]")


def execute_step(
    step: Step,
    working_dir: Path,
    task_dir: Path,
    stream: Callable[[str], None] | None = None,
    log: bool = False,
    engine: AIEngine | None = None,
    no_publish: bool = False,
) -> EngineResult:
    """Executa um único step e devolve o resultado.

    :param log: se True, imprime o prompt enviado à IA, os arquivos de contexto
        e a saída/erro do motor (log de execução).
    :param engine: instância do motor reutilizada ao longo do workflow (permite
        reuso de sessão quando o engine suporta).
    :param no_publish: se True, a etapa de publicação (MR/PGD) é pulada.
    """
    if step.action in ENGINE_ACTIONS:
        engine = engine or build_engine()
        iaw_dir = working_dir / project.IAW_DIR
        try:
            prompt = _step_prompt(step, iaw_dir)
        except FileNotFoundError as exc:
            return EngineResult(success=False, error=str(exc))
        context_files = _step_context_files(step, working_dir, task_dir)

        if log:
            console.print(f"\n[bold cyan]▸ Prompt enviado à IA ({step.id}):[/bold cyan]")
            preview = prompt if len(prompt) <= 4000 else prompt[:4000] + "\n…[truncado]"
            console.print(preview, markup=False)
            if context_files:
                console.print("[dim]Contexto anexado:[/dim]")
                for f in context_files:
                    console.print(f"[dim]  • {f}[/dim]")
            console.print("[dim]── saída da IA ──[/dim]")

        result = engine.generate(
            prompt,
            context_files=context_files,
            working_dir=working_dir,
            stream=stream,
        )

        # Etapa opcional: a IA pode declarar que não há trabalho a fazer.
        if (
            step.allow_no_change
            and result.success
            and NO_CHANGE_MARKER in (result.output or "").upper()
        ):
            console.print(
                f"[dim]⏭ Etapa {step.id}: sem alterações necessárias "
                f"(a IA indicou que nada precisa ser feito).[/dim]"
            )
            return EngineResult(success=True, output="")

        if log:
            if stream is None and result.output:
                console.print(result.output, markup=False)
            if result.error:
                console.print(f"[yellow]{escape(result.error)}[/yellow]")

        if result.success and result.output and step.output_files():
            _write_outputs(step, working_dir, task_dir, result.output)
        return result

    if step.action in TERMINAL_ACTIONS:
        command = step.command or ""
        if task_dir and "{test_target}" in command:
            progress = workspace.load_progress(task_dir)
            command = command.replace("{test_target}", progress.get("test_target", "").strip())
        if not command.strip():
            return EngineResult(success=False, error=f"Step '{step.id}' não define `command`.")
        return run_terminal_command(command)

    if step.action in BROWSER_ACTIONS:
        config = step.raw.get("config") or {}
        start_url = config.get("start_url", "http://localhost:8000/")
        auth_script = config.get("auth_script")
        output = (
            step.output_files()[0]
            if step.output_files()
            else str(working_dir / ".iaw_workspace" / "screenshot_prova.png")
        )
        try:
            path = browser_harness.capture_screenshot(
                start_url, output, auth_script=auth_script
            )
            return EngineResult(success=True, output=f"Screenshot salvo em {path}")
        except RuntimeError as exc:
            return EngineResult(success=False, error=str(exc))

    if step.action in PUBLISH_ACTIONS:
        if no_publish:
            console.print(
                "[yellow]⚠ Publicação desativada (--no-publish):[/yellow] "
                "etapa de MR/PGD pulada."
            )
            return EngineResult(success=True, output="")
        try:
            result = publish.publish_task()
            return EngineResult(
                success=True,
                output=f"Tarefa publicada: {result['mr_url'] or 'sem MR'}",
            )
        except (ValueError, GitLabError) as exc:
            return EngineResult(success=False, error=str(exc))

    return EngineResult(success=False, error=f"Ação desconhecida: '{step.action}'.")


def run_workflow(
    workflow_name: str,
    *,
    working_dir: Path | None = None,
    detach: bool = False,
    notify: bool = False,
    stream: Callable[[str], None] | None = None,
    resume: bool = False,
    issue_id: int | None = None,
    log: bool = False,
    no_publish: bool = False,
) -> int:
    """Executa um workflow do início ao fim.

    :param resume: se True, pula as etapas já registradas como concluídas no
        `state.json` da tarefa (útil para retomar tarefas longas).
    :param issue_id: Id da Issue/tarefa alvo; se omitido, é inferido da branch
        ou do workspace (`.iaw_workspace/issue-<id>`).
    :param log: se True, mostra o log de execução da IA (prompt, contexto e saída).
    :param no_publish: se True, pula a etapa de publicação (MR/PGD).
    :return: código de saída (0 = sucesso, 1 = falha).
    """
    cwd = working_dir or Path.cwd()
    iaw_dir = cwd / project.IAW_DIR

    workflow_path = iaw_dir / "workflows" / f"{workflow_name}.yaml"
    workflow: Workflow = load_workflow(workflow_path)

    if issue_id is not None:
        task_dir = workspace.task_dir(issue_id)
    else:
        task_dir = workspace.find_task_dir() or (cwd / workspace.WORKSPACE_ROOT)
    progress = workspace.load_progress(task_dir)
    issue_id = issue_id or progress.get("issue_id") or workspace.infer_issue_id()
    completed = {s for s in (progress.get("completed_steps") or []) if s in workflow.step_map}

    console.print(
        f"\n[bold magenta]▶ Workflow:[/bold magenta] {workflow.name} "
        f"[dim]({workflow.description})[/dim]\n"
    )

    if detach or notify:
        console.print(
            "[dim](--detach/--notify serão totalmente suportados na Fase 4; "
            "executando em primeiro plano.)[/dim]\n"
        )

    steps = resolve_order(workflow)
    order = [s.id for s in steps]

    # Uma única instância do motor por execução: permite reuso de sessão
    # (ex.: Antigravity continua a mesma conversa entre as etapas).
    engine = build_engine()

    if resume and completed:
        console.print(
            f"[dim]Retomando: {len(completed)} etapa(s) concluída(s) serão puladas.[/dim]\n"
        )

    for step in steps:
        if resume and step.id in completed:
            console.print(f"[dim]⏭ Etapa {step.id} — já concluída (pulada)[/dim]")
            continue

        approval = " [bold yellow]🔒 aprovação humana[/bold yellow]" if step.require_human_approval else ""
        console.print(f"[bold blue]▸ Etapa[/bold blue] {step.id} — {step.action}{approval}")

        result = execute_step(
            step,
            cwd,
            task_dir,
            stream=stream,
            log=log,
            engine=engine,
            no_publish=no_publish,
        )

        if not result.success:
            console.print(f"[red]✗ Falha na etapa '{step.id}':[/red] {escape(result.error)}")
            console.print("[red]Fluxo interrompido.[/red]")
            return 1

        if (
            result.output
            and not step.output_files()
            and step.action in ENGINE_ACTIONS
            and not log
        ):
            console.print(result.output, markup=False)

        if step.require_human_approval:
            from rich.prompt import Confirm

            if not Confirm.ask("Aprovar esta etapa e continuar?", default=True):
                console.print("[yellow]Fluxo pausado pelo usuário.[/yellow]")
                return 1

        completed.add(step.id)
        next_step = next((s for s in order if s not in completed), None)
        workspace.save_progress(
            task_dir,
            workflow=workflow.name,
            issue_id=issue_id,
            completed_steps=sorted(completed, key=order.index),
            next_step=next_step,
            test_target=progress.get("test_target", ""),
        )

    console.print("\n[bold green]✓ Workflow concluído com sucesso.[/bold green]\n")
    return 0
