from pathlib import Path

from app.graphs.main_workflow import build_workflow

def test_workflow_returns_test_cases(fake_llm_client) -> None:
    workflow = build_workflow(fake_llm_client)

    result = workflow.invoke(
        {
            "file_path": str(Path("tests/fixtures/sample_prd.md")),
            "language": "zh-CN",
        }
    )

    assert result["test_cases"]
    assert result["test_cases"][0].title == "User logs in with SMS code"
