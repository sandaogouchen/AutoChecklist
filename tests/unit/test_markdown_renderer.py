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
    preconditions: list[str],
    case_children: list[ChecklistNode],
) -> ChecklistNode:
    """Helper to build a precondition_group node."""
    return ChecklistNode(
        node_id=f"GRP-test",
        title=title,
        node_type="precondition_group",
        children=case_children,
        preconditions=preconditions,
    )


def _case_node(
    tc_id: str,
    title: str = "测试",
    preconditions: list[str] | None = None,
    steps: list[str] | None = None,
    expected_results: list[str] | None = None,
    checkpoint_id: str = "",
) -> ChecklistNode:
    """Helper to build a case node."""
    return ChecklistNode(
        node_id=f"CASE-{tc_id}",
        title=title,
        node_type="case",
        test_case_ref=tc_id,
        preconditions=preconditions or [],
        steps=steps or ["步骤1"],
        expected_results=expected_results or ["预期1"],
        checkpoint_id=checkpoint_id,
    )


class TestTreeRender:
    """Tests for tree-mode rendering."""

    def test_single_group(self) -> None:
        tree = [
            _group_node(
                "用户已登录",
                ["用户已登录"],
                [_case_node("TC-001"), _case_node("TC-002")],
            )
        ]
        md = render_test_cases_markdown([], optimized_tree=tree)
        assert "## 前置条件: 用户已登录" in md
        assert "TC-001" in md
        assert "TC-002" in md

    def test_group_preconditions_rendered(self) -> None:
        tree = [
            _group_node(
                "登录 → 网络正常",
                ["登录", "网络正常"],
                [_case_node("TC-001")],
            )
        ]
        md = render_test_cases_markdown([], optimized_tree=tree)
        assert "- 登录" in md
        assert "- 网络正常" in md

    def test_additional_preconditions(self) -> None:
        tree = [
            _group_node(
                "登录",
                ["登录"],
                [_case_node("TC-001", preconditions=["VPN连接"])],
            )
        ]
        md = render_test_cases_markdown([], optimized_tree=tree)
        assert "附加前置条件" in md
        assert "- VPN连接" in md

    def test_multiple_groups(self) -> None:
        tree = [
            _group_node("条件A", ["条件A"], [_case_node("TC-001")]),
            _group_node("条件B", ["条件B"], [_case_node("TC-002")]),
        ]
        md = render_test_cases_markdown([], optimized_tree=tree)
        assert "## 前置条件: 条件A" in md
        assert "## 前置条件: 条件B" in md

    def test_steps_and_expected_results(self) -> None:
        tree = [
            _group_node(
                "登录",
                ["登录"],
                [
                    _case_node(
                        "TC-001",
                        steps=["打开页面", "点击按钮"],
                        expected_results=["页面跳转", "显示成功"],
                    )
                ],
            )
        ]
        md = render_test_cases_markdown([], optimized_tree=tree)
        assert "1. 打开页面" in md
        assert "2. 点击按钮" in md
        assert "- 页面跳转" in md
        assert "- 显示成功" in md

    def test_root_node_renders_children_only(self) -> None:
        """Root node is transparent — only its children appear."""
        root = ChecklistNode(
            node_id="root",
            title="Root",
            node_type="root",
            children=[_case_node("TC-001", title="子用例")],
        )
        md = render_test_cases_markdown([], optimized_tree=[root])
        assert "子用例" in md

    def test_case_with_checkpoint_id(self) -> None:
        tree = [
            _group_node(
                "登录",
                ["登录"],
                [_case_node("TC-001", checkpoint_id="CP-xyz")],
            )
        ]
        md = render_test_cases_markdown([], optimized_tree=tree)
        assert "**Checkpoint:** CP-xyz" in md
