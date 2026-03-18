"""模板校验器单元测试。"""
from __future__ import annotations

import pytest

from app.services.template_validator import TemplateValidator, ValidationResult


@pytest.fixture
def validator() -> TemplateValidator:
    return TemplateValidator()


VALID_YAML = """
metadata:
  name: "Test Template"
  description: "A test template"
  version: "1.0.0"
categories:
  - name: "功能正确性"
    items:
      - title: "正向流程"
        rules:
          - "规则1"
"""

INVALID_YAML_SYNTAX = """
metadata:
  name: "Test
  broken yaml
"""

MISSING_NAME_YAML = """
metadata:
  version: "1.0.0"
categories:
  - name: "Test"
    items:
      - title: "Item1"
"""

EMPTY_CATEGORIES_YAML = """
metadata:
  name: "Test"
  version: "1.0.0"
categories: []
"""


class TestTemplateValidator:
    def test_valid_yaml(self, validator: TemplateValidator):
        result = validator.validate_yaml_string(VALID_YAML)
        assert result.valid is True
        assert not result.errors
        assert result.stats["categories_count"] == 1

    def test_invalid_yaml_syntax(self, validator: TemplateValidator):
        result = validator.validate_yaml_string(INVALID_YAML_SYNTAX)
        assert result.valid is False
        assert len(result.errors) >= 1

    def test_empty_categories(self, validator: TemplateValidator):
        result = validator.validate_yaml_string(EMPTY_CATEGORIES_YAML)
        assert result.valid is False

    def test_warnings_for_single_item(self, validator: TemplateValidator):
        result = validator.validate_yaml_string(VALID_YAML)
        # 单检查项维度应有 warning
        has_single_item_warning = any(
            "仅有 1 个检查项" in w.message for w in result.warnings
        )
        assert has_single_item_warning

    def test_no_rules_warning(self, validator: TemplateValidator):
        yaml_content = """
metadata:
  name: "Test"
  version: "1.0.0"
categories:
  - name: "Cat1"
    items:
      - title: "Item without rules"
      - title: "Another item"
"""
        result = validator.validate_yaml_string(yaml_content)
        assert result.valid is True
        has_no_rules_warning = any(
            "未定义具体规则" in w.message for w in result.warnings
        )
        assert has_no_rules_warning

    def test_validate_dict(self, validator: TemplateValidator):
        data = {
            "metadata": {"name": "Test", "version": "1.0.0"},
            "categories": [
                {"name": "C1", "items": [{"title": "I1", "rules": ["r1"]}]},
            ],
        }
        result = validator.validate_dict(data)
        assert result.valid is True

    def test_info_for_many_categories(self, validator: TemplateValidator):
        categories = [
            {"name": f"Cat{i}", "items": [{"title": f"Item{i}"}]}
            for i in range(11)
        ]
        data = {
            "metadata": {"name": "Big", "version": "1.0.0"},
            "categories": categories,
        }
        result = validator.validate_dict(data)
        assert result.valid is True
        has_many_cats_info = any(
            "维度过多" in i.message for i in result.infos
        )
        assert has_many_cats_info
