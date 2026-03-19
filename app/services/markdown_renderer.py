"""统一 Markdown 渲染器。

提供 ``render_test_cases_markdown()`` 作为唯一的测试用例 Markdown 渲染入口，
消除 platform_dispatcher 和 workflow_service 中的重复渲染函数（DRY 修复）。

三种渲染模式（优先级从高到低）：
- 模版模式（template）：当提供 template 参数时，按模版树骨架渲染
- 树模式（tree）：当 optimized_tree 非空时，按前置条件分组结构渲染
- 扁平模式（flat）：当 optimized_tree 为空时，与原 _render_test_cases_markdown 行为一致
"""

from __future__ import annotations

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.domain.template_models import (
    ProjectChecklistTemplateFile,
    ProjectChecklistTemplateNode,
)


def render_test_cases_markdown(
    test_cases: list[TestCase],
    optimized_tree: list[ChecklistNode] | None = None,
    template: ProjectChecklistTemplateFile | None = None,
) -> str:
    """渲染测试用例为 Markdown 文档。

    渲染优先级：template 模式 > tree 模式 > flat 模式。

    Args:
        test_cases: 测试用例列表（扁平模式的数据源）。
        optimized_tree: 前置条件分组优化树（非空时启用树模式）。
        template: 项目级 Checklist 模版（非 None 时启用模版模式）。

    Returns:
        Markdown 格式的字符串。
    """
    if template and template.nodes:
        return _render_template_tree(template, test_cases)
    if optimized_tree:
        return _render_tree(optimized_tree)
    return _flat_render(test_cases)


# ---------------------------------------------------------------------------
# 模版模式：按模版树骨架渲染
# ---------------------------------------------------------------------------

def _render_template_tree(
    template: ProjectChecklistTemplateFile,
    test_cases: list[TestCase],
) -> str:
    """按模版树骨架渲染 Markdown。

    以模版的节点结构为骨架，将用例按 template_leaf_id 分组到对应叶子下。
    没有匹配到模版叶子的用例归入"未分类"部分。
    """
    # 按 template_leaf_id 分组用例
    leaf_cases: dict[str, list[TestCase]] = {}
    unclassified: list[TestCase] = []

    for case in test_cases:
        if case.template_leaf_id:
            leaf_cases.setdefault(case.template_leaf_id, []).append(case)
        else:
            unclassified.append(case)

    title = template.metadata.name or "生成的测试用例（模版分类）"
    lines = [f"# {title}", ""]

    if template.metadata.description:
        lines.append(f"> {template.metadata.description}")
        lines.append("")

    for node in template.nodes:
        _render_template_node(node, lines, leaf_cases, heading_level=2)

    # 渲染未分类用例
    if unclassified:
        lines.append("## 未分类")
        lines.append("")
        for case in unclassified:
            _render_single_case(case, lines)

    return "\n".join(lines).strip() + "\n"


def _render_template_node(
    node: ProjectChecklistTemplateNode,
    lines: list[str],
    leaf_cases: dict[str, list[TestCase]],
    heading_level: int,
) -> None:
    """递归渲染模版树节点。

    - 非叶子节点：渲染为标题，递归处理子节点
    - 叶子节点：渲染为标题，下方列出绑定的用例
    """
    prefix = "#" * heading_level
    lines.append(f"{prefix} {node.title}")
    lines.append("")

    if node.children:
        # 非叶子节点，递归子节点
        for child in node.children:
            _render_template_node(
                child, lines, leaf_cases,
                heading_level=min(heading_level + 1, 6),
            )
    else:
        # 叶子节点，渲染绑定的用例
        cases = leaf_cases.get(node.id, [])
        if cases:
            for case in cases:
                _render_single_case(case, lines)
        else:
            lines.append("*暂无匹配的测试用例。*")
            lines.append("")


def _render_single_case(case: TestCase, lines: list[str]) -> str:
    """渲染单个测试用例。

    共享的单个用例渲染逻辑，供模版模式和扁平模式复用。
    低置信度匹配的用例会添加 :warning: 标记。
    """
    title_suffix = ""
    if case.template_match_low_confidence:
        title_suffix = " :warning: *低置信度匹配*"

    lines.append(f"### {case.id} {case.title}{title_suffix}")
    lines.append("")

    if case.checkpoint_id:
        lines.append(f"**Checkpoint:** {case.checkpoint_id}")
        lines.append("")

    if case.template_leaf_id:
        path_text = " > ".join(case.template_path_titles) if case.template_path_titles else case.template_leaf_id
        lines.append(f"**模版归类:** {path_text}")
        if case.template_match_low_confidence:
            lines.append(f"**匹配置信度:** {case.template_match_confidence:.2f} :warning:")
        lines.append("")

    lines.append("#### 前置条件")
    lines.extend(
        [f"- {item}" for item in case.preconditions] or ["- 无"]
    )
    lines.append("")
    lines.append("#### 步骤")
    lines.extend(
        [f"{i}. {step}" for i, step in enumerate(case.steps, start=1)]
        or ["1. 无"]
    )
    lines.append("")
    lines.append("#### 预期结果")
    lines.extend(
        [f"- {item}" for item in case.expected_results] or ["- 无"]
    )
    lines.append("")


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
        _render_node(node, lines, heading_level=2)

    return "\n".join(lines).strip() + "\n"


def _render_node(
    node: ChecklistNode,
    lines: list[str],
    heading_level: int,
) -> None:
    """递归渲染单个节点。"""
    if node.node_type == "root":
        for child in node.children:
            _render_node(child, lines, heading_level=heading_level)
    elif node.node_type in {"group", "precondition_group"}:
        _render_group_node(node, lines, heading_level=heading_level)
    elif node.node_type == "expected_result":
        _render_expected_result_node(node, lines)
    elif node.node_type == "case":
        _render_case_node(node, lines, heading_level=2)


def _render_group_node(
    node: ChecklistNode,
    lines: list[str],
    heading_level: int,
) -> None:
    """渲染共享逻辑组节点。"""
    if not node.hidden:
        prefix = "#" * heading_level
        title = (
            f"前置条件: {node.title}"
            if node.node_type == "precondition_group"
            else node.title
        )
        lines.append(f"{prefix} {title}")
        lines.append("")
        next_heading_level = heading_level + 1
    else:
        next_heading_level = heading_level

    for child in node.children:
        _render_node(child, lines, heading_level=next_heading_level)


def _render_expected_result_node(node: ChecklistNode, lines: list[str]) -> None:
    """渲染预期结果叶子。"""
    lines.append(f"- {node.title}")


def _render_case_node(node: ChecklistNode, lines: list[str], heading_level: int = 3) -> None:
    """渲染 case 叶子节点。"""
    prefix = "#" * heading_level
    ref_label = node.test_case_ref or node.node_id
    lines.append(f"{prefix} {ref_label} {node.title}")
    lines.append("")

    if node.checkpoint_id:
        lines.append(f"**Checkpoint:** {node.checkpoint_id}")
        lines.append("")

    # 树模式下保留用例完整前置条件
    if node.preconditions:
        lines.append(f"{prefix}# 前置条件")
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
