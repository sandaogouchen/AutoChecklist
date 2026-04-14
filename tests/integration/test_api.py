from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.repositories.run_repository import FileRunRepository
from app.services.workflow_service import WorkflowService


def _upload_fixture_file(client: TestClient, fixture_path: Path) -> str:
    response = client.post(
        "/api/v1/files",
        files={"file": (fixture_path.name, fixture_path.read_bytes(), "text/markdown")},
    )
    assert response.status_code == 201
    return response.json()["file_id"]


def test_create_run_returns_generated_cases(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))
    file_id = _upload_fixture_file(client, Path("tests/fixtures/sample_prd.md").resolve())

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_id": file_id},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["test_cases"]
    assert response.json()["input"]["file_id"] == file_id


def test_get_run_returns_saved_result(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    repository = FileRunRepository(tmp_path)
    create_service = WorkflowService(
        settings=settings,
        repository=repository,
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=create_service))
    file_id = _upload_fixture_file(client, Path("tests/fixtures/sample_prd.md").resolve())

    create_response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_id": file_id},
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


def test_create_run_includes_checkpoint_count(tmp_path, fake_llm_client) -> None:
    """运行结果应包含 checkpoint_count 字段。"""
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))
    file_id = _upload_fixture_file(client, Path("tests/fixtures/sample_prd.md").resolve())

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_id": file_id},
    )

    data = response.json()
    assert response.status_code == 200
    assert "checkpoint_count" in data
    assert data["checkpoint_count"] > 0


def test_create_run_persists_checkpoint_artifacts(tmp_path, fake_llm_client) -> None:
    """运行后应持久化 checkpoints.json 和 checkpoint_coverage.json。"""
    settings = Settings(output_dir=str(tmp_path))
    repository = FileRunRepository(tmp_path)
    service = WorkflowService(
        settings=settings,
        repository=repository,
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))
    file_id = _upload_fixture_file(client, Path("tests/fixtures/sample_prd.md").resolve())

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_id": file_id},
    )

    data = response.json()
    assert response.status_code == 200
    artifacts = data["artifacts"]
    assert "checkpoints" in artifacts
    assert "checkpoint_coverage" in artifacts


def test_create_run_returns_422_when_file_id_not_found(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_id": "b" * 32},
    )

    assert response.status_code == 422
    assert "File not found" in response.json()["detail"]


def test_create_run_rejects_legacy_local_path_payload(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))

    fixture_path = Path("tests/fixtures/sample_prd.md").resolve()
    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": str(fixture_path)},
    )

    # 该请求应在 schema 校验阶段被拒绝（file_path 仅作为 legacy 字段名映射到 file_id）。
    assert response.status_code == 422


def test_create_run_returns_422_when_template_file_id_not_found(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))
    file_id = _upload_fixture_file(client, Path("tests/fixtures/sample_prd.md").resolve())

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_id": file_id, "template_file_id": "c" * 32},
    )

    assert response.status_code == 422
    assert "File not found" in response.json()["detail"]
