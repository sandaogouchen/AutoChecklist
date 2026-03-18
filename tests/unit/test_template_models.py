"""模板领域模型单元测试。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.template_models import (
    ChecklistTemplate,
    TemplateCategory,
    TemplateCategoryItem,
    TemplateExclusion,
    TemplateMetadata,
    TemplateSettings,
    VALID_PRIORITIES,
)


# ── TemplateMetadata ────────────────────────────────────────


class TestTemplateMetadata:
    """TemplateMetadata 模型测试。"""

    def test_valid_metadata(self):
        meta = TemplateMetadata(name="Test Template", version="1.0.0")
        assert meta.name == "Test Template"
        assert meta.version == "1.0.0"
        assert meta.tags == []

    def test_name_required(self):
        with pytest.raises(ValidationError):
            TemplateMetadata(name="", version="1.0.0")

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            TemplateMetadata(name="a" * 101, version="1.0.0")

    def test_valid_version_formats(self):
        for v in ("1.0", "1.0.0", "2.1.3", "0.0.1"):
            meta = TemplateMetadata(name="T", version=v)
            assert meta.version == v

    def test_invalid_version_format(self):
        with pytest.raises(ValidationError):
            TemplateMetadata(name="T", version="abc")

    def test_default_timestamps(self):
        meta = TemplateMetadata(name="T", version="1.0.0")
        assert meta.created_at is not None
        assert meta.updated_at is not None


# ── TemplateSettings ────────────────────────────────────────


class TestTemplateSettings:
    def test_defaults(self):
        s = TemplateSettings()
        assert s.default_priority == "medium"
        assert s.min_cases_per_category == 2
        assert s.require_negative_cases is True
        assert s.require_boundary_cases is True

    def test_invalid_priority(self):
        with pytest.raises(ValidationError):
            TemplateSettings(default_priority="invalid")

    def test_min_cases_range(self):
        s = TemplateSettings(min_cases_per_category=1)
        assert s.min_cases_per_category == 1

        with pytest.raises(ValidationError):
            TemplateSettings(min_cases_per_category=0)

        with pytest.raises(ValidationError):
            TemplateSettings(min_cases_per_category=21)


# ── TemplateCategoryItem ────────────────────────────────────


class TestTemplateCategoryItem:
    def test_valid_item(self):
        item = TemplateCategoryItem(title="Test", description="Desc")
        assert item.title == "Test"
        assert item.rules == []

    def test_valid_priority(self):
        for p in VALID_PRIORITIES:
            item = TemplateCategoryItem(title="T", priority=p)
            assert item.priority == p

    def test_invalid_priority(self):
        with pytest.raises(ValidationError):
            TemplateCategoryItem(title="T", priority="invalid")

    def test_none_priority_allowed(self):
        item = TemplateCategoryItem(title="T", priority=None)
        assert item.priority is None


# ── TemplateCategory ────────────────────────────────────────


class TestTemplateCategory:
    def test_valid_category(self):
        cat = TemplateCategory(
            name="功能正确性",
            items=[TemplateCategoryItem(title="正向流程")],
        )
        assert cat.name == "功能正确性"
        assert len(cat.items) == 1

    def test_items_required(self):
        with pytest.raises(ValidationError):
            TemplateCategory(name="Test", items=[])


# ── ChecklistTemplate ──────────────────────────────────────


class TestChecklistTemplate:
    def _make_minimal_template(self, **overrides) -> ChecklistTemplate:
        """创建最小有效模板。"""
        data = {
            "metadata": {"name": "Test", "version": "1.0.0"},
            "categories": [
                {
                    "name": "Cat1",
                    "items": [{"title": "Item1"}],
                },
            ],
        }
        data.update(overrides)
        return ChecklistTemplate.model_validate(data)

    def test_minimal_template(self):
        t = self._make_minimal_template()
        assert t.id  # UUID auto-generated
        assert t.metadata.name == "Test"
        assert t.source == "custom"

    def test_total_items_count(self):
        t = self._make_minimal_template(
            categories=[
                {"name": "C1", "items": [{"title": "I1"}, {"title": "I2"}]},
                {"name": "C2", "items": [{"title": "I3"}]},
            ]
        )
        assert t.total_items_count() == 3

    def test_total_rules_count(self):
        t = self._make_minimal_template(
            categories=[
                {
                    "name": "C1",
                    "items": [
                        {"title": "I1", "rules": ["r1", "r2"]},
                        {"title": "I2", "rules": ["r3"]},
                    ],
                },
            ]
        )
        assert t.total_rules_count() == 3

    def test_categories_required(self):
        with pytest.raises(ValidationError):
            ChecklistTemplate(
                metadata=TemplateMetadata(name="T", version="1.0.0"),
                categories=[],
            )

    def test_format_for_checkpoint_prompt(self):
        t = self._make_minimal_template(
            categories=[
                {
                    "name": "功能正确性",
                    "priority": "critical",
                    "items": [
                        {
                            "title": "正向流程",
                            "description": "验证正向流程",
                            "priority": "critical",
                            "rules": ["规则1", "规则2"],
                        }
                    ],
                },
            ]
        )
        prompt = t.format_for_checkpoint_prompt()
        assert "测试集模板约束" in prompt
        assert "功能正确性" in prompt
        assert "正向流程" in prompt
        assert "规则1" in prompt

    def test_format_for_draft_prompt(self):
        t = self._make_minimal_template(
            categories=[
                {
                    "name": "安全性",
                    "items": [
                        {
                            "title": "认证授权",
                            "rules": ["规则A", "规则B"],
                        }
                    ],
                },
            ]
        )
        prompt = t.format_for_draft_prompt(
            template_category="安全性",
            template_item_title="认证授权",
        )
        assert "模板规则约束" in prompt
        assert "安全性" in prompt
        assert "认证授权" in prompt
        assert "规则A" in prompt

    def test_format_for_draft_prompt_no_match(self):
        t = self._make_minimal_template()
        prompt = t.format_for_draft_prompt(
            template_category="不存在的维度",
        )
        assert "全局模板设置" in prompt
