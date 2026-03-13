from app.domain.api_models import CaseGenerationRequest, CaseGenerationRunResult


def test_case_generation_request_defaults_language() -> None:
    request = CaseGenerationRequest(file_path="prd.md")

    assert request.language == "zh-CN"


def test_case_generation_run_result_uses_lightweight_summary() -> None:
    result = CaseGenerationRunResult.model_validate(
        {
            "run_id": "run-1",
            "status": "succeeded",
            "result": {
                "run_id": "run-1",
                "status": "succeeded",
                "test_case_count": 2,
                "warning_count": 1,
                "artifacts": {
                    "run_result": "/tmp/run-1/run_result.json",
                    "test_cases_markdown": "/tmp/run-1/test_cases.md",
                },
                "outputs": [
                    {
                        "key": "test_cases_markdown",
                        "path": "/tmp/run-1/test_cases.md",
                        "kind": "file",
                        "format": "markdown",
                    }
                ],
            },
        }
    )

    assert result.result is not None
    assert result.result.test_case_count == 2
    assert result.result.outputs[0].format == "markdown"
