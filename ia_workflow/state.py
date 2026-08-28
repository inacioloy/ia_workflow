"""Registro de tarefas do iaw (para `iaw status`).

Persiste um histórico simples de execuções em
``~/.config/ia_workflow/tasks.json``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import config_manager as cfg

STATE_PATH = cfg.CONFIG_DIR / "tasks.json"

STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_DONE = "done"


@dataclass
class TaskRecord:
    id: str
    workflow: str
    status: str = STATUS_RUNNING
    issue_id: int | None = None
    started_at: str = ""
    finished_at: str | None = None
    mr_url: str = ""
    summary: str = ""

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = datetime.now().isoformat(timespec="seconds")


class TaskStore:
    """Leitura/escrita do registro de tarefas em disco."""

    def __init__(self, path: Path = STATE_PATH) -> None:
        self.path = path

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"tasks": []}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def add(self, workflow: str, issue_id: int | None = None) -> TaskRecord:
        """Cria um registro de tarefa em execução."""
        data = self._load()
        record = TaskRecord(
            id=uuid.uuid4().hex[:8], workflow=workflow, issue_id=issue_id
        )
        data["tasks"].append(asdict(record))
        self._save(data)
        return record

    def update(self, task_id: str, **kwargs) -> None:
        """Atualiza campos de uma tarefa existente."""
        data = self._load()
        for task in data["tasks"]:
            if task.get("id") == task_id:
                task.update(kwargs)
                break
        self._save(data)

    def list(self) -> list[dict]:
        """Lista todas as tarefas (mais recentes primeiro)."""
        return list(reversed(self._load()["tasks"]))
