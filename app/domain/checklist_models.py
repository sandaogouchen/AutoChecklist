"""Checklist 优化树节点模型。

将扁平 TestCase 列表按前置条件相同性分组后，构建 ≤3 层树结构:
root → precondition_group → case
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.research_models import EvidenceRef


class ChecklistNode(BaseModel):
    """Checklist 树节点。

    node_type 决定节点语义：
    - root：虚拟根节点，仅作为子节点容器
    - precondition_group：前置条件组，children 均为 case 类型
    - case：叶子节点，对应一条 TestCase
    """

    node_id: str = ""
    title: str = ""
    node_type: Literal["root", "precondition_group", "case"] = "precondition_group"
    children: list[ChecklistNode] = Field(default_factory=list)

    # ---- case 节点专属字段 ----
    test_case_ref: str = ""
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)
    priority: str = "P2"
    category: str = "functional"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    checkpoint_id: str = ""


# Pydantic v2 要求显式 rebuild 以支持自引用
ChecklistNode.model_rebuild()
