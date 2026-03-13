from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.case_models import QualityReport, TestCase
from app.domain.document_models import ParsedDocument
from app.domain.output_models import OutputSummary
from app.domain.research_models import ResearchOutput


class ModelConfigOverride(BaseModel):
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class RunOptions(BaseModel):
    include_intermediate_artifacts: bool = False


class ErrorInfo(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class CaseGenerationRequest(BaseModel):
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
    run_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    input: CaseGenerationRequest
    parsed_document: ParsedDocument | None = None
    research_summary: ResearchOutput | None = None
    test_cases: list[TestCase] = Field(default_factory=list)
    quality_report: QualityReport = Field(default_factory=QualityReport)
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: ErrorInfo | None = None


class CaseGenerationRunResult(BaseModel):
    run_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    result: OutputSummary | None = None
    error: ErrorInfo | None = None

    @classmethod
    def from_run(cls, run: CaseGenerationRun) -> "CaseGenerationRunResult":
        if run.error is not None:
            return cls(run_id=run.run_id, status=run.status, error=run.error)
        return cls(
            run_id=run.run_id,
            status=run.status,
            result=OutputSummary(
                run_id=run.run_id,
                status="succeeded",
                test_case_count=len(run.test_cases),
                warning_count=len(run.quality_report.warnings),
                artifacts=run.artifacts,
            ),
        )
