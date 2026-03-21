"""统一 Markdown 渲染器。

三种渲染模式（优先级从高到低）：
- 模版模式（template）：当提供 template 参数时，按模版树骨架渲染
- 树模式（tree）：当 optimized_tree 非空时，按前置条件分组结构渲染
- 扁平模式（flat）：当 optimized_tree 为空时，与原渲染行为一致

新增 source 标签支持：强制模版节点标题后追加 [模版]，overflow 节点追加 [待分配]。
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
    enable_source_labels: bool = True,
) -> str:
    """渲染测试用例为 Markdown 文档。"""
    if template and template.nodes:
        return _render_template_tree(template, test_cases)
    if optimized_tree:
        return _render_tree(optimized_tree, enable_source_labels=enable_source_labels)
    return _flat_render(test_cases)


# ---------------------------------------------------------------------------
# 模版模式
# ---------------------------------------------------------------------------

def _render_template_tree(
    template: ProjectChecklistTemplateFile,
    test_cases: list[TestCase],
) -> str:
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
    prefix = "#" * heading_level
    lines.append(f"{prefix} {node.title}")
    lines.append("")

    if node.children:
        for child in node.children:
            _render_template_node(
                child, lines, leaf_cases,
                heading_level=min(heading_level + 1, 6),
            )
    else:
        cases = leaf_cases.get(node.id, [])
        if cases:
            for case in cases:
                _render_single_case(case, lines)
        else:
            lines.append("*暂无匹配的测试用例。*")
            lines.append("")


def _render_single_case(case: TestCase, lines: list[str]) -> str:
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
# 扁平模式
# ---------------------------------------------------------------------------

def _flat_render(test_cases: list[TestCase]) -> str:
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
# 树模式（新增 source 标签支持）
# ---------------------------------------------------------------------------

def _render_tree(
    tree: list[ChecklistNode],
    enable_source_labels: bool = True,
) -> str:
    lines = ["# 生成的测试用例（优化分组）", ""]

    for node in tree:
        _render_node(node, lines, heading_level=2, enable_source_labels=enable_source_labels)

    return "\n".join(lines).strip() + "\n"


def _render_node(
    node: ChecklistNode,
    lines: list[str],
    heading_level: int,
    enable_source_labels: bool = True,
) -> None:
    if node.node_type == "root":
        for child in node.children:
            _render_node(child, lines, heading_level=heading_level, enable_source_labels=enable_source_labels)
    elif node.node_type in {"group", "precondition_group"}:
        _render_group_node(node, lines, heading_level=heading_level, enable_source_labels=enable_source_labels)
    elif node.node_type == "expected_result":
        _render_expected_result_node(node, lines)
    elif node.node_type == "case":
        _render_case_node(node, lines, heading_level=2)


def _render_group_node(
    node: ChecklistNode,
    lines: list[str],
    heading_level: int,
    enable_source_labels: bool = True,
) -> None:
    if not node.hidden:
        prefix = "#" * heading_level
        title = (
            f"前置条件: {node.title}"
            if node.node_type == "precondition_group"
            else node.title
        )

        # 新增：source 标签
        if enable_source_labels:
            if node.source == "template":
                title = f"{title} [模版]"
            elif node.source == "overflow":
                title = f"{title} [待分配]"

        lines.append(f"{prefix} {title}")
        lines.append("")
        next_heading_level = heading_level + 1
    else:
        next_heading_level = heading_level

    for child in node.children:
        _render_node(child, lines, heading_level=next_heading_level, enable_source_labels=enable_source_labels)


def _render_expected_result_node(node: ChecklistNode, lines: list[str]) -> None:
    lines.append(f"- {node.title}")


def _render_case_node(node: ChecklistNode, lines: list[str], heading_level: int = 3) -> None:
    prefix = "#" * heading_level
    ref_label = node.test_case_ref or node.node_id
    lines.append(f"{prefix} {ref_label} {node.title}")
    lines.append("")

    if node.checkpoint_id:
        lines.append(f"**Checkpoint:** {node.checkpoint_id}")
        lines.append("")

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
        lines.append(f"{prefix}#预期结果")
        lines.extend(f"- {item}" for item in node.expected_results)
        lines.append("")
