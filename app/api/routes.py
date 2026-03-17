"""API 路由定义模块。

提供以下 HTTP 端点：
- ``GET  /healthz``                          — 健康检查
- ``POST /api/v1/case-generation/runs``      — 创建用例生成任务
- ``GET  /api/v1/case-generation/runs/{id}`` — 查询任务结果
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
from app.services.workflow_service import WorkflowService

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
    """健康检查端点，返回服务名称和版本号。"""
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
    return workflow_service.create_run(payload)


@router.get("/api/v1/case-generation/runs/{run_id}", response_model=CaseGenerationRun)
def get_case_generation_run(
    run_id: str,
    workflow_service: WorkflowService = Depends(_get_workflow_service),
) -> CaseGenerationRun:
    """根据 run_id 查询已完成的任务结果。

    Raises:
        HTTPException(404): 找不到对应的 run_id。
    """
    try:
        return workflow_service.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}") from exc
