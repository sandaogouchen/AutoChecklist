"""XMind 载荷构建器。

将测试用例、检查点、研究输出等数据映射为 XMind 思维导图的节点树结构。

层次结构（扁平模式，向后兼容）：
- 根节点：运行标题或 PRD 标题
  - 一级节点：按 checkpoint 或 fact 分组
    - 二级节点：测试用例标题（附带优先级标签）
      - 三级节点：步骤 + 预期结果（叶子节点）

F3 新增树形模式：
- 当 ``optimized_tree`` 不为空时，使用 ChecklistNode 树形结构直接
  构建 XMindNode 层级，保留前置操作合并后的分组关系。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.xmind_models import XMindNode

if TYPE_CHECKING:
    from app.domain.case_models import TestCase
    from app.domain.checklist_models import ChecklistNode
    from app.domain.checkpoint_models import Checkpoint
    from app.domain.research_models import ResearchOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 分类 → XMind 标记映射
# ---------------------------------------------------------------------------

_CATEGORY_MARKERS: dict[str, str] = {
    "functional": "star-blue",
    "edge_case": "star-orange",
    "performance": "star-green",
    "security": "star-red",
    "usability": "star-purple",
}

_PRIORITY_MARKERS: dict[str, str] = {
    "P0": "priority-1",
    "P1": "priority-2",
    "P2": "priority-3",
    "P3": "priority-4",
}


class XMindPayloadBuilder:
    """XMind 载荷构建器。

    将测试用例树结构映射为 ``XMindNode`` 层次结构，
    供 ``XMindConnector`` 序列化为 .xmind 文件。
    """

    def build(
        self,
        test_cases: list[TestCase],
        checkpoints: list[Checkpoint],
        research_output: ResearchOutput | None = None,
        run_id: str = "",
        title: str = "",
        optimized_tree: list[ChecklistNode] | None = None,
    ) -> XMindNode:
        """构建 XMind 节点树。

        当 ``optimized_tree`` 非空时，优先使用树形结构构建根节点，
        以保留前置操作合并后的层级关系（F3）。否则退回到按
        checkpoint 分组的扁平模式（向后兼容）。

        Args:
            test_cases: 测试用例列表。
            checkpoints: 检查点列表。
            research_output: 研究输出（可选，用于补充根节点信息）。
            run_id: 运行 ID。
            title: 根节点标题，为空时使用默认标题。
            optimized_tree: 合并后的 ChecklistNode 树（可选，F3 新增）。

        Returns:
            XMind 根节点。
        """
        root_title = title or f"测试用例 - {run_id}" if run_id else "测试用例"

        # --- F3: 优先使用 optimized_tree ---
        if optimized_tree:
            return self._build_tree_root(root_title, optimized_tree)

        # --- 原始扁平模式（向后兼容） ---
        # 构建 checkpoint_id → checkpoint 查找表
        cp_lookup: dict[str, Checkpoint] = {}
        for cp in checkpoints:
            if cp.checkpoint_id:
                cp_lookup[cp.checkpoint_id] = cp

        # 按 checkpoint_id 分组测试用例
        grouped: dict[str, list[TestCase]] = {}
        ungrouped: list[TestCase] = []

        for case in test_cases:
            if case.checkpoint_id and case.checkpoint_id in cp_lookup:
                grouped.setdefault(case.checkpoint_id, []).append(case)
            else:
                ungrouped.append(case)

        # 构建一级节点：checkpoint 分组
        level1_children: list[XMindNode] = []

        for cp_id, cases in grouped.items():
            cp = cp_lookup[cp_id]
            cp_node = self._build_checkpoint_node(cp, cases)
            level1_children.append(cp_node)

        # 未关联 checkpoint 的用例归到「其他用例」分组
        if ungrouped:
            other_node = XMindNode(
                title="其他用例",
                children=[self._build_case_node(case) for case in ungrouped],
            )
            level1_children.append(other_node)

        # 如果 research_output 中有未被覆盖的 fact，添加提示节点
        if research_output and research_output.facts:
            covered_fact_ids: set[str] = set()
            for cp in checkpoints:
                covered_fact_ids.update(cp.fact_ids)

            uncovered_facts = [
                f for f in research_output.facts
                if f.fact_id and f.fact_id not in covered_fact_ids
            ]
            if uncovered_facts:
                uncovered_node = XMindNode(
                    title=f"未覆盖的事实 ({len(uncovered_facts)})",
                    children=[
                        XMindNode(
                            title=f"[{f.fact_id}] {f.description}",
                            markers=["flag-red"],
                        )
                        for f in uncovered_facts
                    ],
                    markers=["flag-orange"],
                )
                level1_children.append(uncovered_node)

        return XMindNode(
            title=root_title,
            children=level1_children,
        )

    # ------------------------------------------------------------------
    # F3 新增: 树形模式构建方法
    # ------------------------------------------------------------------

    def _build_tree_root(
        self,
        root_title: str,
        optimized_tree: list[ChecklistNode],
    ) -> XMindNode:
        """从 ChecklistNode 树构建 XMind 根节点。

        Args:
            root_title: 根节点标题。
            optimized_tree: 顶层 ChecklistNode 列表。

        Returns:
            XMind 根节点。
        """
        children = [self._build_tree_node(node) for node in optimized_tree]
        return XMindNode(title=root_title, children=children)

    def _build_tree_node(self, node: ChecklistNode) -> XMindNode:
        """递归地将 ChecklistNode 转换为 XMindNode。

        根据 ``node_type`` 分发到分组节点或用例叶子节点。

        Args:
            node: ChecklistNode 实例。

        Returns:
            对应的 XMindNode。
        """
        if node.node_type == "case":
            return self._build_case_xmind_node(node)
        return self._build_group_xmind_node(node)

    def _build_group_xmind_node(self, node: ChecklistNode) -> XMindNode:
        """构建分组类型的 XMindNode（对应 node_type == "group"）。

        Args:
            node: 分组 ChecklistNode。

        Returns:
            分组 XMindNode，其子节点递归构建。
        """
        children = [self._build_tree_node(child) for child in node.children]
        return XMindNode(
            title=node.title or "(unnamed group)",
            children=children,
        )

    def _build_case_xmind_node(self, node: ChecklistNode) -> XMindNode:
        """构建用例叶子类型的 XMindNode（对应 node_type == "case"）。

        复用 ``_PRIORITY_MARKERS`` 为用例添加优先级图标。

        Args:
            node: 用例 ChecklistNode。

        Returns:
            用例 XMindNode，包含剩余步骤和预期结果。
        """
        markers: list[str] = []
        priority_marker = _PRIORITY_MARKERS.get(node.priority)
        if priority_marker:
            markers.append(priority_marker)

        labels = [node.priority] if node.priority else []

        leaf_children: list[XMindNode] = []

        if node.remaining_steps:
            steps_node = XMindNode(
                title="步骤",
                children=[
                    XMindNode(title=f"{i}. {step}")
                    for i, step in enumerate(node.remaining_steps, start=1)
                ],
            )
            leaf_children.append(steps_node)

        if node.expected_results:
            results_node = XMindNode(
                title="预期结果",
                children=[
                    XMindNode(title=result) for result in node.expected_results
                ],
            )
            leaf_children.append(results_node)

        return XMindNode(
            title=node.title or node.test_case_ref,
            children=leaf_children,
            markers=markers,
            labels=labels,
        )

    # ------------------------------------------------------------------
    # 原有扁平模式辅助方法（向后兼容）
    # ------------------------------------------------------------------

    def _build_checkpoint_node(
        self, checkpoint: Checkpoint, cases: list[TestCase]
    ) -> XMindNode:
        """构建 checkpoint 级别的节点。

        Args:
            checkpoint: 检查点对象。
            cases: 属于该检查点的测试用例列表。

        Returns:
            checkpoint 节点。
        """
        # 标记：根据分类选择不同的图标
        markers = []
        category_marker = _CATEGORY_MARKERS.get(checkpoint.category)
        if category_marker:
            markers.append(category_marker)

        # 备注：聚合证据引用
        notes_parts: list[str] = []
        if checkpoint.objective:
            notes_parts.append(f"目标: {checkpoint.objective}")
        if checkpoint.evidence_refs:
            notes_parts.append("证据引用:")
            for ref in checkpoint.evidence_refs:
                notes_parts.append(
                    f"  - {ref.section_title} (L{ref.line_start}-L{ref.line_end}): {ref.excerpt}"
                )

        return XMindNode(
            title=f"[{checkpoint.checkpoint_id}] {checkpoint.title}",
            children=[self._build_case_node(case) for case in cases],
            markers=markers,
            notes="\n".join(notes_parts),
            labels=[checkpoint.risk, checkpoint.category],
        )

    def _build_case_node(self, case: TestCase) -> XMindNode:
        """构建测试用例级别的节点。

        Args:
            case: 测试用例对象。

        Returns:
            测试用例节点，包含步骤和预期结果作为子节点。
        """
        # 标签：优先级
        labels = [case.priority] if case.priority else []

        # 标记：优先级图标
        markers = []
        priority_marker = _PRIORITY_MARKERS.get(case.priority)
        if priority_marker:
            markers.append(priority_marker)

        # 子节点：步骤和预期结果
        leaf_children: list[XMindNode] = []

        # 前置条件节点
        if case.preconditions:
            precond_node = XMindNode(
                title="前置条件",
                children=[
                    XMindNode(title=pc) for pc in case.preconditions
                ],
            )
            leaf_children.append(precond_node)

        # 步骤节点
        if case.steps:
            steps_node = XMindNode(
                title="步骤",
                children=[
                    XMindNode(title=f"{i}. {step}")
                    for i, step in enumerate(case.steps, start=1)
                ],
            )
            leaf_children.append(steps_node)

        # 预期结果节点
        if case.expected_results:
            results_node = XMindNode(
                title="预期结果",
                children=[
                    XMindNode(title=result) for result in case.expected_results
                ],
            )
            leaf_children.append(results_node)

        return XMindNode(
            title=f"[{case.id}] {case.title}",
            children=leaf_children,
            markers=markers,
            labels=labels,
        )
