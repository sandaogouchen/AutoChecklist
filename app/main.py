"""FastAPI 应用工厂。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.project_routes import router as project_router
from app.api.routes import router as core_router
from app.api.template_routes import router as template_router
from app.clients.llm import LLMClient
from app.config.settings import get_settings
from app.repositories.project_repository import ProjectRepository
from app.repositories.run_repository import FileRunRepository
from app.repositories.run_state_repository import RunStateRepository
from app.repositories.template_repository import TemplateRepository
from app.services.project_context_service import ProjectContextService
from app.services.template_service import TemplateService
from app.services.template_validator import TemplateValidator
from app.services.workflow_service import WorkflowService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理。"""
    settings = get_settings()

    # 初始化基础设施
    llm_client = LLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
    run_repo = FileRunRepository(root_dir=settings.output_dir)
    run_state_repo = RunStateRepository(root_dir=settings.output_dir)
    project_repo = ProjectRepository()

    # ---- 模板基础设施 ----
    template_repo = TemplateRepository()
    template_validator = TemplateValidator()
    template_service = TemplateService(
        repository=template_repo,
        validator=template_validator,
    )

    # 初始化服务
    project_service = ProjectContextService(repository=project_repo)
    workflow_service = WorkflowService(
        llm_client=llm_client,
        run_repository=run_repo,
        run_state_repository=run_state_repo,
        project_service=project_service,
        template_service=template_service,
    )

    # 挂载到应用状态
    app.state.llm_client = llm_client
    app.state.run_repo = run_repo
    app.state.run_state_repo = run_state_repo
    app.state.project_repo = project_repo
    app.state.project_service = project_service
    app.state.workflow_service = workflow_service
    app.state.template_service = template_service

    yield


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title="AutoChecklist",
        description="基于 LLM 的自动化测试用例生成服务",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(core_router)
    app.include_router(project_router)
    app.include_router(template_router)
    return app
