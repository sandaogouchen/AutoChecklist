"""草稿编写节点。

调用 LLM 根据 checkpoint 列表和关联证据，生成初始版本的测试用例草稿。
每个生成的测试用例会携带对应的 checkpoint_id，建立可追溯的链路。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.clients.llm import LLMClient
from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint
from app.domain.state import CaseGenState

# LLM 系统提示词：指导模型基于 checkpoint 生成结构化的手动 QA 测试用例
_SYSTEM_PROMPT = (
    "You write concise manual QA test cases as structured JSON. "
    "Each test case MUST include an id, title, steps, expected_results, evidence_refs, "
    "and a checkpoint_id field that references the checkpoint it was generated from. "
    "Always include ids, steps, expected_results, and evidence_refs.\n\n"
    "【语言要求】\n"
    "- title 字段使用中文书写，简要概括测试目标。\n"
    "- steps 字段使用中文书写操作步骤，其中 UI 元素、按钮文案、字段名等"
    "专有名词保留英文原文并用反引号包裹，例如：点击 `Submit` 按钮。\n"
    "- expected_results 字段使用中文书写预期结果。\n"
    "- preconditions 字段使用中文书写前置条件。\n"
    "- id、priority、category、checkpoint_id 等标识字段保留英文。\n"
    "- evidence_refs 中的 section_title 和 excerpt 保留原文不翻译。"
)


class DraftCaseCollection(BaseModel):
    """LLM 返回的测试用例草稿集合。

    作为 ``generate_structured`` 的 ``response_model``，
    用于将 LLM 的 JSON 输出反序列化为类型安全的对象。
    """

    test_cases: list[TestCase] = Field(default_factory=list)


def build_draft_writer_node(llm_client: LLMClient):
    """构建草稿编写节点的工厂函数。

    Args:
        llm_client: LLM 客户端实例。
    """

    def draft_writer_node(state: CaseGenState) -> CaseGenState:
        """根据 checkpoint 和证据调用 LLM 生成测试用例草稿。

        优先使用 checkpoints 作为生成输入；如果 checkpoints 为空，
        则回退到使用 planned_scenarios（向后兼容）。
        """
        checkpoints = state.get("checkpoints", [])

        if checkpoints:
            prompt_lines = [
                _format_checkpoint_prompt(index, cp)
                for index, cp in enumerate(checkpoints, start=1)
            ]
        else:
            # 向后兼容：使用 scenarios + evidence
            scenarios = state.get("planned_scenarios", [])
            evidence = state.get("mapped_evidence", {})
            prompt_lines = [
                _format_scenario_prompt(index, scenario, evidence.get(scenario.title, []))
                for index, scenario in enumerate(scenarios, start=1)
            ]

        # ---- 项目上下文：追加 checklist 模板约束 ----
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


def _format_checkpoint_prompt(index: int, checkpoint: Checkpoint) -> str:
    """格式化单个 checkpoint 的 prompt 片段。

    将 checkpoint 元信息（ID、标题、目标、类别、风险、前置条件）和关联证据
    组织为 LLM 易于理解的结构化文本。

    Args:
        index: checkpoint 序号（从 1 开始）。
        checkpoint: 检查点对象。
    """
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


def _format_scenario_prompt(index: int, scenario, evidence_refs: list) -> str:
    """格式化单个场景的 prompt 片段（向后兼容）。

    Args:
        index: 场景序号（从 1 开始）。
        scenario: 规划的测试场景对象。
        evidence_refs: 该场景关联的证据引用列表。
    """
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
