"""API 路由定义模块。

提供以下 HTTP 端点：
- ``GET  /healthz``                          — 健康检查
- ``POST /api/v1/case-generation/runs``      — 创建用例生成任务（异步提交，立即返回 run_id）
- ``GET  /api/v1/case-generation/runs/{id}`` — 查询任务结果
- ``GET  /api/v1/templates``                 — 分页列出模板文件
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
from app.domain.file_models import StoredFile, StoredFilePage
from app.services.file_service import FileService
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


def _get_file_service(request: Request) -> FileService:
    return request.app.state.file_service


def _require_admin(
    settings: Settings = Depends(_get_settings),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    expected = (settings.admin_api_key or "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="管理员上传未启用")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="管理员鉴权失败")


class RenameRunXMindRequest(BaseModel):
    file_name: str = Field(..., min_length=1)


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


@router.post(
    "/api/v1/case-generation/runs",
    response_model=CaseGenerationRun,
    status_code=202,
)
async def create_case_generation_run(
    payload: CaseGenerationRequest,
    workflow_service: WorkflowService = Depends(_get_workflow_service),
) -> CaseGenerationRun:
    """创建一次用例生成任务，异步执行工作流并立即返回 run_id。"""
    try:
        return workflow_service.submit_run(payload)
    except (FileNotFoundError, ValueError) as exc:
        # 传入的 file_id / template_file_id / reference_xmind_file_id 不存在，
        # 属于请求参数错误，应返回 4xx 而不是 500。
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/v1/case-generation/runs/xmind-files", response_model=list[StoredFile])
def list_run_xmind_files(
    file_service: FileService = Depends(_get_file_service),
) -> list[StoredFile]:
    """获取历史 runs 生成的 XMind 文件列表（仅生成产物）。"""
    return file_service.list_run_xmind_files()


@router.post(
    "/api/v1/case-generation/runs/xmind-files",
    response_model=StoredFile,
    status_code=201,
    dependencies=[Depends(_require_admin)],
)
async def upload_admin_xmind_file(
    file: UploadFile = File(...),
    settings: Settings = Depends(_get_settings),
    file_service: FileService = Depends(_get_file_service),
) -> StoredFile:
    """管理员上传 XMind 文件，并纳入历史 XMind 列表。"""
    content = await file.read()
    await file.close()

    if not content:
        raise HTTPException(status_code=422, detail="上传文件不能为空")
    if len(content) > settings.admin_xmind_upload_max_bytes:
        raise HTTPException(status_code=413, detail="上传文件超过大小限制")

    try:
        return file_service.create_admin_xmind_file(
            file_name=file.filename or "upload.xmind",
            content=content,
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/api/v1/case-generation/runs/xmind-files/{file_id}", response_model=StoredFile)
def rename_run_xmind_file(
    file_id: str,
    payload: RenameRunXMindRequest,
    file_service: FileService = Depends(_get_file_service),
) -> StoredFile:
    """修改某个历史 runs 生成的 XMind 文件名称。"""
    meta = file_service.get_file(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"文件未找到: {file_id}")

    tags = meta.tags or []
    if "generated_artifact" not in tags or "type:xmind" not in tags:
        raise HTTPException(status_code=422, detail="仅允许修改 runs 生成的 XMind 产物")

    updated = file_service.rename_file(file_id, payload.file_name)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"文件未找到: {file_id}")
    return updated


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


@router.get("/api/v1/templates", response_model=StoredFilePage)
def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    file_service: FileService = Depends(_get_file_service),
) -> StoredFilePage:
    """分页列出模板文件。"""
    return file_service.list_template_files(page=page, page_size=page_size)
