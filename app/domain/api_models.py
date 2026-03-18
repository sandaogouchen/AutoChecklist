"""API 层数据模型。

定义了用例生成的请求/响应 schema，包括：
- 请求模型（``CaseGenerationRequest``）
- 运行结果模型（``CaseGenerationRun``）
- 辅助模型（模型配置覆盖、运行选项、错误信息）

新增迭代评估回路相关的轻量摘要字段。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.case_models import QualityReport, TestCase
from app.domain.document_models import ParsedDocument
from app.domain.research_models import ResearchOutput


class ModelConfigOverride(BaseModel):
    """LLM 调用参数覆盖。"""

    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class RunOptions(BaseModel):
    """运行选项。"""

    include_intermediate_artifacts: bool = False


class ErrorInfo(BaseModel):
    """错误信息载体。"""

    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class IterationSummary(BaseModel):
    """迭代摘要信息。

    作为 CaseGenerationRun 的轻量字段，
    对外展示迭代回路的关键状态，不暴露完整中间过程。
    """

    iteration_count: int = 0
    last_evaluation_score: float = 0.0
    had_retries: bool = False
    final_stage: str = ""
    retry_reasons: list[str] = Field(default_factory=list)


class CaseGenerationRequest(BaseModel):
    """用例生成请求。"""

    model_config = ConfigDict(populate_by_name=True)

    file_path: str
    language: str = "zh-CN"
    llm_config: ModelConfigOverride = Field(
        default_factory=ModelConfigOverride,
        alias="model_config",
        serialization_alias="model_config",
    )
    options: RunOptions = Field(default_factory=RunOptions)
    project_id: str | None = None


class CaseGenerationRun(BaseModel):
    """一次用例生成任务的完整运行结果。

    新增字段：
    - iteration_summary: 迭代摘要，展示轮次、分数、是否发生回流等
    """

    run_id: str
    status: Literal["pending", "running", "evaluating", "retrying", "succeeded", "failed"]
    input: CaseGenerationRequest
    parsed_document: ParsedDocument | None = None
    research_summary: ResearchOutput | None = None
    test_cases: list[TestCase] = Field(default_factory=list)
    quality_report: QualityReport = Field(default_factory=QualityReport)
    checkpoint_count: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: ErrorInfo | None = None
    iteration_summary: IterationSummary = Field(default_factory=IterationSummary)
    project_id: str | None = None
