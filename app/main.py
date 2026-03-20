"""FastAPI 应用入口。

职责：创建 FastAPI 实例、注入配置与服务依赖、注册路由。
支持通过参数覆盖 settings / workflow_service，方便测试时注入 mock 对象。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router
from app.config.settings import Settings, get_settings
from app.logging import configure_app_logging
from app.services.workflow_service import WorkflowService
from app.api.project_routes import router as project_router
from app.repositories.project_repository import ProjectRepository
from app.services.project_context_service import ProjectContextService


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
    configure_app_logging(level="INFO")
    app = FastAPI(title=app_settings.app_name, version=app_settings.app_version)

    # 将配置和服务绑定到 app.state，供路由通过 Depends 获取
    app.state.settings = app_settings

    # 项目上下文服务
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
    return app


# 模块级别的默认应用实例，供 uvicorn 直接引用
app = create_app()
