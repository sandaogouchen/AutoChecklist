"""Thin persistence layer for ProjectContext objects.

For the MVP we use a simple in-memory dict.  The interface is intentionally
narrow so it can be swapped for a real DB-backed implementation later.
"""

from __future__ import annotations

from typing import Optional

from app.domain.project_models import ProjectContext


class ProjectRepository:
    """In-memory store keyed by ``ProjectContext.id``."""

    def __init__(self) -> None:
        self._store: dict[str, ProjectContext] = {}

    # -- write -------------------------------------------------------------

    def save(self, project: ProjectContext) -> ProjectContext:
        """Persist (insert or update) a project context."""
        self._store[project.id] = project
        return project

    def delete(self, project_id: str) -> bool:
        """Remove a project context.  Returns *True* if it existed."""
        return self._store.pop(project_id, None) is not None

    # -- read --------------------------------------------------------------

    def get(self, project_id: str) -> Optional[ProjectContext]:
        return self._store.get(project_id)

    def list_all(self) -> list[ProjectContext]:
        return list(self._store.values())
