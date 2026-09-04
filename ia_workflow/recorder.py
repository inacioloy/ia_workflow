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


def _windows_foreground() -> tuple[str, str]:
    """Retorna ``(título, processo)`` da janela ativa no Windows.

    Declara ``restype``/``argtypes`` explícitos porque o padrão do ctypes é
    ``c_int`` (32 bits) — em Windows 64 bits isso **trunca o HWND** e faz a
    leitura do título falhar silenciosamente. Também faz fallback para o nome
    do executável (útil para apps que não expõem título na janela).
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.GetForegroundWindow.restype = wintypes.HWND

    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""

    title = ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()

    proc = ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if handle:
            try:
                buf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                    proc = Path(buf.value).name
            finally:
                kernel32.CloseHandle(handle)

    return title, proc


def get_active_window_title() -> str:
    """Retorna um rótulo da janela ativa (Windows via ctypes; Linux via xdotool)."""
    if sys.platform == "win32":
        try:
            title, proc = _windows_foreground()
            # Prefere o título; quando a janela não expõe título, usa o processo.
            return title or proc
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
    # Caminho absoluto: o subprocesso grava em background e não depende do cwd.
    session_dir = session_dir.resolve()

    # Limpa resíduos de uma gravação anterior do mesmo work item.
    (session_dir / "activity.log").unlink(missing_ok=True)
    (session_dir / "recorder.err.log").unlink(missing_ok=True)
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

    # stderr vai para um arquivo (não DEVNULL) para permitir diagnóstico se o
    # subprocesso falhar ao iniciar.
    err_file = (session_dir / "recorder.err.log").open("wb")
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": err_file,
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

    try:
        subprocess.Popen(
            [sys.executable, "-m", "ia_workflow.recorder", str(session_dir), str(interval)],
            **kwargs,
        )
    finally:
        err_file.close()
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
        # Marca o início da gravação: confirma que o processo subiu mesmo que
        # nenhuma mudança de janela seja detectada depois.
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(
                f"# gravação iniciada em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )

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
