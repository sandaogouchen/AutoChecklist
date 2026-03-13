from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.repositories.run_repository import FileRunRepository
from app.services.workflow_service import WorkflowService


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
    assert response.json()["status"] == "succeeded"
    assert response.json()["test_cases"]


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
    assert "run_result" in get_response.json()["artifacts"]
