"""Importador de legado (`iaw import-legacy`).

Copia — **sem apagar nada** — as configurações de IA espalhadas pelas
ferramentas (`.agents/`, `.claude/`, `.opencode/`, `.gitlab/`) para a estrutura
canônica `.iaw/`. O legado permanece intacto no projeto.

Fluxo:
  1. `iaw import-legacy --dry-run`  → apenas lista o que será copiado.
  2. `iaw import-legacy`            → copia de fato.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import project

# Arquivos de contexto na raiz → preservados em .iaw/legacy/ (referência).
ROOT_CONTEXT_FILES = ["AGENTS.md", "CLAUDE.md", "CONTEXT.md", "GEMINI.md"]

# Configs de ferramenta (não são skills/agents, mas valem como referência).
TOOL_CONFIG_FILES = {
    ".claude/settings.json": "legacy/claude/settings.json",
    ".claude/launch.json": "legacy/claude/launch.json",
}


@dataclass
class Op:
    """Uma operação de importação (cópia de arquivo ou diretório)."""

    kind: str  # "dir" | "file" | "convert"
    source: Path
    dest: Path
    note: str = ""

    def __str__(self) -> str:  # usado no relatório
        arrow = "📁" if self.kind == "dir" else ("🔁" if self.kind == "convert" else "📄")
        return f"{arrow} {self.source}  →  {self.dest}" + (f"  ({self.note})" if self.note else "")


# --------------------------------------------------------------------------- #
# Conversão TOML (frontmatter +++ do OpenCode) → YAML (--- canônico)
# --------------------------------------------------------------------------- #
def _toml_value_to_yaml(value: str) -> str:
    """Converte o lado direito de `key = value` do TOML para YAML (casos usados)."""
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value  # strings TOML/YAML usam aspas duplas compatíveis aqui
    if value.startswith("[") and value.endswith("]"):
        return value  # array inline já é válido em YAML flow
    return value


def convert_opencode_frontmatter(text: str) -> str:
    """Converte frontmatter TOML (`+++`) em YAML (`---`).

    Só cobre o formato simples usado em `.opencode/agent/*.md`
    (`name`, `description`, `tools`, `mode`). Se não começar com `+++`,
    retorna o texto inalterado.
    """
    if not text.lstrip().startswith("+++"):
        return text

    lines = text.split("\n")
    if lines[0].strip() != "+++":
        return text

    end = 1
    while end < len(lines) and lines[end].strip() != "+++":
        end += 1
    if end >= len(lines):
        return text  # sem fechamento, deixa como está

    yaml_lines: list[str] = []
    for line in lines[1:end]:
        m = re.match(r'^(\w+)\s*=\s*(.*)$', line)
        if m:
            key, value = m.group(1), _toml_value_to_yaml(m.group(2))
            yaml_lines.append(f"{key}: {value}")
        else:
            yaml_lines.append(line)

    return "---\n" + "\n".join(yaml_lines) + "\n---\n" + "\n".join(lines[end + 1 :])


# --------------------------------------------------------------------------- #
# Coleta de operações
# --------------------------------------------------------------------------- #
def _add_dir_copy(ops: list[Op], src: Path, dest_parent: Path) -> None:
    if not src.is_dir():
        return
    for child in sorted(src.iterdir()):
        if child.is_dir():
            ops.append(Op("dir", child, dest_parent / child.name))
        elif child.is_file():
            ops.append(Op("file", child, dest_parent / child.name))


def _add_files(ops: list[Op], src_dir: Path, dest_dir: Path, *, kind: str = "file") -> None:
    if not src_dir.is_dir():
        return
    for child in sorted(src_dir.iterdir()):
        if child.is_file():
            ops.append(Op(kind, child, dest_dir / child.name))


def collect_ops(root: Path) -> list[Op]:
    """Monta a lista de operações de importação a partir do projeto legado."""
    ops: list[Op] = []

    # 1. Skills (fonte da verdade em .agents/skills/)
    _add_dir_copy(ops, root / ".agents" / "skills", project.IAW_DIR / "skills")

    # 2. Templates do documentador
    _add_dir_copy(ops, root / ".agents" / "documentador", project.IAW_DIR / "templates" / "documentador")

    # 3. Agents do Claude Code (YAML, formato canônico)
    claude_agents = root / ".claude" / "agents"
    _add_files(ops, claude_agents, project.IAW_DIR / "agents")

    # 4. Agents do OpenCode (só os que não têm equivalente no Claude; converte TOML→YAML)
    planned = {c.name for c in claude_agents.iterdir() if c.is_file()} if claude_agents.is_dir() else set()
    opencode_agents = root / ".opencode" / "agent"
    if opencode_agents.is_dir():
        for child in sorted(opencode_agents.iterdir()):
            if child.is_file() and child.name not in planned:
                kind = "convert" if child.read_text(encoding="utf-8").lstrip().startswith("+++") else "file"
                ops.append(Op(kind, child, project.IAW_DIR / "agents" / child.name))

    # 5. Experts de domínio (Claude Code commands)
    _add_files(ops, root / ".claude" / "commands" / "suap", project.IAW_DIR / "experts")

    # 6. Hooks Python
    _add_files(ops, root / ".claude" / "hooks", project.IAW_DIR / "hooks")

    # 7. Specs
    _add_files(ops, root / ".claude" / "specs", project.IAW_DIR / "specs")

    # 8. Templates GitLab (cópia de referência; o original continua em .gitlab/)
    _add_files(ops, root / ".gitlab" / "issue_templates", project.IAW_DIR / "templates" / "gitlab" / "issue_templates")
    _add_files(ops, root / ".gitlab" / "merge_request_templates", project.IAW_DIR / "templates" / "gitlab" / "merge_request_templates")

    # 9. Arquivos de contexto da raiz → .iaw/legacy/
    for name in ROOT_CONTEXT_FILES:
        src = root / name
        if src.is_file():
            ops.append(Op("file", src, project.IAW_DIR / "legacy" / name))

    # 10. Configs de ferramenta → .iaw/legacy/
    for src_rel, dest_rel in TOOL_CONFIG_FILES.items():
        src = root / src_rel
        if src.is_file():
            ops.append(Op("file", src, project.IAW_DIR / dest_rel))

    return ops


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #
def execute(ops: list[Op], *, dry_run: bool, overwrite: bool = False) -> None:
    """Executa (ou apenas lista, em dry-run) as operações de importação."""
    copied = 0
    skipped = 0

    for op in ops:
        op.dest.parent.mkdir(parents=True, exist_ok=True)

        if op.dest.exists() and not overwrite:
            skipped += 1
            if dry_run:
                print(f"⏭️  [já existe] {op.source}  →  {op.dest}")
            continue

        if dry_run:
            print(str(op))
            copied += 1
            continue

        if op.kind == "dir":
            if op.dest.exists() and op.dest.is_dir():
                shutil.rmtree(op.dest) if overwrite else None
            shutil.copytree(op.source, op.dest, dirs_exist_ok=True)
        elif op.kind == "convert":
            text = op.source.read_text(encoding="utf-8")
            op.dest.write_text(convert_opencode_frontmatter(text), encoding="utf-8")
        else:
            shutil.copy2(op.source, op.dest)
        copied += 1

    print(f"\n{'Simulação' if dry_run else 'Importação'}: {copied} itens copiados, {skipped} já existentes (ignorados).")


def import_legacy(root: Path, *, dry_run: bool = False, overwrite: bool = False) -> None:
    """Importa o legado do projeto em `root` para `.iaw/` (nunca apaga o legado)."""
    ops = collect_ops(root)
    if not ops:
        print("Nenhum diretório legado encontrado para importar.")
        return
    execute(ops, dry_run=dry_run, overwrite=overwrite)
