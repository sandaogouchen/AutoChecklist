"""统一 Markdown 渲染器。

提供 ``render_test_cases_markdown()`` 作为唯一的测试用例 Markdown 渲染入口，
消除 platform_dispatcher 和 workflow_service 中的重复渲染函数（DRY 修复）。

两种渲染模式：
- 扁平模式（flat）：当 optimized_tree 为空时，与原 _render_test_cases_markdown 行为一致
- 树模式（tree）：按 optimized_tree 的分组结构渲染，前置条件提升为章节标题
"""

from __future__ import annotations

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode


def render_test_cases_markdown(
    test_cases: list[TestCase],
    optimized_tree: list[ChecklistNode] | None = None,
) -> str:
    """渲染测试用例为 Markdown 文档。

    Args:
        test_cases: 测试用例列表（扁平模式的数据源）。
        optimized_tree: 前置条件分组优化树（非空时启用树模式）。

    Returns:
        Markdown 格式的字符串。
    """
    if optimized_tree:
        return _render_tree(optimized_tree)
    return _flat_render(test_cases)


# ---------------------------------------------------------------------------
# 扁平模式：与原 _render_test_cases_markdown 完全一致
# ---------------------------------------------------------------------------

def _flat_render(test_cases: list[TestCase]) -> str:
    """扁平渲染，向后兼容原始格式。"""
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
# 树模式：按 optimized_tree 的分组结构渲染
# ---------------------------------------------------------------------------

def _render_tree(tree: list[ChecklistNode]) -> str:
    """按优化树结构渲染 Markdown。"""
    lines = ["# 生成的测试用例（优化分组）", ""]

    for node in tree:
        _render_node(node, lines)

    return "\n".join(lines).strip() + "\n"


def _render_node(node: ChecklistNode, lines: list[str]) -> None:
    """递归渲染单个节点。"""
    if node.node_type == "root":
        for child in node.children:
            _render_node(child, lines)
    elif node.node_type == "precondition_group":
        _render_group_node(node, lines)
    elif node.node_type == "case":
        _render_case_node(node, lines, heading_level=2)


def _render_group_node(node: ChecklistNode, lines: list[str]) -> None:
    """渲染 precondition_group 节点。"""
    lines.append(f"## 前置条件: {node.title}")
    lines.append("")

    if node.preconditions:
        for pc in node.preconditions:
            lines.append(f"- {pc}")
        lines.append("")

    for child in node.children:
        if child.node_type == "case":
            _render_case_node(child, lines, heading_level=3)
        else:
            _render_node(child, lines)


def _render_case_node(node: ChecklistNode, lines: list[str], heading_level: int = 3) -> None:
    """渲染 case 叶子节点。"""
    prefix = "#" * heading_level
    ref_label = node.test_case_ref or node.node_id
    lines.append(f"{prefix} {ref_label} {node.title}")
    lines.append("")

    if node.checkpoint_id:
        lines.append(f"**Checkpoint:** {node.checkpoint_id}")
        lines.append("")

    # 附加前置条件（分组后的额外条件）
    if node.preconditions:
        lines.append(f"{prefix}# 附加前置条件")
        lines.extend(f"- {item}" for item in node.preconditions)
        lines.append("")

    if node.steps:
        lines.append(f"{prefix}# 步骤")
        lines.extend(
            f"{i}. {step}" for i, step in enumerate(node.steps, start=1)
        )
        lines.append("")

    if node.expected_results:
        lines.append(f"{prefix}# 预期结果")
        lines.extend(f"- {item}" for item in node.expected_results)
        lines.append("")
