"""Checklist 模板 CRUD REST API 路由。

提供完整的模板管理 API：
- POST /api/v1/templates             创建模板
- GET  /api/v1/templates             查询模板列表
- POST /api/v1/templates/validate    校验模板格式
- POST /api/v1/templates/import      导入 YAML
- GET  /api/v1/templates/{id}        获取模板详情
- PUT  /api/v1/templates/{id}        全量更新模板
- PATCH /api/v1/templates/{id}       部分更新模板
- DELETE /api/v1/templates/{id}      删除模板
- POST /api/v1/templates/{id}/duplicate  复制模板
- GET  /api/v1/templates/{id}/export 导出 YAML
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.template_service import (
    TemplateConflictError,
    TemplateNotFoundError,
    TemplatePermissionError,
    TemplateService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


# ── 请求/响应模型 ────────────────────────────────────────


class TemplateCreateRequest(BaseModel):
    """创建/更新模板请求体。"""
    content: str = Field(..., description="模板内容（YAML 或 JSON 字符串）")
    format: str = Field(default="yaml", description="输入格式: yaml | json")


class TemplatePatchRequest(BaseModel):
    """部分更新模板请求体。"""
    updates: dict[str, Any] = Field(..., description="要更新的字段")


class TemplateValidateRequest(BaseModel):
    """模板校验请求体。"""
    content: str = Field(..., description="模板内容")
    format: str = Field(default="yaml", description="输入格式: yaml | json")


# ── 路由 ──────────────────────────────────────────────
# 注意：固定路径路由（validate、import）必须在路径参数路由（{template_id}）
# 之前注册，否则 FastAPI 会将 "validate" / "import" 当作 template_id 匹配。


# 1. POST "" — 创建模板
@router.post("", status_code=201)
async def create_template(
    body: TemplateCreateRequest,
    request: Request,
) -> dict[str, Any]:
    """创建新模板。"""
    service: TemplateService = request.app.state.template_service
    try:
        template = service.create(body.content, body.format)
        return {
            "template_id": template.id,
            "metadata": {
                "name": template.metadata.name,
                "version": template.metadata.version,
                "created_at": template.metadata.created_at.isoformat(),
            },
            "categories_count": len(template.categories),
            "total_items_count": template.total_items_count(),
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except TemplateConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


# 2. GET "" — 查询模板列表
@router.get("")
async def list_templates(
    request: Request,
    tag: Optional[str] = Query(None, description="按标签过滤"),
    project_type: Optional[str] = Query(None, description="按适用项目类型过滤"),
    source: Optional[str] = Query(None, description="builtin / custom / all"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> dict[str, Any]:
    """查询模板列表。"""
    service: TemplateService = request.app.state.template_service

    # source="all" 等同于不过滤
    effective_source = None if source == "all" else source

    return service.list_templates(
        source=effective_source,
        tag=tag,
        project_type=project_type,
        page=page,
        page_size=page_size,
    )


# 3. POST "/validate" — 校验模板格式（固定路径，必须在 {template_id} 之前）
@router.post("/validate")
async def validate_template(
    body: TemplateValidateRequest,
    request: Request,
) -> dict[str, Any]:
    """校验模板格式（不保存）。"""
    service: TemplateService = request.app.state.template_service
    result = service.validate(body.content, body.format)
    return result.to_dict()


# 4. POST "/import" — 导入 YAML（固定路径，必须在 {template_id} 之前）
@router.post("/import", status_code=201)
async def import_template(
    request: Request,
    file: UploadFile = File(..., description="YAML 模板文件"),
) -> dict[str, Any]:
    """导入 YAML 文件创建模板。"""
    service: TemplateService = request.app.state.template_service

    # 检查文件大小（1MB 限制）
    content = await file.read()
    if len(content) > 1_048_576:
        raise HTTPException(status_code=413, detail="文件大小不能超过 1MB")

    try:
        yaml_content = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件必须为 UTF-8 编码")

    try:
        template = service.import_yaml(yaml_content)
        return {
            "template_id": template.id,
            "metadata": {
                "name": template.metadata.name,
                "version": template.metadata.version,
                "created_at": template.metadata.created_at.isoformat(),
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# 5. GET "/{template_id}" — 获取模板详情
@router.get("/{template_id}")
async def get_template(
    template_id: str,
    request: Request,
) -> dict[str, Any]:
    """获取模板详情。"""
    service: TemplateService = request.app.state.template_service
    try:
        template = service.get(template_id)
        return template.model_dump(mode="json")
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# 6. PUT "/{template_id}" — 全量更新模板
@router.put("/{template_id}")
async def update_template(
    template_id: str,
    body: TemplateCreateRequest,
    request: Request,
) -> dict[str, Any]:
    """全量更新模板。"""
    service: TemplateService = request.app.state.template_service
    try:
        template = service.update(template_id, body.content, body.format)
        return {
            "template_id": template.id,
            "metadata": {
                "name": template.metadata.name,
                "version": template.metadata.version,
                "updated_at": template.metadata.updated_at.isoformat(),
            },
            "categories_count": len(template.categories),
            "total_items_count": template.total_items_count(),
        }
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TemplatePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except TemplateConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


# 7. PATCH "/{template_id}" — 部分更新模板
@router.patch("/{template_id}")
async def partial_update_template(
    template_id: str,
    body: TemplatePatchRequest,
    request: Request,
) -> dict[str, Any]:
    """部分更新模板。"""
    service: TemplateService = request.app.state.template_service
    try:
        template = service.partial_update(template_id, body.updates)
        return {
            "template_id": template.id,
            "metadata": {
                "name": template.metadata.name,
                "version": template.metadata.version,
                "updated_at": template.metadata.updated_at.isoformat(),
            },
        }
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TemplatePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except TemplateConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


# 8. DELETE "/{template_id}" — 删除模板
@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    request: Request,
) -> None:
    """删除模板。"""
    service: TemplateService = request.app.state.template_service
    try:
        service.delete(template_id)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TemplatePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# 9. POST "/{template_id}/duplicate" — 复制模板
@router.post("/{template_id}/duplicate", status_code=201)
async def duplicate_template(
    template_id: str,
    request: Request,
) -> dict[str, Any]:
    """复制模板（创建副本）。"""
    service: TemplateService = request.app.state.template_service
    try:
        template = service.duplicate(template_id)
        return {
            "template_id": template.id,
            "metadata": {
                "name": template.metadata.name,
                "version": template.metadata.version,
                "created_at": template.metadata.created_at.isoformat(),
            },
        }
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# 10. GET "/{template_id}/export" — 导出 YAML
@router.get("/{template_id}/export")
async def export_template(
    template_id: str,
    request: Request,
) -> Response:
    """导出模板为 YAML 文件下载。"""
    service: TemplateService = request.app.state.template_service
    try:
        template = service.get(template_id)
        yaml_content = service.export_yaml(template_id)
        filename = f"{template.metadata.name}.yaml"
        return Response(
            content=yaml_content,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
