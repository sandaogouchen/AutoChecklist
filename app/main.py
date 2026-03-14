import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config.settings import Settings, get_settings
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)


async def log_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "请求校验失败：path=%s, method=%s, errors=%s",
        request.url.path,
        request.method,
        exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


def create_app(
    settings: Settings | None = None,
    workflow_service: WorkflowService | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=app_settings.app_version)
    app.state.settings = app_settings
    app.state.workflow_service = workflow_service or WorkflowService(app_settings)
    app.add_exception_handler(RequestValidationError, log_request_validation_error)
    app.include_router(router)
    return app


app = create_app()
