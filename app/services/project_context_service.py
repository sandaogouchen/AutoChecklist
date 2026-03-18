"""Application-level service that sits between the API layer and the
repository for project context operations.

Business rules (validation beyond Pydantic, cross-cutting concerns) live here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.domain.project_models import ProjectContext, ProjectType, RegulatoryFramework
from app.repositories.project_repository import ProjectRepository


class ProjectContextService:
    """Manages CRUD + lookup for :class:`ProjectContext` objects."""

    def __init__(self, repo: Optional[ProjectRepository] = None) -> None:
        self._repo = repo or ProjectRepository()

    # -- commands ----------------------------------------------------------

    def create_project(
        self,
        name: str,
        description: str = "",
        project_type: ProjectType = ProjectType.OTHER,
        regulatory_frameworks: Optional[list[RegulatoryFramework]] = None,
        tech_stack: Optional[list[str]] = None,
        custom_standards: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> ProjectContext:
        project = ProjectContext(
            name=name,
            description=description,
            project_type=project_type,
            regulatory_frameworks=regulatory_frameworks or [],
            tech_stack=tech_stack or [],
            custom_standards=custom_standards or [],
            metadata=metadata or {},
        )
        return self._repo.save(project)

    def update_project(self, project_id: str, **updates) -> ProjectContext:
        existing = self._repo.get(project_id)
        if existing is None:
            raise KeyError(f"Project '{project_id}' not found")
        data = existing.model_dump()
        data.update(updates)
        data["updated_at"] = datetime.utcnow()
        updated = ProjectContext(**data)
        return self._repo.save(updated)

    def delete_project(self, project_id: str) -> bool:
        return self._repo.delete(project_id)

    # -- queries -----------------------------------------------------------

    def get_project(self, project_id: str) -> Optional[ProjectContext]:
        return self._repo.get(project_id)

    def list_projects(self) -> list[ProjectContext]:
        return self._repo.list_all()
