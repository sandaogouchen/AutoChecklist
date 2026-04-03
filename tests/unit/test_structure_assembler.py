"""Unit tests for actionable optimized_tree attachment in structure_assembler."""

from __future__ import annotations

from app.domain.checkpoint_models import Checkpoint
from app.domain.case_models import TestCase
from app.domain.checklist_models import CanonicalOutlineNode, ChecklistNode, CheckpointPathMapping
from app.nodes.structure_assembler import structure_assembler_node


def _group(node_id: str, title: str, children: list[ChecklistNode] | None = None) -> ChecklistNode:
    return ChecklistNode(
        node_id=node_id,
        title=title,
        node_type="group",
        children=children or [],
    )


def _leaf_titles(node: ChecklistNode) -> list[str]:
    return [child.title for child in node.children]


def test_structure_assembler_attaches_actionable_path_to_outline_tree() -> None:
    state = {
        "draft_cases": [
            TestCase(
                id="TC-001",
                title="验证 `optimize goal` 交互",
                preconditions=[
                    "campaign 已处于可创建 ad group 状态",
                    "用户已进入 `Create Ad Group` 页面",
                ],
                steps=[
                    "在页面中定位 `optimize goal` 模块",
                    "检查 `optimize goal` 是否默认可见且可交互",
                    "点击 `Submit` 提交 ad group",
                ],
                expected_results=[
                    "`optimize goal` 模块在创建阶段显式展示。",
                    "提交成功后保存的是用户当前选择的 `optimize goal`。",
                ],
                checkpoint_id="CP-001",
                evidence_refs=[],
            )
        ],
        "optimized_tree": [
            _group(
                "node-ad-group",
                "Ad group",
                [
                    _group(
                        "node-enter-page",
                        "进入 `Create Ad Group` 页面",
                        [
                            _group("node-optimize-goal", "定位 `optimize goal` 区域"),
                        ],
                    )
                ],
            )
        ],
        "checkpoint_paths": [
            CheckpointPathMapping(
                checkpoint_id="CP-001",
                path_node_ids=[
                    "node-ad-group",
                    "node-enter-page",
                    "node-optimize-goal",
                ],
            )
        ],
        "canonical_outline_nodes": [
            CanonicalOutlineNode(
                node_id="node-ad-group",
                display_text="Ad group",
                kind="business_object",
                visibility="visible",
            ),
            CanonicalOutlineNode(
                node_id="node-enter-page",
                display_text="进入 `Create Ad Group` 页面",
                kind="page",
                visibility="visible",
            ),
            CanonicalOutlineNode(
                node_id="node-optimize-goal",
                display_text="定位 `optimize goal` 区域",
                kind="action",
                visibility="visible",
            ),
        ],
    }

    result = structure_assembler_node(state)

    ad_group = result["optimized_tree"][0]
    assert ad_group.title == "Ad group"
    assert _leaf_titles(ad_group) == ["campaign 已处于可创建 ad group 状态"]

    campaign_ready = ad_group.children[0]
    assert _leaf_titles(campaign_ready) == ["进入 `Create Ad Group` 页面"]

    page_entry = campaign_ready.children[0]
    assert _leaf_titles(page_entry) == ["定位 `optimize goal` 区域"]

    locate_module = page_entry.children[0]
    assert _leaf_titles(locate_module) == ["检查 `optimize goal` 是否默认可见且可交互"]

    check_visibility = locate_module.children[0]
    assert _leaf_titles(check_visibility) == ["点击 `Submit` 提交 ad group"]

    submit_action = check_visibility.children[0]
    assert _leaf_titles(submit_action) == [
        "`optimize goal` 模块在创建阶段显式展示。",
        "提交成功后保存的是用户当前选择的 `optimize goal`。",
    ]
    assert all(child.node_type == "expected_result" for child in submit_action.children)


