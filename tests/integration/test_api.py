import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.repositories.run_repository import FileRunRepository
from app.services.workflow_service import WorkflowService
from app.utils.filesystem import read_json


def test_create_run_returns_generated_cases(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": str(Path("tests/fixtures/sample_prd.md").resolve())},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert "parsed_document" not in payload["result"]
    assert "test_cases" not in payload["result"]
    assert payload["result"]["test_case_count"] == 1
    assert "run_result" in payload["result"]["artifacts"]


def test_create_run_accepts_raw_json_body_without_content_type_and_logs_in_chinese(
    tmp_path,
    fake_llm_client,
    caplog,
) -> None:
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))
    request_payload = {
        "file_path": str(Path("tests/fixtures/sample_prd.md").resolve()),
        "language": "zh-CN",
        "options": {"include_intermediate_artifacts": False},
    }

    caplog.set_level(logging.INFO)
    response = client.post(
        "/api/v1/case-generation/runs",
        content=json.dumps(request_payload, ensure_ascii=False),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert "收到创建运行请求" in caplog.text
    assert "检测到原始 JSON 字符串请求体" in caplog.text


def test_get_run_returns_saved_result(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    repository = FileRunRepository(tmp_path)
    create_service = WorkflowService(
        settings=settings,
        repository=repository,
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=create_service))

    create_response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": str(Path("tests/fixtures/sample_prd.md").resolve())},
    )
    run_id = create_response.json()["run_id"]
    read_service = WorkflowService(
        settings=settings,
        repository=repository,
        llm_client=fake_llm_client,
    )
    get_client = TestClient(create_app(settings=settings, workflow_service=read_service))
    get_response = get_client.get(f"/api/v1/case-generation/runs/{run_id}")

    assert get_response.status_code == 200
    assert get_response.json()["run_id"] == run_id
    assert get_response.json()["result"]["test_case_count"] == 1
    assert "parsed_document" not in get_response.json()["result"]
    assert "test_cases" not in get_response.json()["result"]
    assert "run_result" in get_response.json()["result"]["artifacts"]


def test_create_run_returns_compact_error_payload_when_workflow_fails(tmp_path) -> None:
    settings = Settings(
        output_dir=str(tmp_path),
        llm_api_key="",
        llm_base_url="https://example.com/v1",
        llm_model="test-model",
    )
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": str(Path("tests/fixtures/sample_prd.md").resolve())},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "ValidationError"
    assert "result" not in payload
    assert "input" not in payload
    assert "test_cases" not in payload
    assert not any(tmp_path.iterdir())


def test_run_result_json_contains_summary_only(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    repository = FileRunRepository(tmp_path)
    service = WorkflowService(
        settings=settings,
        repository=repository,
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": str(Path("tests/fixtures/sample_prd.md").resolve())},
    )
    run_id = response.json()["run_id"]
    payload = read_json(tmp_path / run_id / "run_result.json")

    assert payload["result"]["test_case_count"] == 1
    assert "test_cases" not in payload["result"]
    assert "parsed_document" not in payload["result"]
    assert payload["result"]["outputs"][-1]["kind"] == "platform"


def test_failed_run_is_only_available_in_memory_until_restart(tmp_path) -> None:
    settings = Settings(
        output_dir=str(tmp_path),
        llm_api_key="",
        llm_base_url="https://example.com/v1",
        llm_model="test-model",
    )
    repository = FileRunRepository(tmp_path)
    create_service = WorkflowService(
        settings=settings,
        repository=repository,
    )
    create_client = TestClient(create_app(settings=settings, workflow_service=create_service))

    create_response = create_client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": str(Path("tests/fixtures/sample_prd.md").resolve())},
    )
    run_id = create_response.json()["run_id"]

    read_service = WorkflowService(
        settings=settings,
        repository=repository,
    )
    read_client = TestClient(create_app(settings=settings, workflow_service=read_service))
    get_response = read_client.get(f"/api/v1/case-generation/runs/{run_id}")

    assert create_response.json()["status"] == "failed"
    assert get_response.status_code == 404
