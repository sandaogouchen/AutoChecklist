"""Checklist 树形结构模型。

定义用于表示合并后 Checklist 树的 Pydantic 模型。
使用递归结构 ``ChecklistNode`` 支持任意深度的分组嵌套。

该模型是 F1（前置操作合并）的核心数据结构，
由 ``ChecklistMerger`` 的 Trie 算法生成，
被 ``markdown_renderer`` 和 ``XMindPayloadBuilder`` 消费。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.research_models import EvidenceRef


class ChecklistNode(BaseModel):
    """Checklist 树节点。

    ``node_type`` 为 ``"group"`` 时表示中间分组节点，
    ``children`` 中包含子节点；``node_type`` 为 ``"case"``
    时表示叶子节点，携带完整的测试用例信息。

    Attributes:
        node_id: 节点唯一标识（group 节点自动生成，case 节点沿用原 TestCase.id）。
        title: 节点标题——group 为公共前置操作描述，case 为用例标题。
        node_type: 节点类型，``"group"`` 或 ``"case"``。
        children: 子节点列表（仅 group 有效）。
        test_case_ref: 原始 TestCase.id 引用（仅 case 有效）。
        remaining_steps: 去掉公共前缀后剩余的操作步骤（仅 case）。
        expected_results: 预期结果列表（仅 case）。
        priority: 优先级（P0-P3），默认 P2。
        category: 用例类别（functional / edge_case / performance 等）。
        evidence_refs: 关联的 PRD 原文证据引用。
        checkpoint_id: 所属 checkpoint 标识。
    """

    node_id: str = ""
    title: str = ""
    node_type: Literal["group", "case"] = "group"
    children: list[ChecklistNode] = Field(default_factory=list)

    # ---- 以下字段仅 case 节点使用 ----
    test_case_ref: str = ""
    remaining_steps: list[str] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)
    priority: str = "P2"
    category: str = "functional"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    checkpoint_id: str = ""


# Pydantic v2 递归模型需要显式 rebuild
ChecklistNode.model_rebuild()
