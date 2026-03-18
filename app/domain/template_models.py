"""Checklist 模板领域模型。

定义了 Checklist 模板的数据结构，用于将 QA 团队的领域经验
编码为可复用的结构化模板，约束 LLM 的测试用例生成过程。

核心模型层次：
- ChecklistTemplate: 顶层模板
  - TemplateMetadata: 元信息
  - TemplateSettings: 全局配置
  - TemplateCategory: 测试维度
    - TemplateCategoryItem: 检查项
  - TemplateExclusion: 排除规则
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

# 优先级枚举值
VALID_PRIORITIES = ("critical", "high", "medium", "low")

# 语义化版本格式正则
SEMVER_PATTERN = re.compile(r"^\d+\.\d+(\.\d+)?$")


class TemplateExclusion(BaseModel):
    """排除规则。

    定义不需要生成测试用例的内容模式。
    """
    pattern: str
    reason: str = ""


class TemplateCategoryItem(BaseModel):
    """测试维度下的检查项。

    每个检查项定义一个具体的测试关注点，
    可选地包含具体的约束规则列表。
    """
    title: str
    description: str = ""
    priority: Optional[str] = None
    rules: list[str] = Field(default_factory=list)

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(
                f"优先级必须为 {'/'.join(VALID_PRIORITIES)} 之一，收到: {v}"
            )
        return v


class TemplateCategory(BaseModel):
    """测试维度。

    模板的一级分类，如"功能正确性"、"安全性"等，
    每个维度下包含一个或多个检查项。
    """
    name: str
    description: str = ""
    priority: Optional[str] = None
    items: list[TemplateCategoryItem] = Field(min_length=1)

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(
                f"优先级必须为 {'/'.join(VALID_PRIORITIES)} 之一，收到: {v}"
            )
        return v


class TemplateMetadata(BaseModel):
    """模板元信息。"""
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    version: str = "1.0.0"
    author: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    applicable_project_types: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not SEMVER_PATTERN.match(v):
            raise ValueError(
                f"版本号必须符合语义化版本格式 (如 1.0.0)，收到: {v}"
            )
        return v


class TemplateSettings(BaseModel):
    """模板全局配置。"""
    default_priority: str = "medium"
    min_cases_per_category: int = Field(default=2, ge=1, le=20)
    require_negative_cases: bool = True
    require_boundary_cases: bool = True
    language: Optional[str] = None

    @field_validator("default_priority")
    @classmethod
    def validate_default_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(
                f"默认优先级必须为 {'/'.join(VALID_PRIORITIES)} 之一，收到: {v}"
            )
        return v


class ChecklistTemplate(BaseModel):
    """Checklist 模板顶层模型。

    将 QA 团队的领域经验编码为结构化模板，
    用于约束 LLM 生成测试用例时的维度覆盖和规则遵循。
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    metadata: TemplateMetadata
    settings: TemplateSettings = Field(default_factory=TemplateSettings)
    categories: list[TemplateCategory] = Field(min_length=1)
    exclusions: list[TemplateExclusion] = Field(default_factory=list)
    source: Literal["builtin", "custom"] = "custom"

    def total_items_count(self) -> int:
        """统计模板中检查项的总数。"""
        return sum(len(cat.items) for cat in self.categories)

    def total_rules_count(self) -> int:
        """统计模板中规则的总数。"""
        return sum(
            len(item.rules)
            for cat in self.categories
            for item in cat.items
        )

    def format_for_checkpoint_prompt(self) -> str:
        """将模板格式化为适合注入检查点生成 LLM 提示的文本。"""
        lines: list[str] = []
        lines.append("## 测试集模板约束\n")
        lines.append(
            "以下模板定义了必须覆盖的测试维度和检查项。"
            "在生成检查点时，请确保每个模板维度都有对应的检查点覆盖。\n"
        )

        for i, cat in enumerate(self.categories, 1):
            priority_tag = f" [priority={cat.priority}]" if cat.priority else ""
            lines.append(f"### 维度 {i}：{cat.name}{priority_tag}")
            if cat.description:
                lines.append(f"{cat.description}")
            lines.append("检查项：")
            for item in cat.items:
                item_priority = f"[{item.priority}] " if item.priority else ""
                lines.append(
                    f"- {item_priority}{item.title}：{item.description}"
                )
                if item.rules:
                    rules_text = "；".join(item.rules)
                    lines.append(f"  规则：{rules_text}")
            lines.append("")

        # 全局设置
        lines.append("### 全局设置")
        lines.append(f"- 每个维度最少用例数：{self.settings.min_cases_per_category}")
        lines.append(
            f"- 要求包含反向测试：{'是' if self.settings.require_negative_cases else '否'}"
        )
        lines.append(
            f"- 要求包含边界测试：{'是' if self.settings.require_boundary_cases else '否'}"
        )

        return "\n".join(lines)

    def format_for_draft_prompt(
        self,
        template_category: Optional[str] = None,
        template_item_title: Optional[str] = None,
    ) -> str:
        """将模板格式化为适合注入用例生成 LLM 提示的文本。

        如果指定了 template_category 和 template_item_title，
        则只返回对应维度和检查项的规则约束。
        """
        lines: list[str] = []

        # 查找匹配的检查项规则
        matched_rules: list[str] = []
        matched_category_name = ""
        matched_item_title = ""

        if template_category:
            for cat in self.categories:
                if cat.name == template_category:
                    matched_category_name = cat.name
                    if template_item_title:
                        for item in cat.items:
                            if item.title == template_item_title:
                                matched_item_title = item.title
                                matched_rules = item.rules
                                break
                    break

        if matched_category_name:
            lines.append("## 模板规则约束")
            if matched_item_title:
                lines.append(f"- 关联模板维度：{matched_category_name}")
                lines.append(f"- 关联模板检查项：{matched_item_title}")
                if matched_rules:
                    for rule in matched_rules:
                        lines.append(f"- {rule}")
            lines.append("")

        # 全局设置
        lines.append("## 全局模板设置")
        if self.settings.require_negative_cases:
            lines.append(
                "- 要求包含反向测试：是 → 请为此检查点同时生成至少 1 个反向测试用例"
            )
        if self.settings.require_boundary_cases:
            lines.append(
                "- 要求包含边界测试：是 → 如涉及输入字段，请生成边界值测试用例"
            )
        lines.append(
            f"- 每个维度最少用例数：{self.settings.min_cases_per_category}"
        )

        return "\n".join(lines)
