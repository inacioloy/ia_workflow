"""Interface abstrata dos motores de IA (Adapter Pattern).

Cada motor (Pi Coding, Aider, etc.) implementa :meth:`AIEngine.generate`.
A CLI só conhece esta interface, então trocar de motor exige apenas mudar
a chave ``default_engine`` na configuração global.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class EngineResult:
    """Resultado de uma chamada ao motor de IA."""

    success: bool
    output: str = ""
    error: str = ""
    files_touched: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # permite `if result:`
        return self.success


class AIEngine(ABC):
    """Contrato mínimo que todo motor de IA deve implementar."""

    name: str = "base"

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        auto_write_files: bool = True,
        **_: object,
    ) -> None:
        self.provider = provider
        self.model = model
        self.auto_write_files = auto_write_files

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        context_files: list[str | Path] | None = None,
        working_dir: str | Path | None = None,
        stream: Optional[Callable[[str], None]] = None,
        timeout: float | None = None,
    ) -> EngineResult:
        """Gera código/texto a partir de um prompt.

        :param prompt: Instrução (geralmente vinda de um artefato validado).
        :param context_files: Arquivos de contexto a anexar ao prompt.
        :param working_dir: Diretório onde o motor deve executar.
        :param stream: Callback opcional para receber texto em tempo real.
        :param timeout: Tempo máximo (segundos) para a execução.
        """

    def build_prompt(self, prompt: str, context_files: list[str | Path] | None) -> str:
        """Monta o prompt final anexando o conteúdo dos arquivos de contexto."""
        if not context_files:
            return prompt

        sections = [prompt, "\n\n--- CONTEXTO (arquivos do projeto) ---"]
        for path in context_files:
            path = Path(path)
            if path.is_file():
                sections.append(f"\n### {path}\n```\n{path.read_text(encoding='utf-8')}\n```")
        return "\n".join(sections)