def test_structure_assembler_merges_equivalent_page_and_operation_nodes() -> None:
    state = {
        "draft_cases": [
            TestCase(
                id="TC-001",
                title="用例一",
                preconditions=["用户已进入 `Create Ad Group` 页面"],
                steps=["在页面中定位 `optimize goal` 模块"],
                expected_results=["结果一"],
                checkpoint_id="CP-001",
                evidence_refs=[],
            ),
            TestCase(
                id="TC-002",
                title="用例二",
                preconditions=["进入 `Create Ad Group` 页面"],
                steps=["定位 `optimize goal` 区域"],
                expected_results=["结果二"],
                checkpoint_id="CP-001",
                evidence_refs=[],
            ),
        ],
        "optimized_tree": [_group("node-ad-group", "Ad group")],
        "checkpoint_paths": [
            CheckpointPathMapping(
                checkpoint_id="CP-001",
                path_node_ids=["node-ad-group"],
            )
        ],
        "canonical_outline_nodes": [
            CanonicalOutlineNode(
                node_id="node-ad-group",
                display_text="Ad group",
                kind="business_object",
                visibility="visible",
            )
        ],
    }

    result = structure_assembler_node(state)

    ad_group = result["optimized_tree"][0]
    assert _leaf_titles(ad_group) == ["进入 `Create Ad Group` 页面"]

    page_entry = ad_group.children[0]
    assert _leaf_titles(page_entry) == ["定位 `optimize goal` 模块"]

    locate_node = page_entry.children[0]
    assert _leaf_titles(locate_node) == ["结果一", "结果二"]


def test_structure_assembler_adds_code_mismatch_pointer_and_logic_branch() -> None:
    state = {
        "draft_cases": [
            TestCase(
                id="TC-001",
                title="验证提交结果",
                preconditions=["用户已进入提交页"],
                steps=["点击 `Submit`"],
                expected_results=["提交成功"],
                checkpoint_id="CP-001",
                evidence_refs=[],
            )
        ],
        "checkpoints": [
            Checkpoint(
                checkpoint_id="CP-001",
                title="验证提交结果",
                code_consistency={
                    "status": "mismatch",
                    "detail": "实际代码走降级分支",
                    "actual_implementation": "1. 先检查开关。\n2. 开关关闭时直接走 fallback 结果。",
                    "code_snippet": "if not flag: return fallback",
                },
            )
        ],
        "optimized_tree": [
            _group(
                "node-submit",
                "提交流程",
                [
                    _group("node-submit-action", "点击 `Submit`"),
                ],
            )
        ],
        "checkpoint_paths": [
            CheckpointPathMapping(
                checkpoint_id="CP-001",
                path_node_ids=["node-submit", "node-submit-action"],
            )
        ],
        "canonical_outline_nodes": [
            CanonicalOutlineNode(
                node_id="node-submit",
                display_text="提交流程",
                kind="business_object",
                visibility="visible",
            ),
            CanonicalOutlineNode(
                node_id="node-submit-action",
                display_text="点击 `Submit`",
                kind="action",
                visibility="visible",
            ),
        ],
    }

    result = structure_assembler_node(state)

    case = result["test_cases"][0]
    assert case.expected_results[-1].startswith("[TODO-CODE-MISMATCH] 代码实现逻辑-1")

    submit_action = result["optimized_tree"][0].children[0]
    assert submit_action.title == "点击 `Submit`"
    assert [child.title for child in submit_action.children[:2]] == [
        "提交成功",
        "[TODO-CODE-MISMATCH] 代码实现逻辑-1: 代码实现与 PRD 不一致",
    ]

    logic_branch = result["optimized_tree"][1]
    assert logic_branch.title == "代码实现逻辑"
    assert logic_branch.children[0].title == "代码实现逻辑-1"
    assert [child.title for child in logic_branch.children[0].children] == [
        "1. 先检查开关。",
        "2. 开关关闭时直接走 fallback 结果。",
    ]
