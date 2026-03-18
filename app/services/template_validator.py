"""Checklist 模板格式校验服务。

提供独立的模板 YAML 内容校验能力，在创建/更新模板时自动执行，
也可通过 /validate 端点独立调用。

校验级别：
- ERROR: 阻止创建/更新
- WARN: 允许操作但给出提醒
- INFO: 信息性提示
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from app.domain.template_models import ChecklistTemplate, SEMVER_PATTERN, VALID_PRIORITIES

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """校验问题。"""
    level: Literal["error", "warning", "info"]
    path: str
    message: str


@dataclass
class ValidationResult:
    """校验结果。"""
    valid: bool = True
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    infos: list[ValidationIssue] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def add_error(self, path: str, message: str) -> None:
        """添加错误级别问题。"""
        self.errors.append(ValidationIssue(level="error", path=path, message=message))
        self.valid = False

    def add_warning(self, path: str, message: str) -> None:
        """添加警告级别问题。"""
        self.warnings.append(ValidationIssue(level="warning", path=path, message=message))

    def add_info(self, path: str, message: str) -> None:
        """添加信息级别提示。"""
        self.infos.append(ValidationIssue(level="info", path=path, message=message))

    def to_dict(self) -> dict[str, Any]:
        """转换为 API 响应格式的字典。"""
        result: dict[str, Any] = {"valid": self.valid}
        if self.errors:
            result["errors"] = [
                {"path": e.path, "message": e.message} for e in self.errors
            ]
        if self.warnings:
            result["warnings"] = [w.message for w in self.warnings]
        if self.stats:
            result["stats"] = self.stats
        return result


class TemplateValidator:
    """模板校验器。"""

    def validate_yaml_string(self, content: str) -> ValidationResult:
        """校验 YAML 字符串格式的模板内容。

        执行顺序：
        1. YAML 语法解析
        2. Pydantic 模型校验
        3. 业务规则校验（warnings / infos）

        Args:
            content: YAML 格式的模板字符串。

        Returns:
            校验结果。
        """
        result = ValidationResult()

        # 步骤 1: YAML 语法解析
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            line_info = ""
            if hasattr(e, "problem_mark") and e.problem_mark is not None:
                mark = e.problem_mark
                line_info = f"（第 {mark.line + 1} 行）"
            result.add_error("yaml", f"YAML 解析失败：{e}{line_info}")
            return result

        if not isinstance(data, dict):
            result.add_error("root", "YAML 内容必须是一个映射（dict）")
            return result

        return self.validate_dict(data, result)

    def validate_dict(
        self,
        data: dict[str, Any],
        result: ValidationResult | None = None,
    ) -> ValidationResult:
        """校验字典格式的模板数据。

        Args:
            data: 模板数据字典。
            result: 可选的已有校验结果（用于累积错误）。

        Returns:
            校验结果。
        """
        if result is None:
            result = ValidationResult()

        # 步骤 2: Pydantic 模型校验
        try:
            template = ChecklistTemplate.model_validate(data)
        except ValidationError as e:
            for error in e.errors():
                path = ".".join(str(loc) for loc in error["loc"])
                result.add_error(path, error["msg"])
            return result

        # 步骤 3: 业务规则校验
        self._check_business_rules(template, result)

        # 统计信息
        result.stats = {
            "categories_count": len(template.categories),
            "total_items_count": template.total_items_count(),
            "total_rules_count": template.total_rules_count(),
        }

        return result

    def _check_business_rules(
        self,
        template: ChecklistTemplate,
        result: ValidationResult,
    ) -> None:
        """检查业务规则（warnings 和 infos）。"""
        # WARN: 维度仅 1 个检查项
        for i, cat in enumerate(template.categories):
            if len(cat.items) == 1:
                result.add_warning(
                    f"categories[{i}].items",
                    f"维度 '{cat.name}' 仅有 1 个检查项，建议至少 2 个",
                )

            # WARN: 检查项无 rules
            for j, item in enumerate(cat.items):
                if not item.rules:
                    result.add_warning(
                        f"categories[{i}].items[{j}].rules",
                        f"检查项 '{item.title}' 未定义具体规则，可能影响生成质量",
                    )

        # WARN: 描述为空
        if not template.metadata.description:
            result.add_warning(
                "metadata.description",
                "建议填写模板描述，便于其他用户了解模板用途",
            )

        # INFO: 维度过多
        cat_count = len(template.categories)
        if cat_count > 10:
            result.add_info(
                "categories",
                f"模板包含 {cat_count} 个维度，维度过多可能导致生成用例过于分散",
            )
