"""FastAPI 应用入口。

职责：创建 FastAPI 实例、注入配置与服务依赖、注册路由。
支持通过参数覆盖 settings / workflow_service，方便测试时注入 mock 对象。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router
from app.config.settings import Settings, get_settings
from app.services.workflow_service import WorkflowService
from app.api.project_routes import router as project_router
from app.repositories.project_repository import ProjectRepository
from app.services.project_context_service import ProjectContextService

# ---- 模板驱动生成支持：导入模板基础设施 ----
from app.api.template_routes import router as template_router
from app.repositories.template_repository import TemplateRepository
from app.services.template_service import TemplateService
from app.services.template_validator import TemplateValidator


def create_app(
    settings: Settings | None = None,
    workflow_service: WorkflowService | None = None,
) -> FastAPI:
    """工厂函数：构建并配置 FastAPI 应用实例。

    Args:
        settings: 可选的自定义配置，为 None 时从环境/.env 自动加载。
        workflow_service: 可选的工作流服务实例，为 None 时自动创建。

    Returns:
        配置完毕的 FastAPI 应用实例。
    """
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=app_settings.app_version)

    # 将配置和服务绑定到 app.state，供路由通过 Depends 获取
    app.state.settings = app_settings

    # 项目上下文服务
    project_repo = ProjectRepository()
    project_context_service = ProjectContextService(project_repo)
    app.state.project_context_service = project_context_service

    # ---- 模板基础设施初始化 ----
    template_repo = TemplateRepository()
    template_validator = TemplateValidator()
    template_service = TemplateService(
        repository=template_repo, validator=template_validator
    )
    app.state.template_service = template_service

    app.state.workflow_service = workflow_service or WorkflowService(
        app_settings,
        project_context_service=project_context_service,
        template_service=template_service,
    project_db_path = Path(app_settings.output_dir) / "projects.sqlite3"
    default_project_service = ProjectContextService(
        ProjectRepository(db_path=project_db_path)
    )

    if workflow_service is not None:
        project_context_service = (
            workflow_service.project_context_service or default_project_service
        )
        workflow_service.project_context_service = project_context_service
        app.state.workflow_service = workflow_service
    else:
        project_context_service = default_project_service
        app.state.workflow_service = WorkflowService(
            app_settings,
            project_context_service=project_context_service,
        )

    app.state.project_context_service = project_context_service

    app.include_router(router)
    app.include_router(project_router)
    app.include_router(template_router)
    return app


# 模块级别的默认应用实例，供 uvicorn 直接引用
app = create_app()
