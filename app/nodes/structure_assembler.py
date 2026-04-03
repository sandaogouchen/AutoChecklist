"""结构组装节点。
对 LLM 生成的草稿用例进行标准化处理：
- 补全缺失的 ID（自动编号 TC-001, TC-002, ...）
- 为空字段填充默认值
- 补充缺失的证据引用（从 mapped_evidence 中查找）
- 保留并补全 checkpoint_id
- 对文本字段进行中英文混排规范化
- 从 checkpoint 继承模版绑定字段（兜底补全）
- 执行强制约束后置校验和 source 标注
- 应用代码一致性 TODO 标注（来自 MR 分析）
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.domain.checkpoint_models import Checkpoint
from app.domain.state import CaseGenState
from app.domain.template_models import MandatorySkeletonNode
from app.services.checkpoint_outline_planner import attach_expected_results_to_outline
from app.services.text_normalizer import normalize_test_case

logger = logging.getLogger(__name__)

_CODE_LOGIC_BRANCH_TITLE = "代码实现逻辑"


@dataclass
class _MismatchDetailRecord:
    case_id: str
    checkpoint_id: str
    pointer: str
    actual_implementation: str


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
            "Checklist pre-integration item: case_id=%s checkpoint_id=%s "
            "template_leaf_id=%s expected_results=%d",
            assembled.id or f"draft-{index}",
            assembled.checkpoint_id or "-",
            assembled.template_leaf_id or "-",
            len(assembled.expected_results or []),
        )

    # ---- 应用代码一致性 TODO 标注 ----
    assembled_cases, mismatch_details = _apply_consistency_todos(
        assembled_cases,
        checkpoints,
    )

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

    optimized_tree = _attach_code_mismatch_details(
        optimized_tree,
        mismatch_details,
        state.get("checkpoint_paths", []),
        state.get("canonical_outline_nodes", []),
    )

    logger.info(
        "Checklist integration completed: test_cases=%d optimized_tree_roots=%d",
        len(assembled_cases),
        len(optimized_tree),
    )

    return {
        "test_cases": assembled_cases,
        "optimized_tree": optimized_tree,
    }


def _apply_consistency_todos(
    cases: list[TestCase],
    checkpoints: list[Checkpoint],
) -> tuple[list[TestCase], list[_MismatchDetailRecord]]:
    """将代码一致性验证结果应用为 TODO 标注。

    遍历每个 test case，查找其关联 checkpoint 上的 code_consistency
    信息。对于 mismatch 或 unverified 状态的条目，在 test case 的
    expected_results 中追加 TODO 提示，帮助 QA 人员关注潜在风险。

    Args:
        cases: 已组装的测试用例列表。
        checkpoints: checkpoint 列表，可能携带 code_consistency 信息。

    Returns:
        ``(更新后的测试用例列表, mismatch 详情记录列表)``。
    """
    if not checkpoints:
        return cases, []

    cp_lookup: dict[str, Checkpoint] = {
        cp.checkpoint_id: cp for cp in checkpoints if cp.checkpoint_id
    }

    todo_count = 0
    mismatch_index = 0
    mismatch_records: list[_MismatchDetailRecord] = []
    for case in cases:
        if not case.checkpoint_id:
            continue

        cp = cp_lookup.get(case.checkpoint_id)
        if cp is None:
            continue

        consistency: dict[str, Any] | None = getattr(cp, "code_consistency", None)
        if not consistency:
            continue

        status = consistency.get("status", "")
        if status == "confirmed":
            # 代码与 PRD 一致，无需额外标注
            if not case.code_consistency:
                case.code_consistency = consistency
            continue

        # mismatch 才追加 TODO；unverified 仅保留状态和标签
        detail = consistency.get("detail", "")
        snippet = consistency.get("code_snippet", "")
        todo_text = ""

        if status == "mismatch":
            mismatch_index += 1
            pointer = f"{_CODE_LOGIC_BRANCH_TITLE}-{mismatch_index}"
            todo_text = (
                f"[TODO-CODE-MISMATCH] {pointer}: 代码实现与 PRD 不一致"
            )
            actual_implementation = str(
                consistency.get("actual_implementation", "")
            ).strip()
            if actual_implementation:
                mismatch_records.append(
                    _MismatchDetailRecord(
                        case_id=case.id or "",
                        checkpoint_id=case.checkpoint_id,
                        pointer=pointer,
                        actual_implementation=actual_implementation,
                    )
                )
            elif detail:
                mismatch_records.append(
                    _MismatchDetailRecord(
                        case_id=case.id or "",
                        checkpoint_id=case.checkpoint_id,
                        pointer=pointer,
                        actual_implementation=detail,
                    )
                )
        else:
            todo_text = ""

        # 追加到 expected_results
        if todo_text and todo_text not in case.expected_results:
            case.expected_results.append(todo_text)
            todo_count += 1

        # 同步 code_consistency 到 case
        if not case.code_consistency:
            case.code_consistency = consistency

        # 追加 tags
        tag = f"code-{status}"
        if hasattr(case, "tags") and tag not in case.tags:
            case.tags.append(tag)

    if todo_count > 0:
        logger.info(
            "Applied %d code consistency TODO annotations to test cases",
            todo_count,
        )

    return cases, mismatch_records


def _attach_code_mismatch_details(
    optimized_tree: list[ChecklistNode],
    mismatch_details: list[_MismatchDetailRecord],
    checkpoint_paths: list[Any],
    canonical_outline_nodes: list[Any],
) -> list[ChecklistNode]:
    """将 mismatch 的完整现状挂到 `代码实现逻辑` 分支下。"""
    if not optimized_tree or not mismatch_details:
        return optimized_tree

    tree = [node.model_copy(deep=True) for node in optimized_tree]
    root_group = _ensure_root_group(tree, _CODE_LOGIC_BRANCH_TITLE)

    for item in mismatch_details:
        pointer_group = _ensure_child_group(
            root_group,
            title=item.pointer,
            stable_key=f"{_CODE_LOGIC_BRANCH_TITLE}||{item.pointer}",
        )

        existing_leaf_titles = {child.title for child in pointer_group.children}
        for line in _split_actual_implementation_lines(item.actual_implementation):
            if line in existing_leaf_titles:
                continue
            pointer_group.children.append(
                ChecklistNode(
                    node_id=_stable_tree_id(
                        "CODE-LOGIC",
                        f"{_CODE_LOGIC_BRANCH_TITLE}||{item.pointer}||{line}",
                    ),
                    title=line,
                    node_type="expected_result",
                    source_test_case_refs=[item.case_id] if item.case_id else [],
                )
            )

    return tree


def _ensure_child_group(
    parent: ChecklistNode,
    *,
    title: str,
    stable_key: str,
) -> ChecklistNode:
    for child in parent.children:
        if child.node_type == "group" and child.title == title:
            return child

    node = ChecklistNode(
        node_id=_stable_tree_id("GROUP", stable_key),
        title=title,
        node_type="group",
        children=[],
    )
    parent.children.append(node)
    return node


def _ensure_root_group(
    tree: list[ChecklistNode],
    title: str,
) -> ChecklistNode:
    for node in tree:
        if node.node_type == "group" and node.title == title:
            return node

    root = ChecklistNode(
        node_id=_stable_tree_id("GROUP", title),
        title=title,
        node_type="group",
        children=[],
    )
    tree.append(root)
    return root


def _split_actual_implementation_lines(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines or [text.strip()]


def _stable_tree_id(prefix: str, raw: str) -> str:
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"




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
            # 保护 template 和 reference 来源的节点不进入溢出区
            if node.source in ("template", "reference"):
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
    """递归设置 source 标记。"""
    if node.node_id in skeleton_ids:
        node.source = "template"
        node.is_mandatory = True
    elif node.source == "reference":
        # 保留 reference 来源标记，不覆盖
        pass
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
