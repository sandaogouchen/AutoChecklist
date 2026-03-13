from fastapi import FastAPI

from app.api.routes import router
from app.config.settings import Settings, get_settings
from app.services.workflow_service import WorkflowService


def create_app(
    settings: Settings | None = None,
    workflow_service: WorkflowService | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=app_settings.app_version)
    app.state.settings = app_settings
    app.state.workflow_service = workflow_service or WorkflowService(app_settings)
    app.include_router(router)
    return app


app = create_app()
