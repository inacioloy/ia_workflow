"""Motor Pi Coding Agent (via RPC mode / JSONL).

Comunicação headless com o Pi usando ``pi --mode rpc --no-session``.
Protocolo: comandos JSON em stdin, eventos JSON em stdout (uma linha por
registro). Documentação: docs/rpc.md do pi-coding-agent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .base import AIEngine, EngineResult


class PiCodingEngine(AIEngine):
    name = "pi-coding"

    def generate(
        self,
        prompt: str,
        *,
        context_files: list[str | Path] | None = None,
        working_dir: str | Path | None = None,
        stream: Optional[Callable[[str], None]] = None,
        timeout: float | None = None,
    ) -> EngineResult:
        if shutil.which("pi") is None:
            return EngineResult(
                success=False,
                error="Comando 'pi' não encontrado no PATH. Instale o Pi Coding Agent.",
            )

        full_prompt = self.build_prompt(prompt, context_files)

        cmd = ["pi", "--mode", "rpc", "--no-session"]
        if self.provider:
            cmd += ["--provider", self.provider]
        if self.model:
            cmd += ["--model", self.model]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(working_dir) if working_dir else None,
                bufsize=1,
            )
        except OSError as exc:
            return EngineResult(success=False, error=f"Falha ao iniciar o Pi: {exc}")

        assert proc.stdin is not None and proc.stdout is not None

        # Envia o prompt.
        proc.stdin.write(json.dumps({"type": "prompt", "message": full_prompt}) + "\n")
        proc.stdin.flush()

        collected_text: list[str] = []
        tool_results: list[str] = []
        settled = False

        try:
            for line in proc.stdout:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")

                if etype == "message_update":
                    delta = event.get("assistantMessageEvent", {})
                    if delta.get("type") == "text_delta":
                        chunk = delta.get("delta", "")
                        collected_text.append(chunk)
                        if stream:
                            stream(chunk)
                elif etype == "tool_execution_end":
                    name = event.get("toolName", "tool")
                    is_error = event.get("isError", False)
                    marker = "ERRO" if is_error else "ok"
                    tool_results.append(f"[{name}: {marker}]")
                elif etype == "agent_settled":
                    settled = True
                    break

        finally:
            # Encerra o processo com segurança.
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.wait(timeout=timeout or 30)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=5)

        output = "".join(collected_text).strip()
        if tool_results:
            output += "\n\n[Ferramentas executadas]\n" + "\n".join(tool_results)

        stderr = ""
        if proc.stderr:
            stderr = proc.stderr.read().strip()

        return EngineResult(
            success=settled,
            output=output,
            error=stderr,
        )
