import io
from pathlib import Path
import threading
import time
import zipfile

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.repositories.file_repository import FileRepository
from app.domain.file_models import StoredFileRecord


def _build_xmind_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("content.json", '{"rootTopic":{"title":"demo"}}')
        archive.writestr("metadata.json", '{"creator":"test"}')
    return buffer.getvalue()


def test_file_management_endpoints(tmp_path) -> None:
    client = TestClient(create_app(settings=Settings(output_dir=str(tmp_path))))
    fixture_path = Path("tests/fixtures/sample_prd.md").resolve()

    upload_response = client.post(
        "/api/v1/files",
        data={"tag": "file"},
        files={"file": (fixture_path.name, fixture_path.read_bytes(), "text/markdown")},
    )

    assert upload_response.status_code == 201
    payload = upload_response.json()
    file_id = payload["file_id"]
    assert payload["file_name"] == fixture_path.name
    assert payload["size_bytes"] > 0

    get_response = client.get(f"/api/v1/files/{file_id}")
    assert get_response.status_code == 200
    assert get_response.json()["file_id"] == file_id

    list_response = client.get("/api/v1/files")
    assert list_response.status_code == 200
    assert any(item["file_id"] == file_id for item in list_response.json())

    content_response = client.get(f"/api/v1/files/{file_id}/content")
    assert content_response.status_code == 200
    assert content_response.content == fixture_path.read_bytes()

    # 可以覆盖更新文件内容（file_id 不变）
    new_bytes = b"# updated\n\nhello"
    update_resp = client.put(
        f"/api/v1/files/{file_id}",
        files={"file": ("updated.md", new_bytes, "text/markdown")},
    )
    assert update_resp.status_code == 200
    updated_meta = update_resp.json()
    assert updated_meta["file_id"] == file_id
    assert updated_meta["file_name"] == "updated.md"
    assert updated_meta["size_bytes"] == len(new_bytes)

    updated_content = client.get(f"/api/v1/files/{file_id}/content")
    assert updated_content.status_code == 200
    assert updated_content.content == new_bytes

    # 可以按 file_id 修改文件名
    rename_resp = client.patch(
        f"/api/v1/files/{file_id}",
        json={"file_name": "renamed.md"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["file_name"] == "renamed.md"

    get_after_rename = client.get(f"/api/v1/files/{file_id}")
    assert get_after_rename.status_code == 200
    assert get_after_rename.json()["file_name"] == "renamed.md"

    delete_response = client.delete(f"/api/v1/files/{file_id}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/files/{file_id}").status_code == 404


def test_template_upload_requires_tag_and_uses_template_pagination(tmp_path) -> None:
    client = TestClient(create_app(settings=Settings(output_dir=str(tmp_path))))
    template_bytes = b"metadata:\n  name: demo\n  version: v1\n"

    missing_tag_resp = client.post(
        "/api/v1/files",
        files={"file": ("demo-template.yaml", template_bytes, "application/yaml")},
    )
    assert missing_tag_resp.status_code == 422

    upload_response = client.post(
        "/api/v1/files",
        data={"tag": "template"},
        files={"file": ("demo-template.yaml", template_bytes, "application/yaml")},
    )
    assert upload_response.status_code == 201
    template_file_id = upload_response.json()["file_id"]
    assert "template" in upload_response.json()["tags"]

    visible_list_resp = client.get("/api/v1/files")
    assert visible_list_resp.status_code == 200
    assert all(item["file_id"] != template_file_id for item in visible_list_resp.json())

    templates_resp = client.get("/api/v1/templates?page=1&page_size=10")
    assert templates_resp.status_code == 200
    templates_payload = templates_resp.json()
    assert templates_payload["page"] == 1
    assert templates_payload["page_size"] == 10
    assert templates_payload["total"] >= 1
    assert any(item["file_id"] == template_file_id for item in templates_payload["items"])

    download_resp = client.get(f"/api/v1/files/{template_file_id}/content")
    assert download_resp.status_code == 200
    assert download_resp.content == template_bytes

    updated_template_bytes = b"metadata:\n  name: updated\n  version: v2\n"
    update_resp = client.put(
        f"/api/v1/files/{template_file_id}",
        files={"file": ("updated-template.yaml", updated_template_bytes, "application/yaml")},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["file_name"] == "updated-template.yaml"
    assert "template" in update_resp.json()["tags"]

    download_updated_resp = client.get(f"/api/v1/files/{template_file_id}/content")
    assert download_updated_resp.status_code == 200
    assert download_updated_resp.content == updated_template_bytes


def test_file_update_and_rename_not_found(tmp_path) -> None:
    client = TestClient(create_app(settings=Settings(output_dir=str(tmp_path))))
    missing = "no_such_file"

    update_resp = client.put(
        f"/api/v1/files/{missing}",
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    assert update_resp.status_code == 404

    rename_resp = client.patch(
        f"/api/v1/files/{missing}",
        json={"file_name": "x.txt"},
    )
    assert rename_resp.status_code == 404


def test_run_xmind_files_endpoints(tmp_path) -> None:
    app = create_app(settings=Settings(output_dir=str(tmp_path)))
    client = TestClient(app)
    file_service = app.state.file_service

    stored = file_service.create_file(
        file_name="checklist.xmind",
        content=b"xmind",
        content_type="application/octet-stream",
        tags=["generated_artifact", "type:xmind", "run:run_123"],
    )

    # 生成产物不会出现在普通 files 列表中
    visible = client.get("/api/v1/files").json()
    assert all(item["file_id"] != stored.file_id for item in visible)

    # 但会出现在 runs/xmind-files 列表中，并可能触发历史数据名称归一化
    list_resp = client.get("/api/v1/case-generation/runs/xmind-files")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(item["file_id"] == stored.file_id for item in items)
    normalized = next(item for item in items if item["file_id"] == stored.file_id)
    assert normalized["file_name"].endswith(".xmind")

    # 可以重命名生成产物
    rename_resp = client.patch(
        f"/api/v1/case-generation/runs/xmind-files/{stored.file_id}",
        json={"file_name": "renamed"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["file_name"] == "renamed.xmind"


def test_admin_can_upload_xmind_into_run_xmind_list(tmp_path) -> None:
    app = create_app(
        settings=Settings(
            output_dir=str(tmp_path),
            admin_api_key="super-secret",
        )
    )
    client = TestClient(app)

    upload_resp = client.post(
        "/api/v1/case-generation/runs/xmind-files",
        headers={"X-Admin-Key": "super-secret"},
        files={"file": ("manual-upload.mind", _build_xmind_bytes(), "application/octet-stream")},
    )

    assert upload_resp.status_code == 201
    payload = upload_resp.json()
    assert payload["file_name"] == "manual-upload.xmind"
    assert "generated_artifact" in payload["tags"]
    assert "type:xmind" in payload["tags"]
    assert "admin_uploaded" in payload["tags"]

    list_resp = client.get("/api/v1/case-generation/runs/xmind-files")
    assert list_resp.status_code == 200
    assert any(item["file_id"] == payload["file_id"] for item in list_resp.json())

    visible_resp = client.get("/api/v1/files")
    assert visible_resp.status_code == 200
    assert all(item["file_id"] != payload["file_id"] for item in visible_resp.json())


def test_admin_upload_xmind_requires_valid_admin_key(tmp_path) -> None:
    client = TestClient(
        create_app(
            settings=Settings(
                output_dir=str(tmp_path),
                admin_api_key="super-secret",
            )
        )
    )

    no_auth_resp = client.post(
        "/api/v1/case-generation/runs/xmind-files",
        files={"file": ("manual-upload.xmind", _build_xmind_bytes(), "application/octet-stream")},
    )
    assert no_auth_resp.status_code == 401

    wrong_auth_resp = client.post(
        "/api/v1/case-generation/runs/xmind-files",
        headers={"X-Admin-Key": "wrong-key"},
        files={"file": ("manual-upload.xmind", _build_xmind_bytes(), "application/octet-stream")},
    )
    assert wrong_auth_resp.status_code == 401


def test_admin_upload_xmind_rejects_invalid_file(tmp_path) -> None:
    client = TestClient(
        create_app(
            settings=Settings(
                output_dir=str(tmp_path),
                admin_api_key="super-secret",
            )
        )
    )

    upload_resp = client.post(
        "/api/v1/case-generation/runs/xmind-files",
        headers={"X-Admin-Key": "super-secret"},
        files={"file": ("not-xmind.mind", b"plain-text", "text/plain")},
    )

    assert upload_resp.status_code == 422
    assert "XMind" in upload_resp.json()["detail"]


def test_file_repository_is_threadsafe_for_concurrent_access(tmp_path) -> None:
    repo = FileRepository(db_path=Path(tmp_path) / "files.sqlite3")
    for i in range(30):
        repo.save(
            StoredFileRecord(
                file_name=f"seed_{i}.xmind",
                content_type="application/octet-stream",
                size_bytes=1,
                sha256="0" * 64,
                tags=["generated_artifact", "type:xmind"],
                content=b"x",
            )
        )

    errors: list[str] = []
    stop = False

    def reader() -> None:
        nonlocal stop
        while not stop:
            try:
                repo.list_generated_xmind()
            except Exception as exc:  # pragma: no cover
                errors.append(repr(exc))

    def writer() -> None:
        nonlocal stop
        idx = 0
        while not stop:
            try:
                repo.save(
                    StoredFileRecord(
                        file_name=f"w_{idx}.xmind",
                        content_type="application/octet-stream",
                        size_bytes=1,
                        sha256="0" * 64,
                        tags=["generated_artifact", "type:xmind"],
                        content=b"x",
                    )
                )
                idx += 1
            except Exception as exc:  # pragma: no cover
                errors.append(repr(exc))

    threads = [threading.Thread(target=reader) for _ in range(6)] + [threading.Thread(target=writer) for _ in range(2)]
    for t in threads:
        t.daemon = True
        t.start()

    time.sleep(0.8)
    stop = True
    for t in threads:
        t.join(timeout=0.5)

    assert errors == []
