"""Motor Aider (via subprocess, modo não interativo)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .base import AIEngine, EngineResult


class AiderEngine(AIEngine):
    name = "aider"

    def generate(
        self,
        prompt: str,
        *,
        context_files: list[str | Path] | None = None,
        working_dir: str | Path | None = None,
        stream: Optional[Callable[[str], None]] = None,
        timeout: float | None = None,
    ) -> EngineResult:
        if shutil.which("aider") is None:
            return EngineResult(
                success=False,
                error="Comando 'aider' não encontrado no PATH. Instale o Aider.",
            )

        full_prompt = self.build_prompt(prompt, context_files)

        cmd = ["aider", "--message", full_prompt]
        if self.auto_write_files:
            cmd.insert(1, "--yes")  # aceita edições sem perguntar
        cmd.insert(1, "--no-auto-commits")  # a CLI faz o commit, não o motor
        if self.model:
            cmd += ["--model", self.model]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(working_dir) if working_dir else None,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return EngineResult(success=False, error="Timeout ao executar o Aider.")

        output = result.stdout.strip()
        if stream:
            stream(output)

        return EngineResult(
            success=result.returncode == 0,
            output=output,
            error=result.stderr.strip(),
        )
