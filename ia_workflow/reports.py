"""Relatório mensal PGD (Programa de Gestão e Desempenho).

O relatório fica **fora do repositório**, no diretório global configurado em
``pgd_report_path``. Um arquivo por mês (ex: ``agosto_2026.md``).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import config_manager as cfg

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def monthly_report_path(config: dict | None = None) -> Path:
    """Caminho do relatório do mês/ano atuais."""
    config = config or cfg.load_config()
    base = Path(config.get("pgd_report_path") or cfg.REPORTS_DIR).expanduser()
    now = datetime.now()
    return base / f"{MESES[now.month - 1]}_{now.year}.md"


def ensure_report_header(path: Path) -> None:
    """Cria o arquivo com cabeçalho se for a primeira tarefa do mês."""
    if path.exists():
        return
    now = datetime.now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Relatório de Atividades PGD - {MESES[now.month - 1].capitalize()}/{now.year}\n",
        encoding="utf-8",
    )


def append_activity(
    *,
    issue_id: int,
    summary: str,
    mr_url: str = "",
    config: dict | None = None,
) -> Path:
    """Adiciona uma atividade ao relatório mensal e retorna o caminho do arquivo."""
    config = config or cfg.load_config()
    path = monthly_report_path(config)
    ensure_report_header(path)

    today = datetime.now().strftime("%d/%m/%Y")
    lines = [f"- **[{today}] Issue #{issue_id}:**"]
    if summary:
        lines.append(f"  - *Resumo IA:* {summary}")
    if mr_url:
        lines.append(f"  - *Evidência:* [Merge Request]({mr_url})")

    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(lines) + "\n")

    return path
