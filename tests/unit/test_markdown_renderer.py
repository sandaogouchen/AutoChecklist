"""Unit tests for markdown_renderer."""

from __future__ import annotations

import pytest

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.services.markdown_renderer import render_test_cases_markdown


def _tc(
    tc_id: str,
    title: str = "测试用例",
    preconditions: list[str] | None = None,
    steps: list[str] | None = None,
    expected_results: list[str] | None = None,
    checkpoint_id: str = "",
) -> TestCase:
    """Helper to build a minimal TestCase."""
    return TestCase(
        id=tc_id,
        title=title,
        preconditions=preconditions or [],
        steps=steps or ["步骤1"],
        expected_results=expected_results or ["预期结果1"],
        checkpoint_id=checkpoint_id,
    )


# ---------------------------------------------------------------------------
# Flat render tests
# ---------------------------------------------------------------------------

class TestFlatRender:
    """Tests for flat (backward-compatible) rendering."""

    def test_empty_input(self) -> None:
        md = render_test_cases_markdown([])
        assert "暂无测试用例" in md

    def test_single_case(self) -> None:
        md = render_test_cases_markdown([_tc("TC-001", "验证登录")])
        assert "## TC-001 验证登录" in md

    def test_with_preconditions(self) -> None:
        md = render_test_cases_markdown(
            [_tc("TC-001", preconditions=["用户已注册", "网络正常"])]
        )
        assert "- 用户已注册" in md
        assert "- 网络正常" in md

    def test_with_checkpoint_id(self) -> None:
        md = render_test_cases_markdown(
            [_tc("TC-001", checkpoint_id="CP-abc123")]
        )
        assert "**Checkpoint:** CP-abc123" in md

    def test_no_preconditions_shows_none(self) -> None:
        md = render_test_cases_markdown([_tc("TC-001", preconditions=[])])
        assert "- 无" in md

    def test_fallback_when_tree_empty(self) -> None:
        """Empty tree → flat mode."""
        md = render_test_cases_markdown([_tc("TC-001")], optimized_tree=[])
        assert "## TC-001" in md

    def test_fallback_when_tree_none(self) -> None:
        """None tree → flat mode."""
        md = render_test_cases_markdown([_tc("TC-001")], optimized_tree=None)
        assert "## TC-001" in md


# ---------------------------------------------------------------------------
# Tree render tests
# ---------------------------------------------------------------------------

def _group_node(
    title: str,
    children: list[ChecklistNode],
    hidden: bool = False,
) -> ChecklistNode:
    """Helper to build a group node."""
    return ChecklistNode(
        node_id=f"GRP-test",
        title=title,
        node_type="group",
        children=children,
        hidden=hidden,
    )


def _expected_leaf(
    title: str,
) -> ChecklistNode:
    """Helper to build an expected-result leaf."""
    return ChecklistNode(
        node_id=f"EXP-{title}",
        title=title,
        node_type="expected_result",
    )


class TestTreeRender:
    """Tests for tree-mode rendering."""

    def test_tree_can_render_before_expected_result_leaves_exist(self) -> None:
        tree = [
            _group_node(
                "Ad group",
                [
                    _group_node(
                        "CBO",
                        [
                            _group_node(
                                "launch 前",
                                [
                                    _group_node("定位 `optimize goal` 区域", []),
                                ],
                            )
                        ],
                    )
                ],
            )
        ]
        md = render_test_cases_markdown([], optimized_tree=tree)
        assert "## Ad group" in md
        assert "### CBO" in md
        assert "#### launch 前" in md
        assert "##### 定位 `optimize goal` 区域" in md
        assert "[TC-" not in md

    def test_renders_shared_logic_path_only(self) -> None:
        tree = [
            _group_node(
                "系统已部署测试版本",
                [
                    _group_node(
                        "用户已登录系统",
                        [
                            _group_node(
                                "进入 `Create Ad Group` 页面",
                                [
                                    _group_node(
                                        "定位 `optimize goal` 区域",
                                        [
                                            _expected_leaf("`optimize goal` 字段在创建阶段显式可见。"),
                                            _expected_leaf("用户可主动选择 `optimize goal`。"),
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ]
        md = render_test_cases_markdown([], optimized_tree=tree)
        assert "## 系统已部署测试版本" in md
        assert "### 用户已登录系统" in md
        assert "#### 进入 `Create Ad Group` 页面" in md
        assert "##### 定位 `optimize goal` 区域" in md
        assert "- `optimize goal` 字段在创建阶段显式可见。" in md
        assert "- 用户可主动选择 `optimize goal`。" in md
        assert "[TC-" not in md
        assert "Checkpoint" not in md
        assert "前置条件" not in md
        assert "步骤" not in md

    def test_multiple_groups(self) -> None:
        tree = [
            _group_node("条件A", [_expected_leaf("结果A")]),
            _group_node("条件B", [_expected_leaf("结果B")]),
        ]
        md = render_test_cases_markdown([], optimized_tree=tree)
        assert "## 条件A" in md
        assert "## 条件B" in md

    def test_root_node_renders_children_only(self) -> None:
        """Root node is transparent — only its children appear."""
        root = ChecklistNode(
            node_id="root",
            title="Root",
            node_type="root",
            children=[_group_node("子路径", [_expected_leaf("子结果")])],
        )
        md = render_test_cases_markdown([], optimized_tree=[root])
        assert "子路径" in md
        assert "子结果" in md
