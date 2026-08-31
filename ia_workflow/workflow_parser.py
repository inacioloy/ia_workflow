"""Parser de workflows YAML (Graph Engineering).

Lê os grafos de execução de `.iaw/workflows/*.yaml` e os transforma em uma
estrutura tipada, com ordenação topológica baseada em `depends_on`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class WorkflowError(RuntimeError):
    """Erro de carregamento/validação de workflow."""


@dataclass
class Step:
    """Um nó do grafo de execução."""

    id: str
    action: str
    depends_on: list[str] = field(default_factory=list)
    inputs: list[Any] = field(default_factory=list)
    context: list[str] = field(default_factory=list)
    outputs: list[Any] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    command: str | None = None
    skill: str | None = None
    agent: str | None = None
    allow_no_change: bool = False
    require_human_approval: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def input_files(self) -> list[str]:
        """Arquivos de entrada (chave `file` nos inputs)."""
        files: list[str] = []
        for item in self.inputs:
            if isinstance(item, dict) and item.get("file"):
                files.append(item["file"])
        return files

    def output_files(self) -> list[str]:
        """Arquivos de saída (chave `file` nos outputs)."""
        files: list[str] = []
        for item in self.outputs:
            if isinstance(item, dict) and item.get("file"):
                files.append(item["file"])
        return files


@dataclass
class Workflow:
    name: str
    description: str
    version: str
    steps: list[Step]

    @property
    def step_map(self) -> dict[str, Step]:
        return {s.id: s for s in self.steps}


def load_workflow(path: str | Path) -> Workflow:
    """Carrega e valida um arquivo YAML de workflow."""
    path = Path(path)
    if not path.is_file():
        raise WorkflowError(f"Workflow não encontrado: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorkflowError(f"YAML inválido em {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise WorkflowError(f"Workflow {path} não é um documento YAML válido.")

    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise WorkflowError(f"Workflow {path} não define `steps`.")

    steps: list[Step] = []
    for i, raw in enumerate(steps_raw):
        if not isinstance(raw, dict):
            raise WorkflowError(f"Step #{i + 1} de {path} não é um objeto válido.")
        step_id = raw.get("id")
        if not step_id:
            raise WorkflowError(f"Step #{i + 1} de {path} não tem `id`.")
        steps.append(
            Step(
                id=str(step_id),
                action=raw.get("action", ""),
                depends_on=list(raw.get("depends_on") or []),
                inputs=list(raw.get("inputs") or []),
                context=[str(c) for c in (raw.get("context") or [])],
                outputs=list(raw.get("outputs") or []),
                prompts=[str(p) for p in (raw.get("prompts") or [])],
                command=raw.get("command"),
                skill=str(raw["skill"]) if raw.get("skill") else None,
                agent=str(raw["agent"]) if raw.get("agent") else None,
                allow_no_change=bool(raw.get("allow_no_change", False)),
                require_human_approval=bool(raw.get("require_human_approval", False)),
                raw=raw,
            )
        )

    return Workflow(
        name=str(data.get("name", path.stem)),
        description=str(data.get("description", "")),
        version=str(data.get("version", "1.0")),
        steps=steps,
    )


def resolve_order(workflow: Workflow) -> list[Step]:
    """Ordena os passos por dependência (ordem topológica).

    :raises WorkflowError: se houver dependência inexistente ou ciclo.
    """
    result: list[Step] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(step: Step) -> None:
        if step.id in visited:
            return
        if step.id in visiting:
            raise WorkflowError(f"Ciclo de dependências detectado em '{step.id}'.")
        visiting.add(step.id)
        for dep in step.depends_on:
            if dep not in workflow.step_map:
                raise WorkflowError(
                    f"Dependência '{dep}' do step '{step.id}' não existe no workflow."
                )
            visit(workflow.step_map[dep])
        visiting.remove(step.id)
        visited.add(step.id)
        result.append(step)

    for step in workflow.steps:
        visit(step)

    return result


def available_workflows(iaw_dir: Path) -> list[str]:
    """Lista os workflows disponíveis em `.iaw/workflows/`."""
    workflows_dir = iaw_dir / "workflows"
    if not workflows_dir.is_dir():
        return []
    return sorted(p.stem for p in workflows_dir.glob("*.yaml"))
