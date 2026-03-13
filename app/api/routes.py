from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
from app.services.workflow_service import WorkflowService

router = APIRouter()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_workflow_service(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


@router.get("/healthz")
def healthz(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.post("/api/v1/case-generation/runs", response_model=CaseGenerationRun)
def create_case_generation_run(
    payload: CaseGenerationRequest,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> CaseGenerationRun:
    return workflow_service.create_run(payload)


@router.get("/api/v1/case-generation/runs/{run_id}", response_model=CaseGenerationRun)
def get_case_generation_run(
    run_id: str,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> CaseGenerationRun:
    try:
        return workflow_service.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}") from exc
