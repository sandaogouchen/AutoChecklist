"""草稿编写节点。

调用 LLM 根据 checkpoint 列表和关联证据，生成初始版本的测试用例草稿。
每个生成的测试用例会携带对应的 checkpoint_id，建立可追溯的链路。

变更：在 _SYSTEM_PROMPT 中新增前置条件编写规范（5 条规则），
引导 LLM 生成高质量、可分组的 preconditions。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.clients.llm import LLMClient
from app.domain.checklist_models import CanonicalOutlineNode, CheckpointPathMapping
from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint
from app.domain.state import CaseGenState

# LLM 系统提示词：指导模型基于 checkpoint 生成结构化的手动 QA 测试用例
_SYSTEM_PROMPT = (
    "You write concise manual QA test cases as structured JSON. "
    "Each test case MUST include an id, title, steps, expected_results, evidence_refs, "
    "and a checkpoint_id field that references the checkpoint it was generated from. "
    "Always include ids, steps, expected_results, and evidence_refs.\n"
    "Fixed hierarchy paths are supplied by the system.\n"
    "Do not restate or merge that hierarchy into testcase titles, preconditions, "
    "or summary headings.\n"
    "Do not restate merged parent phrases such as `处于 CBO 的 Ad group 配置场景`.\n"
    "Generate only the leaf testcase title, concrete steps, and expected_results "
    "under the supplied path.\n\n"
    "【语言要求】\n"
    "- title 字段使用中文书写，简要概括测试目标。\n"
    "- steps 字段使用中文书写操作步骤，其中 UI 元素、按钮文案、字段名等"
    "专有名词保留英文原文并用反引号包裹，例如：点击 `Submit` 按钮。\n"
    "- expected_results 字段使用中文书写预期结果。\n"
    "- preconditions 字段使用中文书写前置条件。\n"
    "- id、priority、category、checkpoint_id 等标识字段保留英文。\n"
    "- evidence_refs 中的 section_title 和 excerpt 保留原文不翻译。\n\n"
    "【前置条件编写规范】\n"
    "preconditions 字段是后续自动分组的关键依据，请严格遵守以下规则：\n"
    "1. 表述规范化：使用统一的句式结构，同一含义只用一种表达方式。"
    "例如：始终使用「用户已登录系统」而非混用「登录状态下」「已完成登录」。\n"
    "2. 层级化描述：前置条件按逻辑顺序排列，从环境/系统状态 → 用户状态 → 数据准备 → 页面/入口。"
    "例如：[\"系统已部署 v2.0 版本\", \"用户已登录管理后台\", \"已创建至少一条测试数据\"]。\n"
    "3. 原子性：每条前置条件仅描述一个独立的准备动作或状态，不要合并多个条件到一句话中。"
    "错误示例：「用户已登录且进入设置页面」→ 应拆分为两条。\n"
    "4. 充分性：列出执行测试步骤前所需的全部准备条件，不遗漏隐含的前置状态。\n"
    "5. 复用意识：当多个测试用例共享相同的前置环境时，确保它们的 preconditions 完全一致"
    "（字面相同），以便自动归组。不要因措辞差异导致相同含义的条件被拆分到不同组。"
)


class DraftCaseCollection(BaseModel):
    """LLM 返回的测试用例草稿集合。"""

    test_cases: list[TestCase] = Field(default_factory=list)


def build_draft_writer_node(llm_client: LLMClient):
    """构建草稿编写节点的工厂函数。"""

    def draft_writer_node(state: CaseGenState) -> CaseGenState:
        """根据 checkpoint 和证据调用 LLM 生成测试用例草稿。"""
        checkpoints = state.get("checkpoints", [])
        checkpoint_paths = state.get("checkpoint_paths", [])
        canonical_outline_nodes = state.get("canonical_outline_nodes", [])

        if checkpoints:
            prompt_lines = [
                _format_checkpoint_prompt(
                    index,
                    cp,
                    checkpoint_paths,
                    canonical_outline_nodes,
                )
                for index, cp in enumerate(checkpoints, start=1)
            ]
        else:
            scenarios = state.get("planned_scenarios", [])
            evidence = state.get("mapped_evidence", {})
            prompt_lines = [
                _format_scenario_prompt(index, scenario, evidence.get(scenario.title, []))
                for index, scenario in enumerate(scenarios, start=1)
            ]

        project_context_summary = state.get("project_context_summary", "")
        if project_context_summary:
            prompt_lines.insert(0, f"[Project Checklist Constraints]\n{project_context_summary}\n")

        if not prompt_lines:
            return {"draft_cases": []}

        response = llm_client.generate_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt="\n\n".join(prompt_lines),
            response_model=DraftCaseCollection,
        )
        return {"draft_cases": response.test_cases}

    return draft_writer_node


def _format_checkpoint_prompt(
    index: int,
    checkpoint: Checkpoint,
    checkpoint_paths: list[CheckpointPathMapping],
    canonical_outline_nodes: list[CanonicalOutlineNode],
) -> str:
    """格式化单个 checkpoint 的 prompt 片段。"""
    lines = [
        f"Checkpoint {index}: {checkpoint.title}",
        f"Checkpoint ID: {checkpoint.checkpoint_id}",
        f"Objective: {checkpoint.objective}",
        f"Category: {checkpoint.category}",
        f"Risk: {checkpoint.risk}",
    ]

    if checkpoint.branch_hint:
        lines.append(f"Branch hint: {checkpoint.branch_hint}")

    if checkpoint.preconditions:
        lines.append("Preconditions:")
        lines.extend(f"- {pc}" for pc in checkpoint.preconditions)

    path_context = _resolve_path_context(
        checkpoint.checkpoint_id,
        checkpoint_paths,
        canonical_outline_nodes,
    )
    if path_context:
        lines.append("Fixed hierarchy path:")
        lines.extend(f"- {item}" for item in path_context)
        lines.append(
            "The hierarchy above already exists in optimized_tree. "
            "Generate only the leaf testcase content below this path."
        )

    lines.append(f"Source facts: {', '.join(checkpoint.fact_ids)}")

    if checkpoint.evidence_refs:
        lines.append("Evidence:")
        lines.extend(
            f"- {ref.section_title} ({ref.line_start}-{ref.line_end}): {ref.excerpt}"
            for ref in checkpoint.evidence_refs
        )

    lines.append(
        f"\nGenerate test case(s) for this checkpoint. Set checkpoint_id to '{checkpoint.checkpoint_id}'."
    )

    return "\n".join(lines)


def _resolve_path_context(
    checkpoint_id: str,
    checkpoint_paths: list[CheckpointPathMapping],
    canonical_outline_nodes: list[CanonicalOutlineNode],
) -> list[str]:
    path_mapping = next(
        (item for item in checkpoint_paths if item.checkpoint_id == checkpoint_id),
        None,
    )
    if path_mapping is None:
        return []

    node_lookup = {node.node_id: node for node in canonical_outline_nodes}
    resolved: list[str] = []
    for node_id in path_mapping.path_node_ids:
        node = node_lookup.get(node_id)
        if node is None or node.visibility == "hidden":
            continue
        resolved.append(node.display_text)

    return resolved


def _format_scenario_prompt(index: int, scenario, evidence_refs: list) -> str:
    """格式化单个场景的 prompt 片段（向后兼容）。"""
    lines = [
        f"Scenario {index}: {scenario.title}",
        f"Category: {scenario.category}",
        f"Risk: {scenario.risk}",
        f"Rationale: {scenario.rationale}",
        "Evidence:",
    ]
    lines.extend(
        f"- {ref.section_title} ({ref.line_start}-{ref.line_end}): {ref.excerpt}"
        for ref in evidence_refs
    )
    return "\n".join(lines)
