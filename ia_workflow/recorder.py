"""Gravação de atividades para o fluxo ``iaw create --recording``.

Enquanto o usuário trabalha, um processo em segundo plano registra:

- o **título da janela ativa** (com timestamp) num arquivo de log;
- **screenshots periódicos** da tela (todos os monitores).

A captura é adaptada ao ambiente:

- **Windows nativo**: ``ctypes`` (título) e ``mss`` (screenshot);
- **WSL**: ``powershell.exe`` via interop captura a tela/janela do **Windows**
  (é o desktop real do usuário, não o display vazio do WSL);
- **Linux**: ``xdotool`` (título) e ``mss`` (screenshot).

No ``iaw finish-task``, a gravação é encerrada e o histórico (screenshots +
títulos) é usado para sugerir o resumo.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import workspace

SESSION_FILE = workspace.WORKSPACE_ROOT / "recording_session.json"
DEFAULT_INTERVAL = 5.0
DEFAULT_SHOT_INTERVAL = 20.0
MAX_SHOTS_FOR_SUMMARY = 24

_IS_WSL: bool | None = None


def _is_wsl() -> bool:
    """Detecta execução dentro do WSL (Windows Subsystem for Linux)."""
    global _IS_WSL
    if _IS_WSL is None:
        try:
            _IS_WSL = (
                "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
            )
        except OSError:
            _IS_WSL = False
    return _IS_WSL


def _powershell(script: str, timeout: int = 30) -> str:
    """Executa um script no Windows via interop do WSL e retorna o stdout."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return (result.stdout or "").strip() if result.returncode == 0 else ""


def _windows_path_to_wsl(win_path: str) -> Path | None:
    """Converte ``C:\\Users\\...`` em ``/mnt/c/Users/...``."""
    p = win_path.strip().replace("\\", "/")
    m = re.match(r"^([A-Za-z]):(.*)$", p)
    if not m:
        return None
    return Path(f"/mnt/{m.group(1).lower()}{m.group(2)}")


def _wsl_window_title() -> str:
    """Título da janela ativa do **Windows** (via PowerShell no WSL)."""
    script = (
        'Add-Type @"\n'
        'using System;\n'
        'using System.Runtime.InteropServices;\n'
        'using System.Text;\n'
        'public class IawWin32 {\n'
        '  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();\n'
        '  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);\n'
        '  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);\n'
        '  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);\n'
        '}\n'
        '"@\n'
        '$h = [IawWin32]::GetForegroundWindow()\n'
        'if ($h -eq [IntPtr]::Zero) { exit 0 }\n'
        '$len = [IawWin32]::GetWindowTextLength($h)\n'
        '$sb = New-Object System.Text.StringBuilder ([Math]::Max($len + 1, 1))\n'
        '[IawWin32]::GetWindowText($h, $sb, $sb.Capacity) | Out-Null\n'
        '$title = $sb.ToString()\n'
        'if ([string]::IsNullOrWhiteSpace($title)) {\n'
        '  $wpid = 0\n'
        '  [IawWin32]::GetWindowThreadProcessId($h, [ref]$wpid) | Out-Null\n'
        '  if ($wpid -ne 0) { try { $title = (Get-Process -Id $wpid -ErrorAction Stop).ProcessName } catch { $title = "" } }\n'
        '}\n'
        'Write-Output $title\n'
    )
    return _powershell(script, timeout=8)


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
    """Retorna um rótulo da janela ativa (Windows nativo, WSL ou Linux)."""
    if sys.platform == "win32":
        try:
            title, proc = _windows_foreground()
            # Prefere o título; quando a janela não expõe título, usa o processo.
            return title or proc
        except Exception:  # noqa: BLE001
            return ""
    if sys.platform.startswith("linux"):
        if _is_wsl():
            return _wsl_window_title()
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


def _wsl_capture(shots_dir: Path, name: str) -> str | None:
    """Captura a tela do **Windows** (todos os monitores) via PowerShell no WSL."""
    script = (
        'Add-Type -AssemblyName System.Drawing\n'
        'Add-Type -AssemblyName System.Windows.Forms\n'
        '$b = [System.Windows.Forms.SystemInformation]::VirtualScreen\n'
        'if ($b.Width -le 0 -or $b.Height -le 0) { exit 1 }\n'
        '$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height\n'
        '$g = [System.Drawing.Graphics]::FromImage($bmp)\n'
        '$g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)\n'
        '$out = Join-Path $env:TEMP ("iaw_shot_" + [DateTime]::Now.ToString("yyyyMMddHHmmssfff") + ".png")\n'
        '$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)\n'
        '$g.Dispose(); $bmp.Dispose()\n'
        'Write-Output $out\n'
    )
    win_out = _powershell(script, timeout=40)
    if not win_out:
        return None
    win_path = win_out.splitlines()[-1]
    wsl_path = _windows_path_to_wsl(win_path)
    if wsl_path is None or not wsl_path.exists():
        return None
    try:
        data = wsl_path.read_bytes()
        wsl_path.unlink(missing_ok=True)
    except OSError:
        return None
    if not data:
        return None
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((1600, 1600))  # preserva a proporção
        out = shots_dir / name.replace(".png", ".jpg")
        img.save(out, "JPEG", quality=70)
        return str(out)
    except Exception:  # noqa: BLE001 — sem Pillow, salva o PNG original
        out = shots_dir / name
        out.write_bytes(data)
        return str(out)


