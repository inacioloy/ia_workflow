"""Motor Antigravity (Google) via CLI ``agy`` (modo --print, não interativo).

O Antigravity não expõe API key; a integração é feita pelo próprio CLI oficial
(``agy``), que usa o OAuth já configurado na máquina do desenvolvedor. O motor
executa ``agy --print`` em modo JSON, lê o ``response`` e devolve como resultado.

Exige: ``agy`` no PATH (instalado pelo Antigravity/Gemini CLI). Configure com:

    iaw config set default_engine antigravity
    iaw config set default_model gemini-3.1-pro-high   # opcional
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .base import AIEngine, EngineResult


class AntigravityEngine(AIEngine):
    name = "antigravity"

    def __init__(
        self,
        *,
        agent: str | None = None,
        skip_permissions: bool | None = None,
        mode: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.agent = agent
        # None => decide pelo auto_write_files (verdadeiro por padrão).
        self.skip_permissions = skip_permissions
        self.mode = mode
        # Reuso de sessão dentro de um mesmo workflow (conversa contínua).
        self.conversation_id: str | None = None

    def generate(
        self,
        prompt: str,
        *,
        context_files: list[str | Path] | None = None,
        working_dir: str | Path | None = None,
        stream: Optional[Callable[[str], None]] = None,
        timeout: float | None = None,
    ) -> EngineResult:
        if shutil.which("agy") is None:
            return EngineResult(
                success=False,
                error=(
                    "Comando 'agy' não encontrado no PATH. Instale o Antigravity CLI "
                    "(Google/Gemini) e garanta que 'agy' esteja acessível."
                ),
            )

        cwd = Path(working_dir).resolve() if working_dir else Path.cwd()
        full_prompt = self.build_prompt(prompt, context_files)

        # O `agy --print` roda no home do usuário, então instruímos o agente a
        # trabalhar com caminhos absolutos no diretório do projeto e adicionamos
        # esse diretório ao workspace do agente via --add-dir.
        header = (
            f"Você está trabalhando no diretório: {cwd}\n"
            "Use caminhos ABSOLUTOS dentro desse diretório para ler, editar e criar "
            "arquivos.\n\n"
        )
        full_prompt = header + full_prompt

        cmd = ["agy", "--print", full_prompt, "--output-format", "json"]
        if self.model:
            cmd += ["--model", self.model]
        if self.agent:
            cmd += ["--agent", self.agent]
        cmd += ["--add-dir", str(cwd)]
        # Continua a conversa anterior do workflow (mantém o contexto entre etapas).
        if self.conversation_id:
            cmd += ["--conversation", self.conversation_id]

        if self.mode:
            cmd += ["--mode", self.mode]
        elif self.auto_write_files is False:
            cmd += ["--mode", "plan"]  # não edita arquivos, apenas planeja

        # Sem --dangerously-skip-permissions o modo --print (não interativo) não
        # consegue aprovar as ferramentas, travando etapas de código.
        skip = self.skip_permissions
        if skip is None:
            skip = self.auto_write_files
        if skip:
            cmd.append("--dangerously-skip-permissions")

        if timeout:
            cmd += ["--print-timeout", f"{int(timeout)}s"]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=(timeout + 30) if timeout else None,
            )
        except subprocess.TimeoutExpired:
            return EngineResult(success=False, error="Timeout ao executar o Antigravity.")

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        # O stdout é um objeto JSON (uma linha). Toleramos ruído antes/depois.
        start, end = stdout.find("{"), stdout.rfind("}")
        data: dict = {}
        if start != -1 and end != -1:
            try:
                parsed = json.loads(stdout[start : end + 1])
                if isinstance(parsed, dict):
                    data = parsed
            except json.JSONDecodeError:
                data = {}

        response = str(data.get("response", "")).strip()
        status = str(data.get("status", "")).upper()
        error = str(data.get("error", "")).strip()
        if data.get("conversation_id"):
            self.conversation_id = str(data["conversation_id"])

        if stream and response:
            stream(response)

        if status in {"SUCCESS", "OK"} or result.returncode == 0:
            return EngineResult(success=True, output=response or stdout, error=error or stderr)

        return EngineResult(
            success=False,
            output=response or stdout,
            error=error or stderr or f"Antigravity encerrou com status '{status or result.returncode}'.",
        )
