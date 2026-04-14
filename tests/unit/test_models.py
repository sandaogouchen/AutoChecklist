from app.domain.api_models import CaseGenerationRequest


def test_case_generation_request_defaults_language() -> None:
    request = CaseGenerationRequest(file_id="0" * 32)

    assert request.language == "zh-CN"


def test_case_generation_request_accepts_legacy_path_alias() -> None:
    request = CaseGenerationRequest(file_path="a" * 32)

    assert request.file_id == "a" * 32


def test_case_generation_request_rejects_local_file_path_like_input() -> None:
    try:
        CaseGenerationRequest(file_path="/etc/passwd")
    except ValueError as exc:
        assert "无效的 file_id" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid file_id")
