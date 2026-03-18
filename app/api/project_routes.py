"""FastAPI router for project-context CRUD endpoints.

Mounted under ``/projects`` in the main application.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.domain.project_models import ProjectType, RegulatoryFramework
from app.services.project_context_service import ProjectContextService

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_project_service(request: Request) -> ProjectContextService:
    """FastAPI dependency that retrieves the shared ProjectContextService
    instance from ``app.state``.

    This ensures the API layer and the workflow layer share the same
    service (and therefore the same in-memory repository).
    """
    return request.app.state.project_context_service


# -- request / response schemas -------------------------------------------

class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    project_type: ProjectType = ProjectType.OTHER
    regulatory_frameworks: list[RegulatoryFramework] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    custom_standards: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    project_type: Optional[ProjectType] = None
    regulatory_frameworks: Optional[list[RegulatoryFramework]] = None
    tech_stack: Optional[list[str]] = None
    custom_standards: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


# -- endpoints ------------------------------------------------------------

@router.post("", status_code=201)
def create_project(
    body: ProjectCreateRequest,
    svc: ProjectContextService = Depends(_get_project_service),
):
    project = svc.create_project(**body.model_dump())
    return project.model_dump()


@router.get("")
def list_projects(
    svc: ProjectContextService = Depends(_get_project_service),
):
    return [p.model_dump() for p in svc.list_projects()]


@router.get("/{project_id}")
def get_project(
    project_id: str,
    svc: ProjectContextService = Depends(_get_project_service),
):
    project = svc.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.model_dump()


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    body: ProjectUpdateRequest,
    svc: ProjectContextService = Depends(_get_project_service),
):
    updates = body.model_dump(exclude_unset=True)
    try:
        updated = svc.update_project(project_id, **updates)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated.model_dump()


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    svc: ProjectContextService = Depends(_get_project_service),
):
    deleted = svc.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return None
