"""API 层数据模型。

定义了用例生成的请求/响应 schema，包括：
- 请求模型（``CaseGenerationRequest``）
- 运行结果模型（``CaseGenerationRun``）
- 辅助模型（模型配置覆盖、运行选项、错误信息）

新增迭代评估回路相关的轻量摘要字段。
新增项目级 Checklist 模版文件路径字段。
新增 template_name 字段，支持按名称加载模版。
新增 reference_xmind_path 字段，支持 XMind 参考文件路径。
新增 frontend_mr / backend_mr 字段，支持 MR 代码分析。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.case_models import QualityReport, TestCase
from app.domain.document_models import ParsedDocument
from app.domain.research_models import ResearchOutput


FILE_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")


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
    """迭代摘要信息。"""

    iteration_count: int = 0
    last_evaluation_score: float = 0.0
    had_retries: bool = False
    final_stage: str = ""
    retry_reasons: list[str] = Field(default_factory=list)


class MRRequestConfig(BaseModel):
    """MR 请求配置（API 层）。

    用于在 CaseGenerationRequest 中传入前端/后端 MR 信息。
    """

    mr_url: str = ""
    git_url: str = ""
    local_path: str = ""
    branch: str = ""
    commit_sha: str = ""
    use_coco: bool = True


class CaseGenerationRequest(BaseModel):
    """用例生成请求。

    新增字段：
    - file_id: 主输入文件 ID。
    - template_file_id: 可选的项目级 Checklist 模版文件 ID（YAML 格式）。
    - template_name: 可选的模版名称，对应 templates/ 目录下的 YAML 文件（不含扩展名）。
      与 template_file_id 二选一使用，template_name 优先。
    - reference_xmind_file_id: 可选的参考 XMind checklist 文件 ID，
      系统将解析其结构并用于引导 checklist 生成。
    - frontend_mr: 可选的前端 MR 配置。
    - backend_mr: 可选的后端 MR 配置。
    """

    model_config = ConfigDict(populate_by_name=True)

    # 主输入 PRD：
    # - 旧入参：file_id / file_path 传单个 file_id
    # - 新入参：file_ids 传多个 file_id
    file_id: str = Field(
        ...,
        validation_alias=AliasChoices("file_id", "file_path"),
    )
    file_ids: list[str] | None = None
    language: str = "zh-CN"
    llm_config: ModelConfigOverride = Field(
        default_factory=ModelConfigOverride,
        alias="model_config",
        serialization_alias="model_config",
    )
    options: RunOptions = Field(default_factory=RunOptions)
    project_id: str | None = None
    template_file_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("template_file_id", "template_file_path"),
    )
    template_name: str | None = None
    reference_xmind_file_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reference_xmind_file_id", "reference_xmind_path"),
    )

    # ---- MR 分析字段（支持多个，兼容旧单值） ----
    frontend_mr: list[MRRequestConfig] | None = Field(
        default=None,
        validation_alias=AliasChoices("frontend_mr", "frontend_mrs"),
    )
    backend_mr: list[MRRequestConfig] | None = Field(
        default=None,
        validation_alias=AliasChoices("backend_mr", "backend_mrs"),
    )

    @field_validator("frontend_mr", "backend_mr", mode="before")
    @classmethod
    def _coerce_mr_list(cls, value):
        if value is None or value == "":
            return None
        # 兼容旧版：传入单个对象
        if isinstance(value, dict):
            return [value]
        if isinstance(value, MRRequestConfig):
            return [value]
        return value

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_file_id_list(cls, data):
        if not isinstance(data, dict):
            return data

        # 新版：仅传 file_ids
        if not data.get("file_id") and isinstance(data.get("file_ids"), list) and data.get("file_ids"):
            data["file_id"] = data["file_ids"][0]

        # 兼容：部分调用方可能传 file_id 为列表
        if isinstance(data.get("file_id"), list) and data.get("file_ids") is None:
            items = data.get("file_id") or []
            data["file_ids"] = items
            data["file_id"] = items[0] if items else ""
        return data

    @field_validator("file_id")
    @classmethod
    def _validate_file_id(cls, value: str):
        if not FILE_ID_RE.fullmatch(value):
            raise ValueError("无效的 file_id: 必须是 32 位十六进制 file_id")
        return value.lower()

    @field_validator("file_ids")
    @classmethod
    def _validate_file_ids(cls, value: list[str] | None):
        if value is None:
            return None
        if not value:
            raise ValueError("无效的 file_ids: 至少需要 1 个 32 位十六进制 file_id")
        normalized: list[str] = []
        for item in value:
            if not FILE_ID_RE.fullmatch(item):
                raise ValueError("无效的 file_ids: 必须是 32 位十六进制 file_id")
            normalized.append(item.lower())
        return normalized

    @field_validator("template_file_id", "reference_xmind_file_id")
    @classmethod
    def _validate_optional_file_ids(cls, value: str | None, info):
        if value is None:
            return None
        if not FILE_ID_RE.fullmatch(value):
            raise ValueError(f"无效的 {info.field_name}: 必须是 32 位十六进制 file_id")
        return value.lower()


class CaseGenerationRun(BaseModel):
    """一次用例生成任务的完整运行结果。"""

    run_id: str
    status: Literal["pending", "running", "evaluating", "retrying", "succeeded", "failed"]
    input: CaseGenerationRequest
    parsed_document: ParsedDocument | None = None
    research_summary: ResearchOutput | None = None
    test_cases: list[TestCase] = Field(default_factory=list)
    quality_report: QualityReport = Field(default_factory=QualityReport)
    checkpoint_count: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
    # 最终生成的 checklist XMind 文件（写入 SQLite 文件存储后的 file_id）。
    # 该文件会带有“生成产物”标签，默认不会出现在 /api/v1/files 列表中。
    checklist_xmind_file_id: str | None = None
    error: ErrorInfo | None = None
    iteration_summary: IterationSummary = Field(default_factory=IterationSummary)
    project_id: str | None = None
