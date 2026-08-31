"""Análise do projeto para preencher `.iaw/stack.md` e `.iaw/contexto.md`.

O comando `iaw analyze` coleta um "fingerprint" do repositório (stack detectada,
árvore de arquivos e conteúdo de arquivos-chave) e pede ao motor de IA que gere
versões ricas do `stack.md` (guardrails técnicos) e do `contexto.md` (domínio).
Se o motor falhar, usa heurísticas simples para não deixar os arquivos vazios.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import project
from .engines import AIEngine, EngineResult, build_engine

IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".iaw_workspace",
    "build", "dist", ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
}

KEY_FILES = [
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements/*.txt",
    "package.json",
    "manage.py",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Pipfile",
    "setup.py",
    ".gitlab-ci.yml",
]

MAX_TREE_ENTRIES = 150
MAX_KEY_FILE_CHARS = 4000
MAX_DIGEST_CHARS = 20000


def _ignore(path: Path, root: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.relative_to(root).parts)


def detect_stack(root: Path) -> list[str]:
    """Detecta a stack por heurística (sem IA)."""
    hints: list[str] = []
    if (root / "manage.py").is_file():
        hints.append("Django")
    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
        if "Django" not in hints:
            hints.append("Python")
    if (root / "package.json").is_file():
        hints.append("Node.js/frontend")
    if (root / "pom.xml").is_file():
        hints.append("Java/Maven")
    if (root / "go.mod").is_file():
        hints.append("Go")
    if (root / "Cargo.toml").is_file():
        hints.append("Rust")
    if list(root.glob("*.csproj")):
        hints.append(".NET")
    return hints or ["(não identificado)"]


def project_tree(root: Path) -> str:
    """Gera uma árvore de arquivos resumida (ignora pastas de build/venv)."""
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if _ignore(path, root):
            continue
        rel = path.relative_to(root)
        lines.append(str(rel) + ("/" if path.is_dir() else ""))
        if len(lines) >= MAX_TREE_ENTRIES:
            lines.append("… (árvore truncada)")
            break
    return "\n".join(lines)


def _read_first(root: Path, pattern: str) -> str:
    matches = sorted(root.glob(pattern))
    for path in matches:
        if _ignore(path, root):
            continue
        try:
            return path.read_text(encoding="utf-8")[:MAX_KEY_FILE_CHARS]
        except (OSError, UnicodeDecodeError):
            return ""
    return ""


def read_key_files(root: Path) -> str:
    """Lê o conteúdo (truncado) dos arquivos-chave do projeto."""
    sections: list[str] = []
    seen: set[str] = set()
    for rel in KEY_FILES:
        for path in sorted(root.glob(rel)):
            if path in seen or _ignore(path, root):
                continue
            seen.add(path)
            try:
                content = path.read_text(encoding="utf-8")[:MAX_KEY_FILE_CHARS]
            except (OSError, UnicodeDecodeError):
                continue
            sections.append(f"### {path.relative_to(root)}\n```\n{content}\n```")

    # settings.py do Django (primeiro encontrado).
    settings = sorted(root.glob("**/settings.py"))
    for path in settings:
        if _ignore(path, root):
            continue
        try:
            content = path.read_text(encoding="utf-8")[:MAX_KEY_FILE_CHARS]
        except (OSError, UnicodeDecodeError):
            continue
        sections.append(f"### {path.relative_to(root)}\n```\n{content}\n```")
        break

    return "\n\n".join(sections)


def build_digest(root: Path) -> str:
    """Monta o resumo do projeto que será enviado à IA."""
    stack = ", ".join(detect_stack(root))
    tree = project_tree(root)
    key_files = read_key_files(root)

    digest = (
        f"# Fingerprint do projeto\n\n"
        f"- Raiz: {root}\n"
        f"- Stack detectada: {stack}\n\n"
        f"## Árvore de arquivos\n```\n{tree}\n```\n\n"
        f"## Arquivos-chave\n{key_files}\n"
    )
    return digest[:MAX_DIGEST_CHARS]


def _heuristic_stack(root: Path) -> str:
    """Gera um stack.md básico sem IA (fallback offline)."""
    stack = ", ".join(detect_stack(root))
    return (
        "# Diretrizes Técnicas do Projeto\n\n"
        f"- **Stack detectada:** {stack}\n"
        "- **Testes:** verifique o comando de teste do projeto (pytest, npm test, etc.).\n"
        "- **Regras de Negócio:** respeite a arquitetura existente. Não sugira "
        "bibliotecas externas sem aprovação.\n"
        "- **Idioma:** pt-BR (código, comentários, commits, docs).\n"
    )


def _heuristic_context(root: Path) -> str:
    stack = ", ".join(detect_stack(root))
    return (
        "# Contexto do Projeto\n\n"
        f"- **Stack:** {stack}\n"
        "- **Domínio:** (a preencher) descreva atores, subsistemas e invariantes.\n"
        "- **Subsistemas:** (a preencher)\n"
        "- **Invariantes:** (a preencher)\n"
    )


def generate_stack(root: Path, engine: AIEngine) -> str:
    """Gera o conteúdo do stack.md usando a IA (com fallback heurístico)."""
    digest = build_digest(root)
    prompt = (
        "Você é um arquiteto sênior. Com base no fingerprint do projeto abaixo, "
        "gere o conteúdo do arquivo `stack.md` (diretrizes técnicas rígidas) em "
        "pt-BR. Inclua: stack/versões, estrutura de pastas, comandos de build/"
        "teste/lint, convenções de código, guardrails (o que NÃO fazer) e idioma. "
        "Seja direto e use markdown.\n\n"
        f"{digest}"
    )
    result: EngineResult = engine.generate(prompt)
    if result.success and result.output.strip():
        return result.output.strip()
    return _heuristic_stack(root)


def generate_context(root: Path, engine: AIEngine) -> str:
    """Gera o conteúdo do contexto.md usando a IA (com fallback heurístico)."""
    digest = build_digest(root)
    prompt = (
        "Você é um analista de domínio. Com base no fingerprint do projeto abaixo, "
        "gere o conteúdo do arquivo `contexto.md` (contexto de negócio) em pt-BR. "
        "Inclua: objetivo do sistema, atores/usuários, subsistemas/módulos, "
        "invariantes e integrações. Se não houver informação suficiente, deixe "
        "tópicos claros com '(a preencher)'. Seja direto e use markdown.\n\n"
        f"{digest}"
    )
    result: EngineResult = engine.generate(prompt)
    if result.success and result.output.strip():
        return result.output.strip()
    return _heuristic_context(root)


def analyze_project(
    root: Path,
    *,
    iaw_dir: Path | None = None,
    engine: AIEngine | None = None,
) -> dict[str, str]:
    """Analisa o projeto e devolve ``{stack.md, contexto.md}``.

    :param iaw_dir: diretório `.iaw/` do projeto (padrão: ``<root>/.iaw``).
    :param engine: motor de IA a usar (padrão: configurado globalmente).
    """
    iaw_dir = iaw_dir or (root / project.IAW_DIR)
    iaw_dir.mkdir(parents=True, exist_ok=True)
    engine = engine or build_engine()

    return {
        "stack.md": generate_stack(root, engine),
        "contexto.md": generate_context(root, engine),
    }
