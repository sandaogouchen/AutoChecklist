"""API 路由定义模块。

提供以下 HTTP 端点：
- ``GET  /healthz``                          — 健康检查
- ``POST /api/v1/case-generation/runs``      — 创建用例生成任务
- ``GET  /api/v1/case-generation/runs/{id}`` — 查询任务结果
- ``GET  /api/v1/templates``                 — 列出可用模版
- ``GET  /api/v1/templates/{name}``          — 获取指定模版详情
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
from app.services.template_loader import ProjectTemplateLoader, TemplateValidationError
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# 依赖注入辅助函数
# ---------------------------------------------------------------------------

def _get_settings(request: Request) -> Settings:
    """从 app.state 中获取全局配置。"""
    return request.app.state.settings


def _get_workflow_service(request: Request) -> WorkflowService:
    """从 app.state 中获取工作流服务实例。"""
    return request.app.state.workflow_service


# ---------------------------------------------------------------------------
# 端点定义
# ---------------------------------------------------------------------------

@router.get("/healthz")
def healthz(settings: Settings = Depends(_get_settings)) -> dict[str, str]:
    """健康检查端点。"""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.post("/api/v1/case-generation/runs", response_model=CaseGenerationRun)
def create_case_generation_run(
    payload: CaseGenerationRequest,
    workflow_service: WorkflowService = Depends(_get_workflow_service),
) -> CaseGenerationRun:
    """创建一次用例生成任务，同步执行工作流并返回结果。"""
    try:
        return workflow_service.create_run(payload)
    except FileNotFoundError as exc:
        # 传入的 file_id / template_file_id / reference_xmind_file_id 不存在，
        # 属于请求参数错误，应返回 4xx 而不是 500。
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/v1/case-generation/runs/{run_id}", response_model=CaseGenerationRun)
def get_case_generation_run(
    run_id: str,
    workflow_service: WorkflowService = Depends(_get_workflow_service),
) -> CaseGenerationRun:
    """根据 run_id 查询已完成的任务结果。"""
    try:
        return workflow_service.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}") from exc


@router.get("/api/v1/templates")
def list_templates(
    settings: Settings = Depends(_get_settings),
) -> list[dict[str, str]]:
    """列出可用模版。

    扫描 templates/ 目录中的 YAML 文件，返回各模版的名称、版本和描述。
    """
    template_dir = Path(settings.template_dir)
    if not template_dir.exists():
        return []

    loader = ProjectTemplateLoader()
    templates: list[dict[str, str]] = []

    for file_path in sorted(template_dir.glob("*.y*ml")):
        try:
            template = loader.load(file_path)
            templates.append({
                "name": template.metadata.name or file_path.stem,
                "version": template.metadata.version,
                "description": template.metadata.description,
                "file_name": file_path.name,
            })
        except Exception as exc:
            logger.warning("加载模版失败 (%s): %s", file_path.name, exc)

    return templates


@router.get("/api/v1/templates/{name}")
def get_template(
    name: str,
    settings: Settings = Depends(_get_settings),
) -> dict:
    """获取指定模版详情。"""
    loader = ProjectTemplateLoader()
    try:
        template = loader.load_by_name(name, template_dir=settings.template_dir)
        return template.model_dump(mode="json")
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{name}' not found in {settings.template_dir}/ directory",
        )
    except TemplateValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
