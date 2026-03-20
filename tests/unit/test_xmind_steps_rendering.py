"""Unit tests for XMind steps rendering.

Covers:
1. case node WITH steps  -> XMindNode contains a "步骤" child node
2. case node with EMPTY steps -> XMindNode does NOT contain a "步骤" child node
3. Tree-mode full rendering: group -> case (with steps) produces correct hierarchy
"""

from __future__ import annotations

import pytest

from app.domain.checklist_models import ChecklistNode
from app.services.xmind_payload_builder import XMindPayloadBuilder, XMindNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _child_titles(xnode: XMindNode) -> list[str]:
    """Return the titles of all immediate children of *xnode*."""
    return [c.title for c in xnode.children]


def _find_child(xnode: XMindNode, title: str) -> XMindNode | None:
    """Find the first immediate child of *xnode* whose title matches *title*."""
    for c in xnode.children:
        if c.title == title:
            return c
    return None


# ---------------------------------------------------------------------------
# Test 1: case node WITH steps -> "步骤" child present
# ---------------------------------------------------------------------------


class TestCaseNodeWithSteps:
    """When a case node has non-empty steps, the rendered XMindNode must
    contain a child titled "步骤" with one sub-node per step line."""

    def test_steps_child_exists(self):
        case_node = ChecklistNode(
            id="c1",
            display_text="验证登录功能",
            node_type="case",
            steps="1. 打开登录页面\n2. 输入用户名和密码\n3. 点击登录按钮",
        )

        builder = XMindPayloadBuilder()
        result = builder.build([case_node])

        assert len(result) == 1
        xnode = result[0]
        assert xnode.title == "验证登录功能"

        steps_child = _find_child(xnode, "步骤")
        assert steps_child is not None, (
            "'步骤' child node should exist when steps is non-empty"
        )

    def test_steps_sub_nodes_match_lines(self):
        case_node = ChecklistNode(
            id="c1",
            display_text="验证登录功能",
            node_type="case",
            steps="打开登录页面\n输入用户名\n点击登录",
        )

        builder = XMindPayloadBuilder()
        xnode = builder.build([case_node])[0]

        steps_child = _find_child(xnode, "步骤")
        assert steps_child is not None
        assert len(steps_child.children) == 3
        assert steps_child.children[0].title == "打开登录页面"
        assert steps_child.children[1].title == "输入用户名"
        assert steps_child.children[2].title == "点击登录"

    def test_single_step_line(self):
        case_node = ChecklistNode(
            id="c1",
            display_text="单步操作",
            node_type="case",
            steps="点击确认按钮",
        )

        builder = XMindPayloadBuilder()
        xnode = builder.build([case_node])[0]

        steps_child = _find_child(xnode, "步骤")
        assert steps_child is not None
        assert len(steps_child.children) == 1
        assert steps_child.children[0].title == "点击确认按钮"

    def test_blank_lines_in_steps_are_ignored(self):
        case_node = ChecklistNode(
            id="c1",
            display_text="含空行步骤",
            node_type="case",
            steps="步骤A\n\n\n步骤B\n",
        )

        builder = XMindPayloadBuilder()
        xnode = builder.build([case_node])[0]

        steps_child = _find_child(xnode, "步骤")
        assert steps_child is not None
        assert len(steps_child.children) == 2
        assert steps_child.children[0].title == "步骤A"
        assert steps_child.children[1].title == "步骤B"


# ---------------------------------------------------------------------------
# Test 2: case node with EMPTY steps -> no "步骤" child
# ---------------------------------------------------------------------------


class TestCaseNodeWithoutSteps:
    """When a case node has empty or whitespace-only steps, no "步骤"
    child should be generated."""

    def test_empty_string_steps(self):
        case_node = ChecklistNode(
            id="c1",
            display_text="无步骤用例",
            node_type="case",
            steps="",
        )

        builder = XMindPayloadBuilder()
        xnode = builder.build([case_node])[0]

        steps_child = _find_child(xnode, "步骤")
        assert steps_child is None, (
            "'步骤' child node should NOT exist when steps is empty"
        )

    def test_whitespace_only_steps(self):
        case_node = ChecklistNode(
            id="c1",
            display_text="空白步骤用例",
            node_type="case",
            steps="   \n  \n   ",
        )

        builder = XMindPayloadBuilder()
        xnode = builder.build([case_node])[0]

        steps_child = _find_child(xnode, "步骤")
        assert steps_child is None

    def test_no_steps_attribute_default(self):
        """ChecklistNode defaults steps to '' -- should also produce no child."""
        case_node = ChecklistNode(
            id="c1",
            display_text="默认步骤用例",
            node_type="case",
        )

        builder = XMindPayloadBuilder()
        xnode = builder.build([case_node])[0]

        steps_child = _find_child(xnode, "步骤")
        assert steps_child is None


