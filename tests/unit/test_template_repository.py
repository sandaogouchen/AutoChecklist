"""模板仓储层单元测试。"""
from __future__ import annotations

import pytest
from pathlib import Path

import yaml

from app.domain.template_models import ChecklistTemplate, TemplateMetadata, TemplateSettings, TemplateCategory, TemplateCategoryItem
from app.repositories.template_repository import TemplateRepository


def _make_template(**overrides) -> ChecklistTemplate:
    """创建测试用模板。"""
    data = {
        "metadata": {"name": "Test Template", "version": "1.0.0"},
        "categories": [
            {"name": "Cat1", "items": [{"title": "Item1", "rules": ["r1"]}]},
        ],
        "source": "custom",
    }
    data.update(overrides)
    return ChecklistTemplate.model_validate(data)


@pytest.fixture
def repo(tmp_path: Path) -> TemplateRepository:
    builtin = tmp_path / "builtin"
    custom = tmp_path / "custom"
    builtin.mkdir()
    custom.mkdir()
    return TemplateRepository(builtin_dir=builtin, custom_dir=custom)


class TestTemplateRepository:
    def test_save_and_get(self, repo: TemplateRepository):
        t = _make_template()
        saved = repo.save(t)
        fetched = repo.get(saved.id)
        assert fetched is not None
        assert fetched.metadata.name == "Test Template"

    def test_get_nonexistent(self, repo: TemplateRepository):
        assert repo.get("nonexistent") is None

    def test_list_all(self, repo: TemplateRepository):
        t1 = _make_template(metadata={"name": "T1", "version": "1.0.0"})
        t2 = _make_template(metadata={"name": "T2", "version": "1.0.0"})
        repo.save(t1)
        repo.save(t2)
        all_templates = repo.list_all()
        assert len(all_templates) == 2

    def test_list_filter_by_source(self, repo: TemplateRepository):
        t = _make_template()
        repo.save(t)
        custom = repo.list_all(source="custom")
        builtin = repo.list_all(source="builtin")
        assert len(custom) == 1
        assert len(builtin) == 0

    def test_delete(self, repo: TemplateRepository):
        t = _make_template()
        repo.save(t)
        assert repo.delete(t.id) is True
        assert repo.get(t.id) is None

    def test_delete_nonexistent(self, repo: TemplateRepository):
        assert repo.delete("nonexistent") is False

    def test_delete_builtin_raises(self, repo: TemplateRepository, tmp_path: Path):
        # 写一个 builtin 模板文件
        builtin_data = {
            "id": "builtin-1",
            "metadata": {"name": "Builtin", "version": "1.0.0"},
            "categories": [{"name": "C", "items": [{"title": "I"}]}],
            "source": "builtin",
        }
        builtin_file = tmp_path / "builtin" / "builtin-1.yaml"
        builtin_file.write_text(
            yaml.safe_dump(builtin_data, allow_unicode=True),
            encoding="utf-8",
        )
        repo.reload()
        with pytest.raises(PermissionError):
            repo.delete("builtin-1")

    def test_name_exists(self, repo: TemplateRepository):
        t = _make_template()
        repo.save(t)
        assert repo.name_exists("Test Template") is True
        assert repo.name_exists("Nonexistent") is False
        assert repo.name_exists("Test Template", exclude_id=t.id) is False

    def test_count(self, repo: TemplateRepository):
        assert repo.count() == 0
        repo.save(_make_template())
        assert repo.count() == 1
        assert repo.count(source="custom") == 1
        assert repo.count(source="builtin") == 0

    def test_atomic_write(self, repo: TemplateRepository, tmp_path: Path):
        """确认写入后文件存在。"""
        t = _make_template()
        repo.save(t)
        yaml_file = tmp_path / "custom" / f"{t.id}.yaml"
        assert yaml_file.exists()

    def test_reload(self, repo: TemplateRepository, tmp_path: Path):
        t = _make_template()
        repo.save(t)
        assert repo.count() == 1
        repo.reload()
        assert repo.count() == 1