def capture_screenshot(shots_dir: Path, name: str) -> str | None:
    """Captura a tela inteira (todos os monitores) e salva em ``shots_dir``.

    No WSL, captura a tela do **Windows** via PowerShell (interop). Fora do
    WSL, usa ``mss`` (monitor 0 → tela virtual). Com Pillow disponível, diminui
    e salva JPEG; sem Pillow, salva PNG.

    Retorna o caminho do arquivo salvo, ou ``None`` se a captura falhar (o
    gravador continua funcionando só com os títulos de janela).
    """
    if _is_wsl():
        return _wsl_capture(shots_dir, name)
    try:
        import mss
    except ImportError:
        return None
    try:
        # ``MSS`` é o nome em mss>=10; ``mss.mss`` é o fallback para mss<10.
        screenshot_cls = getattr(mss, "MSS", mss.mss)
        with screenshot_cls() as sct:
            monitor = sct.monitors[0]  # tela virtual (todos os monitores)
            shot = sct.grab(monitor)
            try:
                from PIL import Image

                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                img.thumbnail((1600, 1600))  # preserva a proporção
                out = shots_dir / name.replace(".png", ".jpg")
                img.save(out, "JPEG", quality=70)
                return str(out)
            except ImportError:
                pass
            return sct.shot(mon=-1, output=str(shots_dir / name))
    except Exception:  # noqa: BLE001 — sem tela/display não pode travar a gravação
        return None


def list_screenshots(
    session: dict[str, Any], max_shots: int = MAX_SHOTS_FOR_SUMMARY
) -> list[str]:
    """Retorna os caminhos dos screenshots da sessão, amostrados uniformemente.

    Se houver mais de ``max_shots`` imagens, seleciona uma amostra temporal
    (preservando a primeira e a última) para não estourar o contexto do modelo.
    """
    session_dir = Path(session.get("session_dir", ""))
    shots_dir = session_dir / "shots"
    if not shots_dir.is_dir():
        return []
    shots = sorted(
        [p for p in shots_dir.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")],
        key=lambda p: p.name,
    )
    if not shots:
        return []
    if len(shots) <= max_shots:
        return [str(p) for p in shots]
    if max_shots <= 1:
        return [str(shots[0])]
    step = (len(shots) - 1) / (max_shots - 1)
    picked: list[Path] = []
    seen: set[Path] = set()
    for i in range(max_shots):
        p = shots[round(i * step)]
        if p not in seen:
            seen.add(p)
            picked.append(p)
    return [str(p) for p in picked]


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
    shot_interval: float = DEFAULT_SHOT_INTERVAL,
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

    shots_dir = session_dir / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    # Limpa resíduos de uma gravação anterior do mesmo work item.
    (session_dir / "activity.log").unlink(missing_ok=True)
    (session_dir / "recorder.err.log").unlink(missing_ok=True)
    (session_dir / "stop").unlink(missing_ok=True)
    (session_dir / "done").unlink(missing_ok=True)
    for old in shots_dir.glob("*"):
        if old.suffix.lower() in (".png", ".jpg", ".jpeg"):
            old.unlink(missing_ok=True)

    session: dict[str, Any] = {
        "iid": iid,
        "project_id": project_id,
        "title": title,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "session_dir": str(session_dir),
        "shots_dir": str(shots_dir),
        "interval": interval,
        "shot_interval": shot_interval,
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
            [
                sys.executable,
                "-m",
                "ia_workflow.recorder",
                str(session_dir),
                str(interval),
                str(shot_interval),
            ],
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


def record_loop(
    session_dir: Path,
    interval: float,
    shot_interval: float = DEFAULT_SHOT_INTERVAL,
) -> None:
    """Loop de gravação executado em subprocesso."""
    session_dir = Path(session_dir)
    log_path = session_dir / "activity.log"
    shots_dir = session_dir / "shots"
    stop_path = session_dir / "stop"
    done_path = session_dir / "done"
    last_title: str | None = None
    last_shot = 0.0
    shot_index = 0

    try:
        shots_dir.mkdir(parents=True, exist_ok=True)
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

            # Screenshot periódico (todos os monitores), independente da mudança
            # de janela — captura leituras/atividades dentro da mesma janela. Os
            # arquivos ficam em shots/ e são listados por ``list_screenshots``.
            now = time.time()
            if shot_interval > 0 and now - last_shot >= shot_interval:
                last_shot = now
                shot_index += 1
                capture_screenshot(shots_dir, f"{shot_index:04d}.png")

            if stop_path.exists():
                break
            time.sleep(interval)
    finally:
        done_path.touch()


def main() -> None:
    """Ponto de entrada do subprocesso: ``python -m ia_workflow.recorder``."""
    if len(sys.argv) not in (3, 4):
        print(
            "uso: python -m ia_workflow.recorder <session_dir> <intervalo> [shot_interval]",
            file=sys.stderr,
        )
        sys.exit(2)
    session_dir = Path(sys.argv[1])
    interval = float(sys.argv[2])
    shot_interval = float(sys.argv[3]) if len(sys.argv) >= 4 else DEFAULT_SHOT_INTERVAL
    record_loop(session_dir, interval, shot_interval)


if __name__ == "__main__":
    main()
