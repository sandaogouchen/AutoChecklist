"""Unit / integration tests for the /projects API routes."""

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


class TestProjectRoutes:

    def _make_client(self, tmp_path) -> TestClient:
        settings = Settings(output_dir=str(tmp_path))
        return TestClient(create_app(settings=settings))

    def test_create_project(self, tmp_path):
        client = self._make_client(tmp_path)
        resp = client.post("/projects", json={"name": "My Project"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Project"
        assert "id" in data

    def test_list_projects(self, tmp_path):
        client = self._make_client(tmp_path)
        client.post("/projects", json={"name": "ListMe"})
        resp = client.get("/projects")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_project(self, tmp_path):
        client = self._make_client(tmp_path)
        create = client.post("/projects", json={"name": "GetMe"})
        pid = create.json()["id"]
        resp = client.get(f"/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == pid

    def test_get_project_not_found(self, tmp_path):
        client = self._make_client(tmp_path)
        resp = client.get("/projects/does-not-exist")
        assert resp.status_code == 404

    def test_update_project(self, tmp_path):
        client = self._make_client(tmp_path)
        create = client.post("/projects", json={"name": "Before"})
        pid = create.json()["id"]
        resp = client.patch(f"/projects/{pid}", json={"name": "After"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    def test_delete_project(self, tmp_path):
        client = self._make_client(tmp_path)
        create = client.post("/projects", json={"name": "DeleteMe"})
        pid = create.json()["id"]
        resp = client.delete(f"/projects/{pid}")
        assert resp.status_code == 204

    def test_delete_project_not_found(self, tmp_path):
        client = self._make_client(tmp_path)
        resp = client.delete("/projects/does-not-exist")
        assert resp.status_code == 404

    def test_projects_persist_across_app_instances(self, tmp_path):
        first_client = self._make_client(tmp_path)
        create = first_client.post("/projects", json={"name": "Persistent Project"})
        project_id = create.json()["id"]

        second_client = self._make_client(tmp_path)
        resp = second_client.get(f"/projects/{project_id}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "Persistent Project"
