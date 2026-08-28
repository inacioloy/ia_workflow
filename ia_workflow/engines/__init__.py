"""Fábrica de motores de IA.

A CLI usa :func:`get_engine` para obter o motor configurado em
``default_engine`` sem conhecer a implementação concreta.
"""

from __future__ import annotations

from .base import AIEngine, EngineResult
from .pi_coding import PiCodingEngine
from .aider import AiderEngine

__all__ = ["AIEngine", "EngineResult", "PiCodingEngine", "AiderEngine", "get_engine", "available_engines"]

ENGINES: dict[str, type[AIEngine]] = {
    "pi-coding": PiCodingEngine,
    "pi": PiCodingEngine,
    "pi_coding": PiCodingEngine,
    "aider": AiderEngine,
}


def available_engines() -> list[str]:
    """Nomes canônicos dos motores suportados."""
    return ["pi-coding", "aider"]


def get_engine(name: str, **kwargs: object) -> AIEngine:
    """Retorna uma instância do motor solicitado.

    :raises ValueError: se o motor não for suportado.
    """
    key = name.strip().lower()
    cls = ENGINES.get(key)
    if cls is None:
        raise ValueError(
            f"Motor '{name}' não suportado. Opções: {', '.join(available_engines())}."
        )
    return cls(**kwargs)


def build_engine(**kwargs: object) -> AIEngine:
    """Instancia o motor de IA configurado globalmente (``default_engine``)."""
    from .. import config_manager as cfg

    config = cfg.load_config()
    name = config.get("default_engine", "pi-coding")
    kwargs.setdefault("auto_write_files", config.get("auto_write_files", True))
    return get_engine(name, **kwargs)
