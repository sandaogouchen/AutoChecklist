from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


def test_file_management_endpoints(tmp_path) -> None:
    client = TestClient(create_app(settings=Settings(output_dir=str(tmp_path))))
    fixture_path = Path("tests/fixtures/sample_prd.md").resolve()

    upload_response = client.post(
        "/api/v1/files",
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

    delete_response = client.delete(f"/api/v1/files/{file_id}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/files/{file_id}").status_code == 404
