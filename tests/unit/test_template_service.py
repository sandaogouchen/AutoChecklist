"""模板服务层单元测试。"""
from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from app.domain.template_models import ChecklistTemplate
from app.repositories.template_repository import TemplateRepository
from app.services.template_service import (
    TemplateConflictError,
    TemplateNotFoundError,
    TemplatePermissionError,
    TemplateService,
)
from app.services.template_validator import TemplateValidator


SAMPLE_YAML = """
metadata:
  name: "Sample Template"
  description: "For testing"
  version: "1.0.0"
categories:
  - name: "功能测试"
    items:
      - title: "正向流程验证"
        rules:
          - "每个功能至少1个正向用例"
      - title: "输入校验"
        rules:
          - "必填字段校验"
"""


@pytest.fixture
def template_service(tmp_path: Path) -> TemplateService:
    """创建使用临时目录的 TemplateService。"""
    builtin_dir = tmp_path / "builtin"
    custom_dir = tmp_path / "custom"
    builtin_dir.mkdir()
    custom_dir.mkdir()
    repo = TemplateRepository(
        builtin_dir=builtin_dir,
        custom_dir=custom_dir,
    )
    validator = TemplateValidator()
    return TemplateService(repository=repo, validator=validator)


class TestTemplateServiceCreate:
    def test_create_success(self, template_service: TemplateService):
        t = template_service.create(SAMPLE_YAML, "yaml")
        assert t.id
        assert t.metadata.name == "Sample Template"
        assert t.source == "custom"

    def test_create_name_conflict(self, template_service: TemplateService):
        template_service.create(SAMPLE_YAML, "yaml")
        with pytest.raises(TemplateConflictError):
            template_service.create(SAMPLE_YAML, "yaml")

    def test_create_invalid_yaml(self, template_service: TemplateService):
        with pytest.raises(ValueError):
            template_service.create("invalid: [yaml: broken", "yaml")


class TestTemplateServiceGet:
    def test_get_success(self, template_service: TemplateService):
        created = template_service.create(SAMPLE_YAML, "yaml")
        fetched = template_service.get(created.id)
        assert fetched.id == created.id

    def test_get_not_found(self, template_service: TemplateService):
        with pytest.raises(TemplateNotFoundError):
            template_service.get("nonexistent-id")

    def test_get_optional(self, template_service: TemplateService):
        result = template_service.get_optional("nonexistent")
        assert result is None


class TestTemplateServiceList:
    def test_list_empty(self, template_service: TemplateService):
        result = template_service.list_templates()
        assert result["total"] == 0

    def test_list_with_pagination(self, template_service: TemplateService):
        for i in range(5):
            yaml_content = SAMPLE_YAML.replace("Sample Template", f"Template {i}")
            template_service.create(yaml_content, "yaml")

        result = template_service.list_templates(page=1, page_size=2)
        assert len(result["templates"]) == 2
        assert result["total"] == 5
        assert result["page"] == 1


class TestTemplateServiceUpdate:
    def test_update_success(self, template_service: TemplateService):
        created = template_service.create(SAMPLE_YAML, "yaml")
        updated_yaml = SAMPLE_YAML.replace("Sample Template", "Updated Name")
        updated = template_service.update(created.id, updated_yaml, "yaml")
        assert updated.metadata.name == "Updated Name"

    def test_update_not_found(self, template_service: TemplateService):
        with pytest.raises(TemplateNotFoundError):
            template_service.update("nonexistent", SAMPLE_YAML, "yaml")


class TestTemplateServiceDelete:
    def test_delete_success(self, template_service: TemplateService):
        created = template_service.create(SAMPLE_YAML, "yaml")
        template_service.delete(created.id)
        assert template_service.get_optional(created.id) is None

    def test_delete_not_found(self, template_service: TemplateService):
        with pytest.raises(TemplateNotFoundError):
            template_service.delete("nonexistent")


class TestTemplateServiceDuplicate:
    def test_duplicate_success(self, template_service: TemplateService):
        created = template_service.create(SAMPLE_YAML, "yaml")
        copy = template_service.duplicate(created.id)
        assert copy.id != created.id
        assert "(copy)" in copy.metadata.name


class TestTemplateServiceValidate:
    def test_validate_valid(self, template_service: TemplateService):
        result = template_service.validate(SAMPLE_YAML, "yaml")
        assert result.valid is True

    def test_validate_invalid(self, template_service: TemplateService):
        result = template_service.validate("categories: []", "yaml")
        assert result.valid is False


class TestTemplateServiceExportImport:
    def test_export_yaml(self, template_service: TemplateService):
        created = template_service.create(SAMPLE_YAML, "yaml")
        exported = template_service.export_yaml(created.id)
        assert "Sample Template" in exported

    def test_import_yaml(self, template_service: TemplateService):
        imported = template_service.import_yaml(SAMPLE_YAML)
        assert imported.metadata.name == "Sample Template"
        assert imported.source == "custom"

    def test_import_name_conflict(self, template_service: TemplateService):
        template_service.create(SAMPLE_YAML, "yaml")
        imported = template_service.import_yaml(SAMPLE_YAML)
        assert "(imported)" in imported.metadata.name
