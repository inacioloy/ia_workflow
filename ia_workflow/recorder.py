"""Gravação de atividades (janela ativa) para o fluxo ``iaw create --recording``.

Enquanto o usuário trabalha, um processo em segundo plano registra o título da
janela ativa (com timestamp) num arquivo de log. No ``iaw finish-task``, a
gravação é encerrada e o histórico é usado para sugerir o resumo.

Sem dependências extras: usa ``ctypes`` no Windows e ``xdotool`` no Linux
(quando disponível).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import workspace

SESSION_FILE = workspace.WORKSPACE_ROOT / "recording_session.json"
DEFAULT_INTERVAL = 5.0


def get_active_window_title() -> str:
    """Retorna o título da janela ativa (Windows via ctypes; Linux via xdotool)."""
    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value.strip()
        except Exception:  # noqa: BLE001
            return ""
    if sys.platform.startswith("linux"):
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return ""


def load_session() -> dict[str, Any] | None:
    """Lê a sessão de gravação ativa (se existir)."""
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("iid"):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def clear_session() -> None:
    """Remove o arquivo de sessão de gravação."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def start_recording(
    *,
    iid: int,
    project_id: str,
    title: str,
    interval: float = DEFAULT_INTERVAL,
) -> dict[str, Any]:
    """Cria a sessão de gravação e inicia o processo em segundo plano."""
    if load_session() is not None:
        raise RuntimeError(
            "Já existe uma gravação ativa. Encerre com `iaw finish-task` antes de iniciar outra."
        )

    session_dir = workspace.WORKSPACE_ROOT / "recording" / str(iid)
    session_dir.mkdir(parents=True, exist_ok=True)

    # Limpa resíduos de uma gravação anterior do mesmo work item.
    (session_dir / "activity.log").unlink(missing_ok=True)
    (session_dir / "stop").unlink(missing_ok=True)
    (session_dir / "done").unlink(missing_ok=True)

    session: dict[str, Any] = {
        "iid": iid,
        "project_id": project_id,
        "title": title,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "session_dir": str(session_dir),
        "interval": interval,
    }
    workspace.WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        # No Windows não se pode combinar ``close_fds=True`` com redirecionamento
        # de stdout/stderr (levantaria ValueError). DETACHED_PROCESS + CREATE_NO_WINDOW
        # destacam o processo da console atual sem abrir uma janela nova.
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        kwargs["close_fds"] = True
        kwargs["start_new_session"] = True

    subprocess.Popen(
        [sys.executable, "-m", "ia_workflow.recorder", str(session_dir), str(interval)],
        **kwargs,
    )
    return session


def stop_recording(session: dict[str, Any]) -> str:
    """Para a gravação e retorna o texto do log de atividades."""
    session_dir = Path(session["session_dir"])
    interval = float(session.get("interval", DEFAULT_INTERVAL))
    stop_path = session_dir / "stop"
    done_path = session_dir / "done"

    stop_path.touch()

    deadline = time.time() + interval + 5
    while time.time() < deadline:
        if done_path.exists():
            break
        time.sleep(0.2)

    log_path = session_dir / "activity.log"
    if log_path.exists():
        return log_path.read_text(encoding="utf-8").strip()
    return ""


def record_loop(session_dir: Path, interval: float) -> None:
    """Loop de gravação executado em subprocesso."""
    session_dir = Path(session_dir)
    log_path = session_dir / "activity.log"
    stop_path = session_dir / "stop"
    done_path = session_dir / "done"
    last_title: str | None = None

    try:
        while True:
            title = get_active_window_title()
            if title and title != last_title:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{ts}] {title}\n")
                last_title = title
            if stop_path.exists():
                break
            time.sleep(interval)
    finally:
        done_path.touch()


def main() -> None:
    """Ponto de entrada do subprocesso: ``python -m ia_workflow.recorder``."""
    if len(sys.argv) != 3:
        print(
            "uso: python -m ia_workflow.recorder <session_dir> <intervalo>",
            file=sys.stderr,
        )
        sys.exit(2)
    record_loop(Path(sys.argv[1]), float(sys.argv[2]))


if __name__ == "__main__":
    main()
