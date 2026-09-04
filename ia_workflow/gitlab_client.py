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

    def current_user(self) -> Any:
        """Retorna o usuário autenticado (para usar como assignee)."""
        try:
            # python-gitlab >= 8 só popula ``gl.user`` após ``gl.auth()``.
            self.gl.auth()
            if self.gl.user is None:
                raise GitLabError("Usuário autenticado não retornado pelo GitLab.")
            return self.gl.user
        except GitLabError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"Não foi possível obter o usuário autenticado: {exc}") from exc

    def create_issue(
        self,
        project_id: str,
        *,
        title: str,
        description: str = "",
        labels: list[str] | None = None,
        issue_type: str = "issue",
    ) -> Any:
        """Cria um work item (Issue ou Task) no GitLab, com assignee = usuário atual."""
        try:
            project = self.get_project(project_id)
            user = self.current_user()
            data: dict[str, Any] = {
                "title": title,
                "description": description,
                "issue_type": issue_type,
                "assignee_ids": [user.id],
            }
            if labels:
                data["labels"] = ",".join(labels)
            return project.issues.create(data)
        except GitLabError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"Não foi possível criar o work item: {exc}") from exc

    def list_issues(
        self,
        project_id: str,
        *,
        state: str = "opened",
        labels: str | None = None,
        author_id: int | None = None,
        assignee_id: int | None = None,
    ) -> list[Any]:
        """Lista Issues do GitLab (opcionalmente por estado, label, autor e assignee)."""
        try:
            project = self.get_project(project_id)
            kwargs: dict[str, Any] = {"state": state, "all": True}
            if labels:
                kwargs["labels"] = labels
            if author_id is not None:
                kwargs["author_id"] = author_id
            if assignee_id is not None:
                kwargs["assignee_id"] = assignee_id
            return list(project.issues.list(**kwargs))
        except GitLabError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"Não foi possível listar as Issues: {exc}") from exc

    def create_merge_request(self, project_id: str, **kwargs: Any) -> Any:
        """Cria um Merge Request (Fase 4 — ainda não usado pelo finish-task)."""
        try:
            project = self.get_project(project_id)
            return project.mergerequests.create(kwargs)
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"Não foi possível criar o MR: {exc}") from exc
