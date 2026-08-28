"""Browser Harness — prova visual com Playwright (headless).

Captura um screenshot da tela alterada no ambiente local, provando que a
funcionalidade/correção renderiza sem erros. Playwright é uma dependência
opcional (extra ``browser``).
"""

from __future__ import annotations

from pathlib import Path


def capture_screenshot(
    url: str,
    output_path: str | Path,
    *,
    headless: bool = True,
    auth_script: str | Path | None = None,
    timeout_ms: int = 30000,
) -> Path:
    """Navega até `url` e salva um screenshot em `output_path`.

    :param auth_script: arquivo JavaScript executado na página após o load
        (para login/sessão de dev, se necessário).
    :raises RuntimeError: se o Playwright não estiver instalado.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright não está instalado. Rode:\n"
            "  pip install 'ia_workflow[browser]'\n"
            "  playwright install chromium"
        ) from exc

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)

        if auth_script:
            script_path = Path(auth_script)
            js = (
                script_path.read_text(encoding="utf-8")
                if script_path.is_file()
                else str(auth_script)
            )
            page.evaluate(js)
            page.wait_for_load_state("networkidle")

        page.screenshot(path=str(output), full_page=True)
        browser.close()

    return output
