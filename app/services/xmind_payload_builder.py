"""XMind 载荷构建器。
将测试用例、检查点、研究输出等数据映射为 XMind 思维导图的节点树结构。

变更：
- build() 新增 optimized_tree 参数
- 当 optimized_tree 非空时，使用树模式构建 XMind 节点
- 新增 source 颜色标记：template=蓝色, overflow=红色, reference=绿色
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.domain.checklist_models import ChecklistNode
from app.domain.xmind_models import XMindNode

if TYPE_CHECKING:
    from app.domain.case_models import TestCase
    from app.domain.checkpoint_models import Checkpoint
    from app.domain.research_models import ResearchOutput


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

# 来源 → XMind 标记映射
_SOURCE_MARKERS: dict[str, str] = {
    "template": "flag-blue",
    "overflow": "flag-red",
    "reference": "flag-green",
}


class XMindPayloadBuilder:
    """XMind 载荷构建器。"""

    def build(
        self,
        test_cases: list[TestCase],
        checkpoints: list[Checkpoint],
        research_output: ResearchOutput | None = None,
        run_id: str = "",
        title: str = "",
        optimized_tree: list[ChecklistNode] | None = None,
        enable_source_labels: bool = True,
    ) -> XMindNode:
        """构建 XMind 节点树。"""
        root_title = title or (f"测试用例 - {run_id}" if run_id else "测试用例")
        if optimized_tree:
            return self._build_tree_root(root_title, optimized_tree, enable_source_labels)
        return self._build_checkpoint_mode(
            root_title, test_cases, checkpoints, research_output
        )

    # -----------------------------------------------------------------------
    # 树模式：基于 optimized_tree（新增 source 颜色标记）
    # -----------------------------------------------------------------------

    def _build_tree_root(
        self,
        root_title: str,
        tree: list[ChecklistNode],
        enable_source_labels: bool = True,
    ) -> XMindNode:
        children: list[XMindNode] = []
        for node in tree:
            children.extend(self._build_tree_children(node, enable_source_labels))
        return XMindNode(title=root_title, children=children)

    def _build_tree_children(
        self,
        node: ChecklistNode,
        enable_source_labels: bool = True,
    ) -> list[XMindNode]:
        if node.node_type == "root":
            children: list[XMindNode] = []
            for child in node.children:
                children.extend(self._build_tree_children(child, enable_source_labels))
            return children

        if node.node_type in {"group", "precondition_group"}:
            if node.hidden:
                children: list[XMindNode] = []
                for child in node.children:
                    children.extend(self._build_tree_children(child, enable_source_labels))
                return children
            return [self._build_group_xmind_node(node, enable_source_labels)]

        if node.node_type == "expected_result":
            return [self._build_expected_result_xmind_node(node)]

        return [self._build_case_xmind_node(node)]

    def _build_group_xmind_node(
        self,
        node: ChecklistNode,
        enable_source_labels: bool = True,
    ) -> XMindNode:
        notes_parts: list[str] = []
        if node.preconditions:
            notes_parts.append("前置条件:")
            notes_parts.extend(f" - {pc}" for pc in node.preconditions)

        children: list[XMindNode] = []
        for child in node.children:
            children.extend(self._build_tree_children(child, enable_source_labels))

        # 构建标记列表（新增 source 标记）
        markers: list[str] = []
        if enable_source_labels:
            source_marker = _SOURCE_MARKERS.get(node.source)
            if source_marker:
                markers.append(source_marker)

        title = (
            f"[前置] {node.title}"
            if node.node_type == "precondition_group"
            else node.title
        )

        return XMindNode(
            title=title,
            children=children,
            notes="\n".join(notes_parts),
            markers=markers,
        )

    def _build_expected_result_xmind_node(self, node: ChecklistNode) -> XMindNode:
        return XMindNode(title=node.title)

    def _build_case_xmind_node(self, node: ChecklistNode) -> XMindNode:
        markers = []
        priority_marker = _PRIORITY_MARKERS.get(node.priority)
        if priority_marker:
            markers.append(priority_marker)
        category_marker = _CATEGORY_MARKERS.get(node.category)
        if category_marker:
            markers.append(category_marker)
        labels = [node.priority] if node.priority else []

        leaf_children: list[XMindNode] = []

        if node.preconditions:
            leaf_children.append(
                XMindNode(
                    title="前置条件",
                    children=[XMindNode(title=pc) for pc in node.preconditions],
                )
            )

        if node.steps:
            leaf_children.append(
                XMindNode(
                    title="步骤",
                    children=[
                        XMindNode(
                            title=(
                                step.strip()
                                if re.match(r"^\d+[\.|\)]\s+", (step or "").strip())
                                else f"{i}. {(step or '').strip()}"
                            )
                        )
                        for i, step in enumerate(node.steps, start=1)
                    ],
                )
            )

        if node.expected_results:
            leaf_children.append(
                XMindNode(
                    title="预期结果",
                    children=[
                        XMindNode(title=result)
                        for result in node.expected_results
                    ],
                )
            )

        ref_label = node.test_case_ref or node.node_id
        return XMindNode(
            title=f"[{ref_label}] {node.title}",
            children=leaf_children,
            markers=markers,
            labels=labels,
        )

    # -----------------------------------------------------------------------
    # Checkpoint 模式（原有逻辑，作为 fallback）
    # -----------------------------------------------------------------------

    def _build_checkpoint_mode(
        self,
        root_title: str,
        test_cases: list[TestCase],
        checkpoints: list[Checkpoint],
        research_output: ResearchOutput | None,
    ) -> XMindNode:
        cp_lookup: dict[str, Checkpoint] = {}
        for cp in checkpoints:
            if cp.checkpoint_id:
                cp_lookup[cp.checkpoint_id] = cp

        grouped: dict[str, list[TestCase]] = {}
        ungrouped: list[TestCase] = []

        for case in test_cases:
            if case.checkpoint_id and case.checkpoint_id in cp_lookup:
                grouped.setdefault(case.checkpoint_id, []).append(case)
            else:
                ungrouped.append(case)

        level1_children: list[XMindNode] = []

        for cp_id, cases in grouped.items():
            cp = cp_lookup[cp_id]
            cp_node = self._build_checkpoint_node(cp, cases)
            level1_children.append(cp_node)

        if ungrouped:
            other_node = XMindNode(
                title="其他用例",
                children=[self._build_case_node(case) for case in ungrouped],
            )
            level1_children.append(other_node)

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

    def _build_checkpoint_node(
        self, checkpoint: Checkpoint, cases: list[TestCase]
    ) -> XMindNode:
        markers = []
        category_marker = _CATEGORY_MARKERS.get(checkpoint.category)
        if category_marker:
            markers.append(category_marker)

        notes_parts: list[str] = []
        if checkpoint.objective:
            notes_parts.append(f"目标: {checkpoint.objective}")
        if checkpoint.evidence_refs:
            notes_parts.append("证据引用:")
            for ref in checkpoint.evidence_refs:
                notes_parts.append(
                    f" - {ref.section_title} (L{ref.line_start}-L{ref.line_end}): {ref.excerpt}"
                )

        return XMindNode(
            title=f"[{checkpoint.checkpoint_id}] {checkpoint.title}",
            children=[self._build_case_node(case) for case in cases],
            markers=markers,
            notes="\n".join(notes_parts),
            labels=[checkpoint.risk, checkpoint.category],
        )

    def _build_case_node(self, case: TestCase) -> XMindNode:
        labels = [case.priority] if case.priority else []
        markers = []
        priority_marker = _PRIORITY_MARKERS.get(case.priority)
        if priority_marker:
            markers.append(priority_marker)

        leaf_children: list[XMindNode] = []

        if case.preconditions:
            precond_node = XMindNode(
                title="前置条件",
                children=[XMindNode(title=pc) for pc in case.preconditions],
            )
            leaf_children.append(precond_node)

        if case.steps:
            steps_node = XMindNode(
                title="步骤",
                children=[
                    XMindNode(title=f"{i}. {step}")
                    for i, step in enumerate(case.steps, start=1)
                ],
            )
            leaf_children.append(steps_node)

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
