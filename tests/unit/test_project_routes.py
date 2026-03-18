"""Unit / integration tests for the /projects API routes."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestProjectRoutes:

    def test_create_project(self):
        resp = client.post("/projects", json={"name": "My Project"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Project"
        assert "id" in data

    def test_list_projects(self):
        # Ensure at least one exists.
        client.post("/projects", json={"name": "ListMe"})
        resp = client.get("/projects")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_project(self):
        create = client.post("/projects", json={"name": "GetMe"})
        pid = create.json()["id"]
        resp = client.get(f"/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == pid

    def test_get_project_not_found(self):
        resp = client.get("/projects/does-not-exist")
        assert resp.status_code == 404

    def test_update_project(self):
        create = client.post("/projects", json={"name": "Before"})
        pid = create.json()["id"]
        resp = client.patch(f"/projects/{pid}", json={"name": "After"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    def test_delete_project(self):
        create = client.post("/projects", json={"name": "DeleteMe"})
        pid = create.json()["id"]
        resp = client.delete(f"/projects/{pid}")
        assert resp.status_code == 204

    def test_delete_project_not_found(self):
        resp = client.delete("/projects/does-not-exist")
        assert resp.status_code == 404
