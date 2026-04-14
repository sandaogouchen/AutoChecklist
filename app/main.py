"""FastAPI 应用入口。

职责：创建 FastAPI 实例、注入配置与服务依赖、注册路由。
支持通过参数覆盖 settings / workflow_service，方便测试时注入 mock 对象。

新增：GraphRAG 知识检索引擎的生命周期管理和知识库 API 路由注册。
变更：WorkflowService 创建时注入 graphrag_engine，使知识检索节点在运行时自动接入工作流。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router
from app.api.file_routes import router as file_router
from app.config.settings import Settings, get_settings
from app.logging import configure_app_logging
from app.repositories.file_repository import FileRepository
from app.services.workflow_service import WorkflowService
from app.api.project_routes import router as project_router
from app.repositories.project_repository import ProjectRepository
from app.services.file_service import FileService
from app.services.project_context_service import ProjectContextService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """FastAPI 应用生命周期管理。

    启动时：初始化 GraphRAG 引擎（如果启用）。
    关闭时：释放 GraphRAG 引擎资源。
    """
    settings: Settings = app.state.settings

    # ---- 启动：初始化 GraphRAG 引擎 ----
    if settings.enable_knowledge_retrieval:
        try:
            from app.knowledge.graphrag_engine import GraphRAGEngine
            from app.knowledge.ingestion import scan_knowledge_directory

            engine = GraphRAGEngine(settings)
            await engine.initialize()

            if engine.is_ready():
                # 扫描并增量索引新文档
                scanned = scan_knowledge_directory(
                    settings.knowledge_docs_dir,
                    max_doc_size_kb=settings.knowledge_max_doc_size_kb,
                )
                if scanned:
                    await engine.insert_batch(scanned)
                    logger.info("知识文档启动索引完成: %d 文档", len(scanned))

            app.state.graphrag_engine = engine
            logger.info("GraphRAG 引擎已启动")

            # 将引擎注入到 WorkflowService，使知识检索节点可用
            workflow_service = getattr(app.state, "workflow_service", None)
            if workflow_service is not None:
                workflow_service._graphrag_engine = engine
                # 清除缓存的工作流，以便下次调用时带上知识检索节点
                workflow_service._workflow = None
                logger.info("GraphRAG 引擎已注入 WorkflowService")

        except Exception:
            logger.exception("GraphRAG 引擎启动失败，知识检索功能不可用")
            app.state.graphrag_engine = None
    else:
        app.state.graphrag_engine = None

    yield

    # ---- 关闭：释放 GraphRAG 引擎资源 ----
    engine = getattr(app.state, "graphrag_engine", None)
    if engine is not None:
        try:
            await engine.finalize()
            logger.info("GraphRAG 引擎已关闭")
        except Exception:
            logger.exception("GraphRAG 引擎关闭失败")


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
    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        lifespan=_lifespan,
    )

    # 将配置和服务绑定到 app.state，供路由通过 Depends 获取
    app.state.settings = app_settings

    # 项目上下文服务
    project_db_path = Path(app_settings.output_dir) / "projects.sqlite3"
    default_project_service = ProjectContextService(
        ProjectRepository(db_path=project_db_path)
    )
    file_db_path = Path(app_settings.output_dir) / "files.sqlite3"
    default_file_service = FileService(FileRepository(db_path=file_db_path))

    if workflow_service is not None:
        project_context_service = (
            workflow_service.project_context_service or default_project_service
        )
        workflow_service.project_context_service = project_context_service
        if getattr(workflow_service, "file_service", None) is None:
            workflow_service.file_service = default_file_service
        app.state.workflow_service = workflow_service
    else:
        project_context_service = default_project_service
        app.state.workflow_service = WorkflowService(
            app_settings,
            project_context_service=project_context_service,
            file_service=default_file_service,
        )

    app.state.project_context_service = project_context_service
    app.state.file_service = app.state.workflow_service.file_service

    app.include_router(router)
    app.include_router(file_router)
    app.include_router(project_router)

    # ---- 注册知识库管理 API ----
    from app.api.knowledge_routes import router as knowledge_router
    app.include_router(knowledge_router)

    return app


# 模块级别的默认应用实例，供 uvicorn 直接引用
app = create_app()
