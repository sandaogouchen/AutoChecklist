"""Checklist 模板业务服务。

提供模板的完整生命周期管理：创建、查询、更新、删除、
导入导出、复制、校验等操作。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import yaml

from app.domain.template_models import ChecklistTemplate, TemplateMetadata
from app.repositories.template_repository import TemplateRepository
from app.services.template_validator import TemplateValidator, ValidationResult

logger = logging.getLogger(__name__)


class TemplateNotFoundError(Exception):
    """模板未找到异常。"""
    pass


class TemplateConflictError(Exception):
    """模板冲突异常（名称重复等）。"""
    pass


class TemplatePermissionError(Exception):
    """模板权限异常（操作内置模板等）。"""
    pass


class TemplateService:
    """模板业务服务。

    封装模板的 CRUD 操作和业务逻辑，
    协调 TemplateRepository（持久化）和 TemplateValidator（校验）。
    """

    def __init__(
        self,
        repository: TemplateRepository,
        validator: TemplateValidator | None = None,
    ) -> None:
        self.repository = repository
        self.validator = validator or TemplateValidator()

    def create(
        self,
        content: str,
        fmt: str = "yaml",
    ) -> ChecklistTemplate:
        """创建新模板。

        Args:
            content: 模板内容（YAML 字符串或 JSON 字符串）。
            fmt: 输入格式（"yaml" 或 "json"）。

        Returns:
            创建后的模板。

        Raises:
            ValueError: 校验失败。
            TemplateConflictError: 名称重复。
        """
        data = self._parse_content(content, fmt)

        # 校验
        validation = self.validator.validate_dict(data)
        if not validation.valid:
            errors_msg = "; ".join(e.message for e in validation.errors)
            raise ValueError(f"模板校验失败: {errors_msg}")

        # 生成新 ID 和时间戳
        now = datetime.now(timezone.utc)
        data["id"] = str(uuid4())
        data["source"] = "custom"

        if "metadata" in data and isinstance(data["metadata"], dict):
            data["metadata"]["created_at"] = now.isoformat()
            data["metadata"]["updated_at"] = now.isoformat()

        template = ChecklistTemplate.model_validate(data)

        # 检查名称唯一性
        if self.repository.name_exists(template.metadata.name):
            raise TemplateConflictError(
                f"模板名称 '{template.metadata.name}' 已存在"
            )

        return self.repository.save(template)

    def get(self, template_id: str) -> ChecklistTemplate:
        """获取模板详情。

        Raises:
            TemplateNotFoundError: 模板不存在。
        """
        template = self.repository.get(template_id)
        if template is None:
            raise TemplateNotFoundError(f"模板 '{template_id}' 不存在")
        return template

    def get_optional(self, template_id: str) -> Optional[ChecklistTemplate]:
        """获取模板，不存在时返回 None（用于工作流降级场景）。"""
        return self.repository.get(template_id)

    def list_templates(
        self,
        *,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        project_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """列出模板（支持过滤和分页）。

        Returns:
            包含 templates, total, page, page_size 的字典。
        """
        page_size = min(max(page_size, 1), 100)
        page = max(page, 1)

        all_templates = self.repository.list_all(
            source=source,
            tag=tag,
            project_type=project_type,
        )
        total = len(all_templates)

        # 分页
        start = (page - 1) * page_size
        end = start + page_size
        page_templates = all_templates[start:end]

        return {
            "templates": [
                self._to_summary(t) for t in page_templates
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update(
        self,
        template_id: str,
        content: str,
        fmt: str = "yaml",
    ) -> ChecklistTemplate:
        """全量更新模板。

        Raises:
            TemplateNotFoundError: 模板不存在。
            TemplatePermissionError: 内置模板不可修改。
            ValueError: 校验失败。
            TemplateConflictError: 名称冲突。
        """
        existing = self.get(template_id)

        if existing.source == "builtin":
            raise TemplatePermissionError("内置模板不可修改")

        data = self._parse_content(content, fmt)

        # 校验
        validation = self.validator.validate_dict(data)
        if not validation.valid:
            errors_msg = "; ".join(e.message for e in validation.errors)
            raise ValueError(f"模板校验失败: {errors_msg}")

        # 保留 ID 和来源
        data["id"] = template_id
        data["source"] = "custom"

        # 更新时间戳，保留创建时间
        now = datetime.now(timezone.utc)
        if "metadata" in data and isinstance(data["metadata"], dict):
            data["metadata"]["created_at"] = existing.metadata.created_at.isoformat()
            data["metadata"]["updated_at"] = now.isoformat()

        template = ChecklistTemplate.model_validate(data)

        # 检查名称唯一性（排除自身）
        if self.repository.name_exists(template.metadata.name, exclude_id=template_id):
            raise TemplateConflictError(
                f"模板名称 '{template.metadata.name}' 已被其他模板使用"
            )

        return self.repository.save(template)

    def partial_update(
        self,
        template_id: str,
        updates: dict[str, Any],
    ) -> ChecklistTemplate:
        """部分更新模板。

        Args:
            template_id: 模板 ID。
            updates: 要更新的字段（支持嵌套路径如 metadata.name）。

        Raises:
            TemplateNotFoundError: 模板不存在。
            TemplatePermissionError: 内置模板不可修改。
        """
        existing = self.get(template_id)

        if existing.source == "builtin":
            raise TemplatePermissionError("内置模板不可修改")

        # 将现有模板转为 dict，合并更新
        data = existing.model_dump(mode="json")
        self._deep_merge(data, updates)

        # 更新时间戳
        now = datetime.now(timezone.utc)
        if "metadata" in data and isinstance(data["metadata"], dict):
            data["metadata"]["updated_at"] = now.isoformat()

        # 校验合并后的数据
        validation = self.validator.validate_dict(data)
        if not validation.valid:
            errors_msg = "; ".join(e.message for e in validation.errors)
            raise ValueError(f"模板校验失败: {errors_msg}")

        template = ChecklistTemplate.model_validate(data)

        # 检查名称唯一性（排除自身）
        if self.repository.name_exists(template.metadata.name, exclude_id=template_id):
            raise TemplateConflictError(
                f"模板名称 '{template.metadata.name}' 已被其他模板使用"
            )

        return self.repository.save(template)

    def delete(self, template_id: str) -> None:
        """删除模板。

        Raises:
            TemplateNotFoundError: 模板不存在。
            TemplatePermissionError: 内置模板不可删除。
        """
        existing = self.get(template_id)

        if existing.source == "builtin":
            raise TemplatePermissionError("内置模板不可删除")

        if not self.repository.delete(template_id):
            raise TemplateNotFoundError(f"模板 '{template_id}' 不存在")

    def validate(self, content: str, fmt: str = "yaml") -> ValidationResult:
        """校验模板格式（不保存）。

        Args:
            content: 模板内容。
            fmt: 输入格式。

        Returns:
            校验结果。
        """
        if fmt == "yaml":
            return self.validator.validate_yaml_string(content)

        try:
            import json
            data = json.loads(content)
        except Exception as e:
            result = ValidationResult()
            result.add_error("json", f"JSON 解析失败: {e}")
            return result

        return self.validator.validate_dict(data)

    def duplicate(self, template_id: str) -> ChecklistTemplate:
        """复制模板，创建一个新的自定义副本。

        Raises:
            TemplateNotFoundError: 源模板不存在。
        """
        source_template = self.get(template_id)

        # 创建副本数据
        data = source_template.model_dump(mode="json")
        now = datetime.now(timezone.utc)
        data["id"] = str(uuid4())
        data["source"] = "custom"

        # 处理名称（追加 "(copy)" 并避免冲突）
        base_name = source_template.metadata.name
        new_name = f"{base_name} (copy)"
        counter = 2
        while self.repository.name_exists(new_name):
            new_name = f"{base_name} (copy {counter})"
            counter += 1

        data["metadata"]["name"] = new_name
        data["metadata"]["created_at"] = now.isoformat()
        data["metadata"]["updated_at"] = now.isoformat()

        template = ChecklistTemplate.model_validate(data)
        return self.repository.save(template)

    def export_yaml(self, template_id: str) -> str:
        """导出模板为格式化的 YAML 字符串。

        Raises:
            TemplateNotFoundError: 模板不存在。
        """
        template = self.get(template_id)
        data = template.model_dump(mode="json")
        # 移除内部字段
        data.pop("source", None)

        return yaml.safe_dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    def import_yaml(self, content: str) -> ChecklistTemplate:
        """从 YAML 内容导入模板。

        自动生成新 ID，名称冲突时追加 "(imported)" 后缀。

        Args:
            content: YAML 字符串。

        Returns:
            导入后创建的模板。

        Raises:
            ValueError: 校验失败。
        """
        validation = self.validator.validate_yaml_string(content)
        if not validation.valid:
            errors_msg = "; ".join(e.message for e in validation.errors)
            raise ValueError(f"模板校验失败: {errors_msg}")

        data = yaml.safe_load(content)
        now = datetime.now(timezone.utc)

        # 生成新 ID
        data["id"] = str(uuid4())
        data["source"] = "custom"

        # 处理名称冲突
        if "metadata" in data and isinstance(data["metadata"], dict):
            name = data["metadata"].get("name", "Imported Template")
            if self.repository.name_exists(name):
                name = f"{name} (imported)"
                counter = 2
                while self.repository.name_exists(name):
                    base = data["metadata"].get("name", "Imported Template")
                    name = f"{base} (imported {counter})"
                    counter += 1
            data["metadata"]["name"] = name
            data["metadata"]["created_at"] = now.isoformat()
            data["metadata"]["updated_at"] = now.isoformat()

        template = ChecklistTemplate.model_validate(data)
        return self.repository.save(template)

    def _parse_content(self, content: str, fmt: str) -> dict[str, Any]:
        """解析输入内容为字典。"""
        if fmt == "yaml":
            try:
                data = yaml.safe_load(content)
            except yaml.YAMLError as e:
                raise ValueError(f"YAML 解析失败: {e}") from e
        elif fmt == "json":
            import json
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON 解析失败: {e}") from e
        else:
            raise ValueError(f"不支持的格式: {fmt}")

        if not isinstance(data, dict):
            raise ValueError("内容必须是一个映射（dict）")

        return data

    def _to_summary(self, template: ChecklistTemplate) -> dict[str, Any]:
        """将模板转为列表摘要格式。"""
        return {
            "template_id": template.id,
            "metadata": {
                "name": template.metadata.name,
                "description": template.metadata.description,
                "version": template.metadata.version,
                "tags": template.metadata.tags,
            },
            "source": template.source,
            "categories_count": len(template.categories),
            "total_items_count": template.total_items_count(),
        }

    def _deep_merge(self, base: dict, updates: dict) -> None:
        """深度合并更新到基础字典。"""
        for key, value in updates.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
