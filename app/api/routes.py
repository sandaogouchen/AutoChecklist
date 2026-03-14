from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError

from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRunResult
from app.services.workflow_service import WorkflowService

router = APIRouter()
logger = logging.getLogger(__name__)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_workflow_service(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


def _coerce_form_value(value: str) -> Any:
    normalized_value = value.strip()
    if not normalized_value:
        return ""

    lower_value = normalized_value.lower()
    if lower_value == "true":
        return True
    if lower_value == "false":
        return False

    if normalized_value[0] in {'{', '[', '"'}:
        try:
            return json.loads(normalized_value)
        except json.JSONDecodeError:
            return normalized_value

    return normalized_value


def _assign_nested_value(container: dict[str, Any], key: str, value: Any) -> None:
    normalized_key = key.replace("]", "").replace("[", ".")
    key_parts = [part for part in normalized_key.split(".") if part]
    if not key_parts:
        return

    current = container
    for part in key_parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[key_parts[-1]] = value


def _parse_form_encoded_payload(raw_payload: str) -> dict[str, Any]:
    parsed_payload: dict[str, Any] = {}
    for key, value in parse_qsl(raw_payload, keep_blank_values=True):
        _assign_nested_value(parsed_payload, key, _coerce_form_value(value))
    return parsed_payload


def _normalize_request_payload(raw_payload: str) -> dict[str, Any]:
    normalized_payload = raw_payload.strip()
    if not normalized_payload:
        raise HTTPException(status_code=422, detail="请求体不能为空，请传入 JSON 对象。")

    if normalized_payload.startswith("{"):
        logger.info("检测到原始 JSON 字符串请求体，开始手动解析。")
        try:
            parsed_payload = json.loads(normalized_payload)
        except json.JSONDecodeError as exc:
            logger.warning("原始 JSON 字符串解析失败：%s", exc)
            raise HTTPException(status_code=422, detail="请求体不是合法 JSON，请检查格式。") from exc

        if not isinstance(parsed_payload, dict):
            logger.warning("JSON 解析成功，但顶层类型不是对象：%s", type(parsed_payload).__name__)
            raise HTTPException(status_code=422, detail="请求体顶层必须是 JSON 对象。")

        logger.info("原始 JSON 字符串解析成功，字段=%s", sorted(parsed_payload.keys()))
        return parsed_payload

    if "=" in normalized_payload:
        logger.info("检测到表单风格请求体，开始按键值对解析。")
        parsed_payload = _parse_form_encoded_payload(normalized_payload)
        logger.info("表单风格请求体解析完成，字段=%s", sorted(parsed_payload.keys()))
        return parsed_payload

    logger.warning("无法识别请求体格式，原始内容前 120 个字符：%s", normalized_payload[:120])
    raise HTTPException(status_code=422, detail="无法识别请求体格式，请使用 JSON 对象提交。")


def _parse_case_generation_request(raw_payload: CaseGenerationRequest | str) -> CaseGenerationRequest:
    if isinstance(raw_payload, CaseGenerationRequest):
        logger.info(
            "请求体已按标准 JSON 模型解析：file_path=%s, language=%s, include_intermediate_artifacts=%s",
            raw_payload.file_path,
            raw_payload.language,
            raw_payload.options.include_intermediate_artifacts,
        )
        return raw_payload

    normalized_payload = _normalize_request_payload(raw_payload)
    try:
        request_payload = CaseGenerationRequest.model_validate(normalized_payload)
    except ValidationError as exc:
        logger.warning("请求参数校验失败：errors=%s", exc.errors())
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    logger.info(
        "请求参数校验通过：file_path=%s, language=%s, include_intermediate_artifacts=%s",
        request_payload.file_path,
        request_payload.language,
        request_payload.options.include_intermediate_artifacts,
    )
    return request_payload


@router.get("/healthz")
def healthz(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.post(
    "/api/v1/case-generation/runs",
    response_model=CaseGenerationRunResult,
    response_model_exclude_none=True,
)
async def create_case_generation_run(
    request: Request,
    raw_payload: CaseGenerationRequest | str = Body(...),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> CaseGenerationRunResult:
    logger.info(
        "收到创建运行请求：path=%s, content_type=%s, client=%s",
        request.url.path,
        request.headers.get("content-type", "<missing>"),
        request.client.host if request.client else "<unknown>",
    )
    payload = _parse_case_generation_request(raw_payload)
    return workflow_service.create_run(payload)


@router.get(
    "/api/v1/case-generation/runs/{run_id}",
    response_model=CaseGenerationRunResult,
    response_model_exclude_none=True,
)
def get_case_generation_run(
    run_id: str,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> CaseGenerationRunResult:
    try:
        return workflow_service.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}") from exc
