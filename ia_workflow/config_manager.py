"""Gerenciamento da configuração global (por máquina/usuário).

A configuração fica em ``~/.config/ia_workflow/config.toml`` e guarda apenas
dados sensíveis/pessoais (tokens, engine preferida, nome do dev, caminho do
relatório). As regras do projeto ficam na pasta ``.iaw/`` do repositório.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore

import tomli_w

CONFIG_DIR = Path.home() / ".config" / "ia_workflow"
CONFIG_PATH = CONFIG_DIR / "config.toml"
REPORTS_DIR = CONFIG_DIR / "reports"

# Chaves válidas e seus valores padrão.
DEFAULT_CONFIG: dict[str, Any] = {
    "gitlab_url": "",
    "gitlab_token": "",
    "gitlab_project": "",
    "skill_repo": "",
    "default_engine": "pi-coding",
    "default_model": "",
    "default_provider": "",
    "default_agent": "",
    "antigravity_skip_permissions": True,
    # Janela de contexto (0 = sem limite). Aplicado pelo motor, independente do engine.
    "context_max_chars": 80000,
    "context_max_file_chars": 20000,
    "dev_name": "",
    "relatorio_path": str(REPORTS_DIR),
    "auto_write_files": True,
    "notify_webhook": "",
    # Gravação de atividades (iaw create --recording).
    "recording_shot_interval": 30,  # segundos entre screenshots
    "recording_summary_model": "gemini-3.8-flash-high",  # modelo rápido p/ resumo por visão
}


def ensure_config_dir() -> Path:
    """Garante que o diretório de configuração existe e o retorna."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def load_config() -> dict[str, Any]:
    """Lê o arquivo de configuração, fundindo com os valores padrão."""
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "rb") as f:
                user_config = tomllib.load(f)
            if isinstance(user_config, dict):
                config.update(user_config)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            # Não derruba a CLI por causa de config corrompida.
            print(f"[iaw] Aviso: não foi possível ler {CONFIG_PATH}: {exc}")
    return config


def save_config(config: dict[str, Any]) -> None:
    """Persiste o dicionário de configuração em TOML."""
    ensure_config_dir()
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(config, f)


def get(key: str, default: Any = None) -> Any:
    """Retorna o valor de uma chave da configuração global."""
    return load_config().get(key, default)


def set(key: str, value: Any) -> None:
    """Define e persiste uma chave na configuração global."""
    config = load_config()
    config[key] = value
    save_config(config)
