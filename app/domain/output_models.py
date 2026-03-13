from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from app.domain.case_models import QualityReport, TestCase
from app.domain.document_models import ParsedDocument
from app.domain.research_models import ResearchOutput

if TYPE_CHECKING:
    from app.domain.api_models import CaseGenerationRequest


class OutputArtifact(BaseModel):
    key: str
    path: str
    kind: Literal["file", "platform"]
    format: str


class OutputFilePayload(BaseModel):
    key: str
    content: dict[str, Any] | list[Any] | str
    format: Literal["json", "markdown"]


class OutputSummary(BaseModel):
    run_id: str
    status: Literal["succeeded"]
    test_case_count: int = 0
    warning_count: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
    outputs: list[OutputArtifact] = Field(default_factory=list)


class OutputBundle(BaseModel):
    run_id: str
    test_case_count: int = 0
    warning_count: int = 0
    file_payloads: dict[str, OutputFilePayload] = Field(default_factory=dict)

    @classmethod
    def from_state(
        cls,
        *,
        run_id: str,
        request: CaseGenerationRequest,
        parsed_document: ParsedDocument,
        research_output: ResearchOutput,
        test_cases: list[TestCase],
        quality_report: QualityReport,
    ) -> "OutputBundle":
        return cls(
            run_id=run_id,
            test_case_count=len(test_cases),
            warning_count=len(quality_report.warnings),
            file_payloads={
                "request.json": OutputFilePayload(
                    key="request",
                    content=request.model_dump(mode="json", by_alias=True),
                    format="json",
                ),
                "parsed_document.json": OutputFilePayload(
                    key="parsed_document",
                    content=parsed_document.model_dump(mode="json"),
                    format="json",
                ),
                "research_output.json": OutputFilePayload(
                    key="research_output",
                    content=research_output.model_dump(mode="json"),
                    format="json",
                ),
                "test_cases.json": OutputFilePayload(
                    key="test_cases",
                    content=[case.model_dump(mode="json") for case in test_cases],
                    format="json",
                ),
                "test_cases.md": OutputFilePayload(
                    key="test_cases_markdown",
                    content=_render_test_cases_markdown(test_cases),
                    format="markdown",
                ),
                "quality_report.json": OutputFilePayload(
                    key="quality_report",
                    content=quality_report.model_dump(mode="json"),
                    format="json",
                ),
            },
        )


def _render_test_cases_markdown(test_cases: list[TestCase]) -> str:
    if not test_cases:
        return "# Generated Test Cases\n\nNo test cases were generated.\n"

    lines = ["# Generated Test Cases", ""]
    for test_case in test_cases:
        lines.append(f"## {test_case.id} {test_case.title}")
        lines.append("")
        lines.append("### Preconditions")
        lines.extend([f"- {item}" for item in test_case.preconditions] or ["- None"])
        lines.append("")
        lines.append("### Steps")
        lines.extend([f"{index}. {step}" for index, step in enumerate(test_case.steps, start=1)] or ["1. None"])
        lines.append("")
        lines.append("### Expected Results")
        lines.extend([f"- {item}" for item in test_case.expected_results] or ["- None"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"
