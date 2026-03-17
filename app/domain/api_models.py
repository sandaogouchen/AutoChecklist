"""API 层数据模型。

定义了用例生成的请求/响应 schema，包括：
- 请求模型（``CaseGenerationRequest``）
- 运行结果模型（``CaseGenerationRun``）
- 辅助模型（模型配置覆盖、运行选项、错误信息）
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.case_models import QualityReport, TestCase
from app.domain.document_models import ParsedDocument
from app.domain.research_models import ResearchOutput


class ModelConfigOverride(BaseModel):
    """LLM 调用参数覆盖。

    允许在单次请求中临时覆盖全局 LLM 配置（模型名、温度、最大 token 数）。
    值为 None 时沿用全局默认值。
    """

    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class RunOptions(BaseModel):
    """运行选项。"""

    include_intermediate_artifacts: bool = False


class ErrorInfo(BaseModel):
    """错误信息载体，用于在运行失败时向调用方返回结构化的错误描述。"""

    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class CaseGenerationRequest(BaseModel):
    """用例生成请求。

    ``file_path`` 指向待分析的 PRD 文档（Markdown 格式），
    ``language`` 控制生成用例的语言。
    ``llm_config`` 支持在请求级别覆盖 LLM 参数。
    """

    model_config = ConfigDict(populate_by_name=True)

    file_path: str
    language: str = "zh-CN"
    llm_config: ModelConfigOverride = Field(
        default_factory=ModelConfigOverride,
        alias="model_config",
        serialization_alias="model_config",
    )
    options: RunOptions = Field(default_factory=RunOptions)


class CaseGenerationRun(BaseModel):
    """一次用例生成任务的完整运行结果。

    包含输入参数、中间产物（解析文档、研究摘要）、最终用例列表、
    质量报告以及持久化产物路径映射。

    ``checkpoint_count`` 是新增的轻量字段，表示本次运行生成的 checkpoint 数量，
    避免将 checkpoints 全量内嵌到响应体中。
    """

    run_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    input: CaseGenerationRequest
    parsed_document: ParsedDocument | None = None
    research_summary: ResearchOutput | None = None
    test_cases: list[TestCase] = Field(default_factory=list)
    quality_report: QualityReport = Field(default_factory=QualityReport)
    checkpoint_count: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: ErrorInfo | None = None
