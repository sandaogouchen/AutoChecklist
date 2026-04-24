import io
from pathlib import Path
import time
import zipfile

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.repositories.run_repository import FileRunRepository
from app.services.workflow_service import WorkflowService


def _wait_for_run(client: TestClient, run_id: str, *, timeout_seconds: float = 5.0) -> dict:
    deadline = time.time() + timeout_seconds
    last: dict | None = None
    while time.time() < deadline:
        resp = client.get(f"/api/v1/case-generation/runs/{run_id}")
        assert resp.status_code == 200
        last = resp.json()
        if last.get("status") in ("succeeded", "failed"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"run 未在 {timeout_seconds}s 内完成: run_id={run_id}, last={last}")


def _upload_fixture_file(client: TestClient, fixture_path: Path) -> str:
    response = client.post(
        "/api/v1/files",
        data={"tag": "file"},
        files={"file": (fixture_path.name, fixture_path.read_bytes(), "text/markdown")},
    )
    assert response.status_code == 201
    return response.json()["file_id"]


def _upload_template_file(client: TestClient) -> str:
    template_bytes = b"metadata:\n  name: demo-template\n  version: v1\nnodes: []\n"
    response = client.post(
        "/api/v1/files",
        data={"tag": "template"},
        files={"file": ("demo-template.yaml", template_bytes, "application/yaml")},
    )
    assert response.status_code == 201
    return response.json()["file_id"]


def _upload_fixture_files(client: TestClient, fixture_paths: list[Path]) -> list[str]:
    return [_upload_fixture_file(client, path) for path in fixture_paths]


def test_create_run_returns_generated_cases(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))
    file_ids = _upload_fixture_files(client, [Path("tests/fixtures/sample_prd.md").resolve()])

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_id": file_ids},
    )

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    result = _wait_for_run(client, run_id)
    assert result["status"] == "succeeded"
    assert result["test_cases"]
    assert result["input"]["file_id"] == file_ids[0]

    # runs 请求附带的上传文件不应落盘到 run 输出目录中（文件内容已在 SQLite 保存）
    # runs 请求附带的上传文件不应落盘到 run 输出目录中（文件内容已在 SQLite 保存）
    run_id = response.json()["run_id"]
    assert not (tmp_path / run_id / "input_files").exists()


def test_create_run_writes_xmind_to_sqlite_and_hides_from_file_list(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))
    file_ids = _upload_fixture_files(client, [Path("tests/fixtures/sample_prd.md").resolve()])

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_id": file_ids},
    )

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    payload = _wait_for_run(client, run_id)
    xmind_file_id = payload.get("checklist_xmind_file_id")
    assert isinstance(xmind_file_id, str)
    assert len(xmind_file_id) == 32

    # 生成产物可通过 file_id 获取元信息
    meta_resp = client.get(f"/api/v1/files/{xmind_file_id}")
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    assert meta["file_id"] == xmind_file_id
    assert "generated_artifact" in (meta.get("tags") or [])

    # 普通文件列表不应包含生成产物
    list_resp = client.get("/api/v1/files")
    assert list_resp.status_code == 200
    assert all(item["file_id"] != xmind_file_id for item in list_resp.json())

    # 内容可下载且为 zip（.xmind 本质为 zip）
    content_resp = client.get(f"/api/v1/files/{xmind_file_id}/content")
    assert content_resp.status_code == 200
    assert zipfile.is_zipfile(io.BytesIO(content_resp.content))

    # 历史 XMind 文件列表接口应包含该产物
    xmind_list_resp = client.get("/api/v1/case-generation/runs/xmind-files")
    assert xmind_list_resp.status_code == 200
    assert any(item["file_id"] == xmind_file_id for item in xmind_list_resp.json())

    # 默认文件名应为 run_id.xmind
    run_id = payload["run_id"]
    listed = [item for item in xmind_list_resp.json() if item["file_id"] == xmind_file_id][0]
    assert listed["file_name"] == f"{run_id}.xmind"

    # 改名接口
    rename_resp = client.patch(
        f"/api/v1/case-generation/runs/xmind-files/{xmind_file_id}",
        json={"file_name": "自定义名称"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["file_name"].endswith(".xmind")

    # 改名后列表/元信息可见
    xmind_list_resp2 = client.get("/api/v1/case-generation/runs/xmind-files")
    assert any(
        item["file_id"] == xmind_file_id and item["file_name"] == "自定义名称.xmind"
        for item in xmind_list_resp2.json()
    )


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

    assert create_response.status_code == 202
    run_id = create_response.json()["run_id"]
    _wait_for_run(client, run_id)

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

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    data = _wait_for_run(client, run_id)
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

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    data = _wait_for_run(client, run_id)
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


def test_create_run_returns_422_when_template_file_id_is_not_template(tmp_path, fake_llm_client) -> None:
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
        json={"file_id": file_id, "template_file_id": file_id},
    )

    assert response.status_code == 422
    assert "Template file expected" in response.json()["detail"]


def test_create_run_accepts_template_file_id_when_tagged_as_template(tmp_path, fake_llm_client) -> None:
    settings = Settings(output_dir=str(tmp_path))
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))
    file_id = _upload_fixture_file(client, Path("tests/fixtures/sample_prd.md").resolve())
    template_file_id = _upload_template_file(client)

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_id": file_id, "template_file_id": template_file_id},
    )

    assert response.status_code == 202
