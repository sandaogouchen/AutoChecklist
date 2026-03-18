"""API 请求与响应模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LLMConfigOverride(BaseModel):
    """LLM 配置覆盖。"""
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class GenerationOptions(BaseModel):
    """生成选项。"""
    max_iterations: int = Field(default=3, ge=1, le=10)
    pass_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    enable_xmind: bool = False


class CaseGenerationRequest(BaseModel):
    """用例生成请求。"""
    file_path: str
    language: str = "en"
    llm_config: Optional[LLMConfigOverride] = None
    options: Optional[GenerationOptions] = None
    project_id: Optional[str] = None
    # ---- 模板驱动生成支持：指定模板 ID 以启用模板引导的用例生成 ----
    template_id: Optional[str] = None


class CaseGenerationResponse(BaseModel):
    """用例生成响应。"""
    run_id: str
    status: str
    message: str = ""
