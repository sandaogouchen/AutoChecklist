"""Markdown 渲染服务。

提供统一的 Markdown 渲染入口 ``render_test_cases_markdown``，
支持两种渲染模式：
- **扁平模式**（flat）：按用例逐条渲染，与原 ``_render_test_cases_markdown`` 一致
- **树形模式**（tree）：根据 ``optimized_tree``（ChecklistNode 树）渲染层级结构

本模块消除了原先在 ``platform_dispatcher.py`` 和 ``workflow_service.py``
中重复定义的 ``_render_test_cases_markdown`` 函数（DRY 修复）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.case_models import TestCase
    from app.domain.checklist_models import ChecklistNode

# Markdown 标题最大深度
_MAX_HEADING_DEPTH = 6


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------

def render_test_cases_markdown(
    test_cases: list[TestCase],
    optimized_tree: list[ChecklistNode] | None = None,
) -> str:
    """将测试用例渲染为 Markdown 文档。

    当 ``optimized_tree`` 非空时使用树形渲染，否则回退到扁平渲染。

    Args:
        test_cases: 测试用例列表（扁平模式使用）。
        optimized_tree: ChecklistNode 树（可选，树形模式使用）。

    Returns:
        Markdown 格式的字符串。
    """
    if optimized_tree:
        return _render_tree(optimized_tree)
    return flat_render(test_cases)


def flat_render(test_cases: list[TestCase]) -> str:
    """扁平模式渲染（向后兼容别名）。

    与原 ``_render_test_cases_markdown`` 实现完全一致，
    使用中文标题以保持与中文优先输出策略的一致性。
    """
    if not test_cases:
        return "# 生成的测试用例\n\n暂无测试用例。\n"

    lines = ["# 生成的测试用例", ""]
    for test_case in test_cases:
        lines.append(f"## {test_case.id} {test_case.title}")
        lines.append("")

        if test_case.checkpoint_id:
            lines.append(f"**Checkpoint:** {test_case.checkpoint_id}")
            lines.append("")

        lines.append("### 前置条件")
        lines.extend(
            [f"- {item}" for item in test_case.preconditions] or ["- 无"]
        )
        lines.append("")
        lines.append("### 步骤")
        lines.extend(
            [f"{i}. {step}" for i, step in enumerate(test_case.steps, start=1)]
            or ["1. 无"]
        )
        lines.append("")
        lines.append("### 预期结果")
        lines.extend(
            [f"- {item}" for item in test_case.expected_results] or ["- 无"]
        )
        lines.append("")

    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# 树形渲染
# ---------------------------------------------------------------------------

def _render_tree(tree: list[ChecklistNode]) -> str:
    """将 ChecklistNode 树渲染为层级 Markdown。"""
    lines = ["# 生成的测试用例（树形视图）", ""]
    for node in tree:
        _render_node(node, depth=2, lines=lines)
    return "\n".join(lines).strip() + "\n"


def _render_node(
    node: ChecklistNode,
    depth: int,
    lines: list[str],
) -> None:
    """递归渲染单个节点。"""
    if node.node_type == "group":
        _render_group_node(node, depth, lines)
    else:
        _render_case_node(node, depth, lines)


def _render_group_node(
    node: ChecklistNode,
    depth: int,
    lines: list[str],
) -> None:
    """渲染 group 节点。"""
    heading_level = min(depth, _MAX_HEADING_DEPTH)
    prefix = "#" * heading_level
    lines.append(f"{prefix} {node.title}")
    lines.append("")

    for child in node.children:
        _render_node(child, depth + 1, lines)


def _render_case_node(
    node: ChecklistNode,
    depth: int,
    lines: list[str],
) -> None:
    """渲染 case（叶子）节点。"""
    heading_level = min(depth, _MAX_HEADING_DEPTH)
    prefix = "#" * heading_level
    lines.append(f"{prefix} {node.test_case_ref} {node.title}")
    lines.append("")

    if node.checkpoint_id:
        lines.append(f"**Checkpoint:** {node.checkpoint_id}")
        lines.append("")

    if node.remaining_steps:
        lines.append(f"{'#' * min(heading_level + 1, _MAX_HEADING_DEPTH)} 步骤")
        lines.extend(
            f"{i}. {step}"
            for i, step in enumerate(node.remaining_steps, start=1)
        )
        lines.append("")

    if node.expected_results:
        lines.append(f"{'#' * min(heading_level + 1, _MAX_HEADING_DEPTH)} 预期结果")
        lines.extend(f"- {item}" for item in node.expected_results)
        lines.append("")
