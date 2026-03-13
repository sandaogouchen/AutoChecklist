from app.domain.api_models import CaseGenerationRequest


def test_case_generation_request_defaults_language() -> None:
    request = CaseGenerationRequest(file_path="prd.md")

    assert request.language == "zh-CN"
