"""Cliente GitLab (python-gitlab) usado pelo iaw.

Fase 2: conexão + leitura de Issues para o fluxo "Task-First".
"""

from __future__ import annotations

from typing import Any

import gitlab

from . import config_manager as cfg


class GitLabError(RuntimeError):
    """Erro de integração com o GitLab."""


class GitLabClient:
    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        config = cfg.load_config()
        self.url = (url or config.get("gitlab_url") or "").rstrip("/")
        self.token = token or config.get("gitlab_token") or ""
        self._gl: gitlab.Gitlab | None = None

    @property
    def gl(self) -> gitlab.Gitlab:
        if self._gl is None:
            if not self.token:
                raise GitLabError(
                    "Token do GitLab não configurado. Rode `iaw setup` ou "
                    "`iaw config set gitlab_token <token>`."
                )
            if not self.url:
                raise GitLabError(
                    "URL do GitLab não configurada. Rode `iaw config set gitlab_url <url>`."
                )
            self._gl = gitlab.Gitlab(self.url, private_token=self.token)
        return self._gl

    def get_project(self, project_id: str) -> Any:
        """Retorna o projeto pelo path (ex: 'cosinf/suap') ou id numérico."""
        try:
            return self.gl.projects.get(project_id)
        except Exception as exc:  # noqa: BLE001 — reaproveita a mensagem original
            raise GitLabError(f"Não foi possível acessar o projeto '{project_id}': {exc}") from exc

    def get_issue(self, project_id: str, issue_id: int) -> Any:
        """Retorna uma Issue do GitLab."""
        try:
            project = self.get_project(project_id)
            return project.issues.get(issue_id)
        except GitLabError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"Não foi possível acessar a Issue #{issue_id}: {exc}") from exc

    def create_merge_request(self, project_id: str, **kwargs: Any) -> Any:
        """Cria um Merge Request (Fase 4 — ainda não usado pelo finish-task)."""
        try:
            project = self.get_project(project_id)
            return project.mergerequests.create(kwargs)
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"Não foi possível criar o MR: {exc}") from exc
