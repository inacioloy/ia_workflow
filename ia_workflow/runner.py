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
from . import project
from . import publish
from .engines import EngineResult, build_engine
from .gitlab_client import GitLabError
from .workflow_parser import Step, Workflow, load_workflow, resolve_order

console = Console()

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


def _step_prompt(step: Step) -> str:
    """Monta a instrução do step a partir do campo `prompts`."""
    if step.prompts:
        return "\n".join(step.prompts)
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
    return fallback.get(step.action, f"Execute a etapa '{step.id}' ({step.action}).")


def _step_context_files(step: Step, working_dir: Path) -> list[Path]:
    """Reúne os arquivos de contexto (inputs + context + artefatos do workspace)."""
    files: list[Path] = []
    for rel in step.input_files() + step.context:
        path = working_dir / rel
        if path.is_file() and path not in files:
            files.append(path)

    # Auto-inclui os artefatos gerados por etapas anteriores (start-task/run),
    # para que o motor sempre enxergue o contexto acumulado da tarefa.
    workspace = working_dir / ".iaw_workspace"
    if workspace.is_dir():
        for artifact in sorted(workspace.glob("*.md")):
            if artifact not in files:
                files.append(artifact)

    return files


def _write_outputs(step: Step, working_dir: Path, text: str) -> None:
    """Escreve a saída do motor nos arquivos declarados em `outputs`."""
    for rel in step.output_files():
        path = working_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        console.print(f"[green]✓[/green] Artefato gravado em [cyan]{path}[/cyan]")


def execute_step(
    step: Step,
    working_dir: Path,
    stream: Callable[[str], None] | None = None,
) -> EngineResult:
    """Executa um único step e devolve o resultado."""
    if step.action in ENGINE_ACTIONS:
        engine = build_engine()
        prompt = _step_prompt(step)
        context_files = _step_context_files(step, working_dir)
        result = engine.generate(
            prompt,
            context_files=context_files,
            working_dir=working_dir,
            stream=stream,
        )
        if result.success and result.output and step.output_files():
            _write_outputs(step, working_dir, result.output)
        return result

    if step.action in TERMINAL_ACTIONS:
        if not step.command:
            return EngineResult(success=False, error=f"Step '{step.id}' não define `command`.")
        return run_terminal_command(step.command)

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
) -> int:
    """Executa um workflow do início ao fim.

    :return: código de saída (0 = sucesso, 1 = falha).
    """
    cwd = working_dir or Path.cwd()
    iaw_dir = cwd / project.IAW_DIR

    workflow_path = iaw_dir / "workflows" / f"{workflow_name}.yaml"
    workflow: Workflow = load_workflow(workflow_path)

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
    for step in steps:
        approval = " [bold yellow]🔒 aprovação humana[/bold yellow]" if step.require_human_approval else ""
        console.print(f"[bold blue]▸ Etapa[/bold blue] {step.id} — {step.action}{approval}")

        result = execute_step(step, cwd, stream=stream)

        if not result.success:
            console.print(f"[red]✗ Falha na etapa '{step.id}':[/red] {escape(result.error)}")
            console.print("[red]Fluxo interrompido.[/red]")
            return 1

        if result.output and not step.output_files() and step.action in ENGINE_ACTIONS:
            console.print(result.output)

        if step.require_human_approval:
            from rich.prompt import Confirm

            if not Confirm.ask("Aprovar esta etapa e continuar?", default=True):
                console.print("[yellow]Fluxo pausado pelo usuário.[/yellow]")
                return 1

    console.print("\n[bold green]✓ Workflow concluído com sucesso.[/bold green]\n")
    return 0
