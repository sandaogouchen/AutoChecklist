from __future__ import annotations

import pytest

from app.domain.api_models import CaseGenerationRequest
from app.domain.case_models import QualityReport, TestCase
from app.domain.document_models import DocumentSection, DocumentSource, ParsedDocument
from app.domain.output_models import OutputBundle
from app.domain.research_models import EvidenceRef, ResearchOutput
from app.nodes.output_bundle_builder import output_bundle_builder_node
from app.nodes.output_file_writer import build_output_file_writer_node
from app.nodes.output_platform_writer import LocalPlatformPublisher, build_output_platform_writer_node
from app.repositories.run_repository import FileRunRepository


@pytest.fixture
def request_fixture() -> CaseGenerationRequest:
    return CaseGenerationRequest(file_path="/tmp/sample_prd.md", language="zh-CN")


@pytest.fixture
def parsed_document_fixture() -> ParsedDocument:
    return ParsedDocument(
        raw_text="# Login\nUsers log in with SMS code.",
        sections=[
            DocumentSection(
                heading="Login",
                level=1,
                content="Users log in with SMS code.",
                line_start=1,
                line_end=2,
            )
        ],
        references=["REQ-1"],
        metadata={"author": "tester"},
        source=DocumentSource(source_path="/tmp/sample_prd.md", source_type="markdown", title="Sample PRD"),
    )


@pytest.fixture
def research_output_fixture() -> ResearchOutput:
    return ResearchOutput(
        feature_topics=["Login"],
        user_scenarios=["User logs in with SMS code"],
        constraints=["SMS code expires in 5 minutes"],
        ambiguities=["Rate limit is unspecified"],
        test_signals=["success path"],
    )


@pytest.fixture
def test_case_fixture() -> TestCase:
    return TestCase(
        id="TC-001",
        title="User logs in with SMS code",
        preconditions=["User has a registered phone number"],
        steps=["Open login page", "Request SMS code", "Submit valid code"],
        expected_results=["User reaches the dashboard"],
        priority="P1",
        category="functional",
        evidence_refs=[
            EvidenceRef(
                section_title="Acceptance Criteria",
                excerpt="Successful login redirects to the dashboard.",
                line_start=7,
                line_end=10,
                confidence=0.9,
            )
        ],
    )


@pytest.fixture
def quality_report_fixture() -> QualityReport:
    return QualityReport(warnings=["Missing rate-limit requirement"], coverage_notes=["Covered primary login flow"])


@pytest.fixture
def output_bundle_fixture(
    request_fixture: CaseGenerationRequest,
    parsed_document_fixture: ParsedDocument,
    research_output_fixture: ResearchOutput,
    test_case_fixture: TestCase,
    quality_report_fixture: QualityReport,
) -> OutputBundle:
    return OutputBundle.from_state(
        run_id="run-1",
        request=request_fixture,
        parsed_document=parsed_document_fixture,
        research_output=research_output_fixture,
        test_cases=[test_case_fixture],
        quality_report=quality_report_fixture,
    )


def test_output_bundle_builder_collects_successful_run_payloads(
    request_fixture: CaseGenerationRequest,
    parsed_document_fixture: ParsedDocument,
    research_output_fixture: ResearchOutput,
    test_case_fixture: TestCase,
    quality_report_fixture: QualityReport,
) -> None:
    result = output_bundle_builder_node(
        {
            "run_id": "run-1",
            "request": request_fixture,
            "parsed_document": parsed_document_fixture,
            "research_output": research_output_fixture,
            "test_cases": [test_case_fixture],
            "quality_report": quality_report_fixture,
        }
    )

    bundle = result["output_bundle"]
    assert bundle.run_id == "run-1"
    assert "request.json" in bundle.file_payloads
    assert "test_cases.md" in bundle.file_payloads


def test_output_file_writer_persists_bundle_files(tmp_path, output_bundle_fixture: OutputBundle) -> None:
    node = build_output_file_writer_node(FileRunRepository(tmp_path))

    result = node({"run_id": "run-1", "output_bundle": output_bundle_fixture})

    assert (tmp_path / "run-1" / "test_cases.json").exists()
    assert result["artifacts"]["test_cases"] == str(tmp_path / "run-1" / "test_cases.json")


def test_platform_writer_uses_local_adapter_until_real_platform_exists(
    tmp_path, output_bundle_fixture: OutputBundle
) -> None:
    publisher = LocalPlatformPublisher(root_dir=tmp_path)
    node = build_output_platform_writer_node(publisher)

    result = node({"run_id": "run-1", "output_bundle": output_bundle_fixture})

    assert result["outputs"][-1].kind == "platform"
    assert (tmp_path / "run-1-platform.json").exists()
