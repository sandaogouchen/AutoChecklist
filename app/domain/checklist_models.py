"""Checklist 树与大纲规划相关模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.domain.research_models import EvidenceRef


class ChecklistNode(BaseModel):
    """Checklist 树节点。

    node_type 决定节点语义：
    - root：虚拟根节点，仅作为子节点容器
    - group：共享前置/操作节点
    - expected_result：预期结果叶子节点

    同时保留旧的 ``precondition_group`` / ``case``，便于兼容已有
    渲染或历史数据。
    """

    model_config = ConfigDict(populate_by_name=True)

    node_id: str = Field(
        default="",
        validation_alias=AliasChoices("node_id", "id"),
    )
    title: str = Field(
        default="",
        validation_alias=AliasChoices("title", "display_text"),
    )
    node_type: Literal[
        "root",
        "group",
        "expected_result",
        "precondition_group",
        "case",
    ] = "group"
    children: list[ChecklistNode] = Field(default_factory=list)
    hidden: bool = False

    # ---- 来源与强制性标记 ----
    source: Literal["template", "generated", "overflow", "reference"] = "generated"
    is_mandatory: bool = False

    # ---- case 节点专属字段 ----
    test_case_ref: str = ""
    source_test_case_refs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)
    priority: str = "P2"
    category: str = "functional"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    checkpoint_id: str | None = None

    @field_validator("preconditions", "steps", "expected_results", mode="before")
    @classmethod
    def _coerce_case_fields_to_list(cls, value):
        """兼容旧输入：允许 steps/expected_results/preconditions 传字符串。"""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return [line.strip() for line in stripped.splitlines() if line.strip()]
        return value

    @property
    def id(self) -> str:
        return self.node_id

    @id.setter
    def id(self, value: str) -> None:
        self.node_id = value

    @property
    def display_text(self) -> str:
        return self.title

    @display_text.setter
    def display_text(self, value: str) -> None:
        self.title = value


class CanonicalOutlineNode(BaseModel):
    """Checkpoint 大纲规划阶段的规范节点定义。"""

    node_id: str
    semantic_key: str = ""
    display_text: str
    kind: Literal["business_object", "context", "page", "action"] = "context"
    visibility: Literal["visible", "required", "hidden"] = "visible"
    aliases: list[str] = Field(default_factory=list)


class CanonicalOutlineNodeCollection(BaseModel):
    """规范大纲节点集合。"""

    model_config = ConfigDict(populate_by_name=True)

    canonical_nodes: list[CanonicalOutlineNode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("canonical_nodes", "nodes"),
    )

    @property
    def nodes(self) -> list[CanonicalOutlineNode]:
        return self.canonical_nodes


class CheckpointPathMapping(BaseModel):
    """单个 checkpoint 对应的固定层级路径。"""

    checkpoint_id: str
    path_node_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("path_node_ids", "path"),
    )

    @property
    def path(self) -> list[str]:
        return self.path_node_ids


class CheckpointPathCollection(BaseModel):
    """Checkpoint 路径映射集合。"""

    model_config = ConfigDict(populate_by_name=True)

    checkpoint_paths: list[CheckpointPathMapping] = Field(
        default_factory=list,
        validation_alias=AliasChoices("checkpoint_paths", "mappings"),
    )

    @property
    def mappings(self) -> list[CheckpointPathMapping]:
        return self.checkpoint_paths


# Pydantic v2 要求显式 rebuild 以支持自引用
ChecklistNode.model_rebuild()
