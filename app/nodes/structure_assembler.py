"""结构组装节点。
对 LLM 生成的草稿用例进行标准化处理：
- 补全缺失的 ID（自动编号 TC-001, TC-002, ...）
- 为空字段填充默认值
- 补充缺失的证据引用（从 mapped_evidence 中查找）
- 保留并补全 checkpoint_id
- 对文本字段进行中英文混排规范化
- 从 checkpoint 继承模版绑定字段（兜底补全）
- 执行强制约束后置校验和 source 标注

改造说明：
- 移除对 source="reference" 节点的特殊保护逻辑
  （改造后不再有来自参考树的 reference 源节点，所有节点均为 LLM 生成）
- 保留 mandatory_skeleton 的强制约束逻辑（独立于 XMind 参考模板）
- assembler 的输入仅为 planner 输出的 optimized_tree + checkpoint_path_collection
"""
from __future__ import annotations

import logging

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.domain.checkpoint_models import Checkpoint
from app.domain.state import CaseGenState
from app.domain.template_models import MandatorySkeletonNode
from app.services.checkpoint_outline_planner import attach_expected_results_to_outline
from app.services.text_normalizer import normalize_test_case

logger = logging.getLogger(__name__)


def structure_assembler_node(state: CaseGenState) -> CaseGenState:
    """组装并标准化测试用例。"""
    assembled_cases: list[TestCase] = []
    evidence_lookup = state.get("mapped_evidence", {})
    checkpoints: list[Checkpoint] = state.get("checkpoints", [])
    cp_lookup: dict[str, Checkpoint] = {
        cp.checkpoint_id: cp for cp in checkpoints if cp.checkpoint_id
    }

    for index, case in enumerate(state.get("draft_cases", []), start=1):
        update_fields = {
            "id": case.id or f"TC-{index:03d}",
            "preconditions": case.preconditions or [],
            "steps": case.steps or [],
            "expected_results": case.expected_results or [],
            "priority": case.priority or "P2",
            "category": case.category or "functional",
            "evidence_refs": case.evidence_refs or evidence_lookup.get(case.title, []),
            "checkpoint_id": case.checkpoint_id or "",
        }

        # ---- 模版字段兜底继承 ----
        if not case.template_leaf_id and case.checkpoint_id:
            cp = cp_lookup.get(case.checkpoint_id)
            if cp and cp.template_leaf_id:
                update_fields.update({
                    "template_leaf_id": cp.template_leaf_id,
                    "template_path_ids": cp.template_path_ids,
                    "template_path_titles": cp.template_path_titles,
                    "template_match_confidence": cp.template_match_confidence,
                    "template_match_low_confidence": cp.template_match_low_confidence,
                })
                logger.info(
                    "Checklist template inheritance: case_id=%s checkpoint_id=%s "
                    "inherited_leaf_id=%s path=%s confidence=%.2f low_confidence=%s",
                    case.id or f"draft-{index}",
                    case.checkpoint_id,
                    cp.template_leaf_id,
                    " > ".join(cp.template_path_titles) or "-",
                    cp.template_match_confidence,
                    cp.template_match_low_confidence,
                )

        assembled = case.model_copy(update=update_fields)
        assembled = normalize_test_case(assembled)
        assembled_cases.append(assembled)

    logger.info(
        "Checklist integration starting: draft_cases=%d optimized_tree_roots=%d "
        "checkpoint_paths=%d canonical_outline_nodes=%d template_bound_cases=%d",
        len(state.get("draft_cases", [])),
        len(state.get("optimized_tree", [])),
        len(state.get("checkpoint_paths", [])),
        len(state.get("canonical_outline_nodes", [])),
        sum(1 for case in assembled_cases if case.template_leaf_id),
    )

    optimized_tree = attach_expected_results_to_outline(
        state.get("optimized_tree", []),
        assembled_cases,
        state.get("checkpoint_paths", []),
        state.get("canonical_outline_nodes", []),
    )

    # ---- 强制约束后置校验 ----
    mandatory_skeleton = state.get("mandatory_skeleton")
    if mandatory_skeleton:
        optimized_tree = _enforce_mandatory_constraints(
            optimized_tree, mandatory_skeleton
        )
        _annotate_source(optimized_tree, mandatory_skeleton)

    logger.info(
        "Checklist integration completed: test_cases=%d optimized_tree_roots=%d",
        len(assembled_cases),
        len(optimized_tree),
    )

    return {
        "test_cases": assembled_cases,
        "optimized_tree": optimized_tree,
    }


