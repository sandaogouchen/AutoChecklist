from __future__ import annotations

from typing import TypedDict

from app.domain.api_models import CaseGenerationRequest, ErrorInfo, ModelConfigOverride
from app.domain.case_models import QualityReport, TestCase
from app.domain.document_models import ParsedDocument
from app.domain.research_models import EvidenceRef, PlannedScenario, ResearchOutput


class GlobalState(TypedDict, total=False):
    run_id: str
    file_path: str
    language: str
    request: CaseGenerationRequest
    model_config: ModelConfigOverride
    parsed_document: ParsedDocument
    research_output: ResearchOutput
    planned_scenarios: list[PlannedScenario]
    mapped_evidence: dict[str, list[EvidenceRef]]
    draft_cases: list[TestCase]
    test_cases: list[TestCase]
    quality_report: QualityReport
    artifacts: dict[str, str]
    error: ErrorInfo


class CaseGenState(TypedDict, total=False):
    language: str
    parsed_document: ParsedDocument
    research_output: ResearchOutput
    planned_scenarios: list[PlannedScenario]
    mapped_evidence: dict[str, list[EvidenceRef]]
    draft_cases: list[TestCase]
    test_cases: list[TestCase]