# ---------------------------------------------------------------------------
# Test 3: Tree mode -- group -> case with steps
# ---------------------------------------------------------------------------


class TestTreeModeRendering:
    """Full hierarchy: group node containing a case node with steps.
    The XMind tree should mirror the structure and include 步骤 at the
    case leaf level."""

    def test_group_case_hierarchy(self):
        case_node = ChecklistNode(
            id="case_1",
            display_text="验证提交功能",
            node_type="case",
            steps="1. 填写表单\n2. 点击提交",
            expected_results="提交成功提示",
            priority="P0",
            category="功能测试",
        )
        group_node = ChecklistNode(
            id="group_1",
            display_text="进入 `Submit` 页面",
            node_type="group",
            children=[case_node],
        )

        builder = XMindPayloadBuilder()
        result = builder.build([group_node])

        assert len(result) == 1
        xgroup = result[0]
        assert xgroup.title == "进入 `Submit` 页面"

        # Group should have exactly one child: the case
        assert len(xgroup.children) == 1
        xcase = xgroup.children[0]
        assert xcase.title == "验证提交功能"

        # Case should have detail children
        child_titles = _child_titles(xcase)
        assert "步骤" in child_titles
        assert "预期结果" in child_titles
        assert "优先级: P0" in child_titles
        assert "类型: 功能测试" in child_titles

        # Verify steps content
        steps_child = _find_child(xcase, "步骤")
        assert steps_child is not None
        assert len(steps_child.children) == 2
        assert steps_child.children[0].title == "1. 填写表单"
        assert steps_child.children[1].title == "2. 点击提交"

    def test_deeply_nested_group_case(self):
        """group -> group -> case should all render correctly."""
        case_node = ChecklistNode(
            id="deep_case",
            display_text="验证深层用例",
            node_type="case",
            steps="执行操作X\n验证结果Y",
        )
        inner_group = ChecklistNode(
            id="inner",
            display_text="配置 `Settings` 参数",
            node_type="group",
            children=[case_node],
        )
        outer_group = ChecklistNode(
            id="outer",
            display_text="进入 `Dashboard` 页面",
            node_type="group",
            children=[inner_group],
        )

        builder = XMindPayloadBuilder()
        result = builder.build([outer_group])

        # Navigate: outer -> inner -> case
        xouter = result[0]
        assert xouter.title == "进入 `Dashboard` 页面"
        assert len(xouter.children) == 1

        xinner = xouter.children[0]
        assert xinner.title == "配置 `Settings` 参数"
        assert len(xinner.children) == 1

        xcase = xinner.children[0]
        assert xcase.title == "验证深层用例"

        steps_child = _find_child(xcase, "步骤")
        assert steps_child is not None
        assert len(steps_child.children) == 2

    def test_group_node_without_case_children(self):
        """A group node with no case children should have no 步骤."""
        group_node = ChecklistNode(
            id="g1",
            display_text="空分组",
            node_type="group",
            children=[],
        )

        builder = XMindPayloadBuilder()
        result = builder.build([group_node])

        xgroup = result[0]
        assert xgroup.title == "空分组"
        steps_child = _find_child(xgroup, "步骤")
        assert steps_child is None

    def test_multiple_cases_under_group(self):
        """Group with two cases: one with steps, one without."""
        case_with = ChecklistNode(
            id="cw",
            display_text="有步骤用例",
            node_type="case",
            steps="做A\n做B",
        )
        case_without = ChecklistNode(
            id="cwo",
            display_text="无步骤用例",
            node_type="case",
            steps="",
        )
        group = ChecklistNode(
            id="g1",
            display_text="测试分组",
            node_type="group",
            children=[case_with, case_without],
        )

        builder = XMindPayloadBuilder()
        result = builder.build([group])

        xgroup = result[0]
        assert len(xgroup.children) == 2

        # First case has steps
        assert _find_child(xgroup.children[0], "步骤") is not None
        assert len(_find_child(xgroup.children[0], "步骤").children) == 2

        # Second case has no steps
        assert _find_child(xgroup.children[1], "步骤") is None
