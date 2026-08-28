"""Notificações do iaw (`--notify`).

Tenta usar o `plyer` (notificações nativas do SO); se indisponível, cai para
uma mensagem no terminal. `plyer` é dependência opcional (extra ``notify``).
"""

from __future__ import annotations


def notify(title: str, message: str) -> None:
    """Exibe uma notificação (desktop ou terminal)."""
    try:
        from plyer import notification  # type: ignore

        notification.notify(title=title, message=message, timeout=8)
    except Exception:  # noqa: BLE001 — fallback silencioso
        print(f"\n🔔 [{title}] {message}")