def _enforce_mandatory_constraints(
    tree: list[ChecklistNode],
    skeleton: MandatorySkeletonNode,
) -> list[ChecklistNode]:
    """强制约束最终防线：确保输出树的强制节点与骨架一致。

    策略：
    1. 检查骨架中的每个强制节点是否存在于树中
    2. 缺失的节点从骨架复原
    3. 强制层级中的非模版节点的子内容迁移到最近的模版节点下
    """
    if not skeleton.children:
        return tree

    skeleton_ids = _collect_skeleton_ids(skeleton)
    tree_lookup: dict[str, ChecklistNode] = {}
    _index_tree(tree, tree_lookup)

    result: list[ChecklistNode] = []
    for sk_child in skeleton.children:
        restored = _restore_or_merge(sk_child, tree_lookup)
        result.append(restored)

    # 保留非骨架的顶层节点
    result_ids = {n.node_id for n in result}
    overflow_cases: list[ChecklistNode] = []
    for node in tree:
        if node.node_id not in skeleton_ids and node.node_id not in result_ids:
            # 所有节点现在均为 LLM 生成，不再有 reference 源节点需要特殊保护。
            # 仅保护 template 来源的节点不进入溢出区。
            if node.source == "template":
                result.append(node)
            elif node.children or node.node_type in ("expected_result", "case"):
                overflow_cases.append(node)

    if overflow_cases:
        overflow_ratio = len(overflow_cases) / max(len(tree), 1)
        if overflow_ratio > 0.2:
            logger.warning(
                "大量节点进入溢出区 (%d/%d = %.0f%%)，建议检查模版与 PRD 的匹配度",
                len(overflow_cases),
                len(tree),
                overflow_ratio * 100,
            )

        result.append(
            ChecklistNode(
                node_id="_overflow",
                title="待分配 (Overflow)",
                node_type="group",
                source="overflow",
                children=overflow_cases,
            )
        )

    return result


def _restore_or_merge(
    sk_node: MandatorySkeletonNode,
    tree_lookup: dict[str, ChecklistNode],
) -> ChecklistNode:
    """从树中查找对应节点或从骨架复原。"""
    existing = tree_lookup.get(sk_node.id)
    merged_children: list[ChecklistNode] = []
    sk_child_ids = {c.id for c in sk_node.children}

    for sk_child in sk_node.children:
        merged_children.append(_restore_or_merge(sk_child, tree_lookup))

    # 保留已有节点的非骨架子节点
    if existing:
        for child in existing.children:
            if child.node_id not in sk_child_ids:
                merged_children.append(child)

    priority = sk_node.original_metadata.get("priority", "P2")
    return ChecklistNode(
        node_id=sk_node.id,
        title=sk_node.title,
        node_type="group",
        hidden=False,
        source="template",
        is_mandatory=sk_node.is_mandatory,
        priority=priority,
        children=merged_children,
    )


def _annotate_source(
    tree: list[ChecklistNode],
    skeleton: MandatorySkeletonNode,
) -> None:
    """为每个节点标注 source 字段。"""
    skeleton_ids = _collect_skeleton_ids(skeleton)
    for node in tree:
        _set_source_recursive(node, skeleton_ids)


def _set_source_recursive(node: ChecklistNode, skeleton_ids: set[str]) -> None:
    """递归设置 source 标记。

    改造说明：移除了对 source="reference" 的特殊保留逻辑。
    改造后所有节点均为 LLM 生成（source="generated"）或来自 YAML 模板
    （source="template"），不再有参考树来源的节点。
    """
    if node.node_id in skeleton_ids:
        node.source = "template"
        node.is_mandatory = True
    elif node.node_id == "_overflow":
        node.source = "overflow"
    # children 中的 source 不需要覆盖（保留 generated 默认值或已设置的值）
    for child in node.children:
        _set_source_recursive(child, skeleton_ids)


def _collect_skeleton_ids(node: MandatorySkeletonNode) -> set[str]:
    """收集骨架中所有节点 ID。"""
    ids = {node.id}
    for child in node.children:
        ids.update(_collect_skeleton_ids(child))
    return ids


def _index_tree(tree: list[ChecklistNode], lookup: dict[str, ChecklistNode]) -> None:
    """递归索引树节点。"""
    for node in tree:
        if node.node_id:
            lookup[node.node_id] = node
        _index_tree(node.children, lookup)
