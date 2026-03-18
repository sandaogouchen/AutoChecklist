"""模板 API 路由单元测试。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.api.template_routes import router
from app.domain.template_models import ChecklistTemplate
from app.services.template_service import (
    TemplateConflictError,
    TemplateNotFoundError,
    TemplatePermissionError,
    TemplateService,
)
from app.services.template_validator import ValidationResult


def _make_mock_template() -> ChecklistTemplate:
    return ChecklistTemplate.model_validate({
        "id": "test-id-123",
        "metadata": {"name": "Test", "version": "1.0.0", "description": "Test desc"},
        "categories": [
            {"name": "Cat1", "items": [{"title": "Item1"}]},
        ],
        "source": "custom",
    })


@pytest.fixture
def app() -> FastAPI:
    """创建测试用 FastAPI 应用。"""
    test_app = FastAPI()
    test_app.include_router(router)

    # Mock TemplateService
    mock_service = MagicMock(spec=TemplateService)
    test_app.state.template_service = mock_service

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def mock_service(app: FastAPI) -> MagicMock:
    return app.state.template_service


class TestCreateTemplate:
    def test_create_success(self, client: TestClient, mock_service: MagicMock):
        mock_service.create.return_value = _make_mock_template()
        resp = client.post(
            "/api/v1/templates",
            json={"content": "metadata:\n  name: T\n  version: '1.0.0'\ncategories:\n  - name: C\n    items:\n      - title: I\n", "format": "yaml"},
        )
        assert resp.status_code == 201
        assert resp.json()["template_id"] == "test-id-123"

    def test_create_conflict(self, client: TestClient, mock_service: MagicMock):
        mock_service.create.side_effect = TemplateConflictError("name exists")
        resp = client.post(
            "/api/v1/templates",
            json={"content": "test", "format": "yaml"},
        )
        assert resp.status_code == 409

    def test_create_validation_error(self, client: TestClient, mock_service: MagicMock):
        mock_service.create.side_effect = ValueError("invalid")
        resp = client.post(
            "/api/v1/templates",
            json={"content": "test", "format": "yaml"},
        )
        assert resp.status_code == 422


class TestListTemplates:
    def test_list_success(self, client: TestClient, mock_service: MagicMock):
        mock_service.list_templates.return_value = {
            "templates": [], "total": 0, "page": 1, "page_size": 20
        }
        resp = client.get("/api/v1/templates")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestGetTemplate:
    def test_get_success(self, client: TestClient, mock_service: MagicMock):
        mock_service.get.return_value = _make_mock_template()
        resp = client.get("/api/v1/templates/test-id-123")
        assert resp.status_code == 200

    def test_get_not_found(self, client: TestClient, mock_service: MagicMock):
        mock_service.get.side_effect = TemplateNotFoundError("not found")
        resp = client.get("/api/v1/templates/nonexistent")
        assert resp.status_code == 404


class TestDeleteTemplate:
    def test_delete_success(self, client: TestClient, mock_service: MagicMock):
        mock_service.delete.return_value = None
        resp = client.delete("/api/v1/templates/test-id")
        assert resp.status_code == 204

    def test_delete_forbidden(self, client: TestClient, mock_service: MagicMock):
        mock_service.delete.side_effect = TemplatePermissionError("builtin")
        resp = client.delete("/api/v1/templates/builtin-id")
        assert resp.status_code == 403


class TestValidateTemplate:
    def test_validate_success(self, client: TestClient, mock_service: MagicMock):
        result = ValidationResult()
        result.stats = {"categories_count": 1, "total_items_count": 1, "total_rules_count": 0}
        mock_service.validate.return_value = result
        resp = client.post(
            "/api/v1/templates/validate",
            json={"content": "test", "format": "yaml"},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True


class TestDuplicateTemplate:
    def test_duplicate_success(self, client: TestClient, mock_service: MagicMock):
        mock_service.duplicate.return_value = _make_mock_template()
        resp = client.post("/api/v1/templates/test-id/duplicate")
        assert resp.status_code == 201
