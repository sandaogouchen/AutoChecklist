"""FastAPI application entry-point for AutoChecklist."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.project_routes import router as project_router
from app.domain.api_models import RunRequest, RunResponse
from app.services.workflow_service import WorkflowService

app = FastAPI(title="AutoChecklist", version="0.2.0")

# -- routers ---------------------------------------------------------------
app.include_router(project_router)

# -- module-level service instances ----------------------------------------
_workflow_service = WorkflowService()


@app.post("/run", response_model=RunResponse)
def run_workflow(body: RunRequest):
    record = _workflow_service.run(
        case_id=body.case_id,
        project_id=body.project_id,
        options=body.options,
    )
    return RunResponse(
        run_id=record.run_id,
        status=record.status.value,
        result=record.result,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
