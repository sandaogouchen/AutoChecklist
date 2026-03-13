from pathlib import Path

from app.domain.api_models import CaseGenerationRequest
from app.graphs.main_workflow import build_workflow
from app.nodes.output_platform_writer import LocalPlatformPublisher
from app.repositories.run_repository import FileRunRepository


def test_workflow_returns_test_cases(tmp_path, fake_llm_client) -> None:
    workflow = build_workflow(
        fake_llm_client,
        repository=FileRunRepository(tmp_path),
        platform_publisher=LocalPlatformPublisher(tmp_path),
    )

    result = workflow.invoke(
        {
            "run_id": "run-0",
            "file_path": str(Path("tests/fixtures/sample_prd.md")),
            "language": "zh-CN",
            "request": CaseGenerationRequest(file_path=str(Path("tests/fixtures/sample_prd.md").resolve())),
        }
    )

    assert result["test_cases"]
    assert result["test_cases"][0].title == "User logs in with SMS code"


def test_workflow_writes_outputs_via_output_delivery_subgraph(tmp_path, fake_llm_client) -> None:
    workflow = build_workflow(
        fake_llm_client,
        repository=FileRunRepository(tmp_path),
        platform_publisher=LocalPlatformPublisher(tmp_path),
    )

    result = workflow.invoke(
        {
            "run_id": "run-1",
            "file_path": str(Path("tests/fixtures/sample_prd.md").resolve()),
            "language": "zh-CN",
            "request": CaseGenerationRequest(file_path=str(Path("tests/fixtures/sample_prd.md").resolve())),
        }
    )

    assert result["output_summary"].test_case_count == 1
    assert (tmp_path / "run-1" / "run_result.json").exists()
