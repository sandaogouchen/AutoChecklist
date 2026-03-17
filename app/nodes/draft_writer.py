"""草稿编写节点。

调用 LLM 根据规划的测试场景和关联证据，生成初始版本的测试用例草稿。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.clients.llm import LLMClient
from app.domain.case_models import TestCase
from app.domain.state import CaseGenState

# LLM 系统提示词：指导模型生成结构化的手动 QA 测试用例
_SYSTEM_PROMPT = (
    "You write concise manual QA test cases as structured JSON. "
    "Always include ids, steps, expected_results, and evidence_refs."
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
        """根据场景和证据调用 LLM 生成测试用例草稿。

        为每个规划场景构造包含场景信息和证据摘录的 prompt，
        将所有场景拼接后一次性发送给 LLM，获取批量生成的用例。
        """
        scenarios = state["planned_scenarios"]
        evidence = state["mapped_evidence"]

        prompt_lines = [
            _format_scenario_prompt(index, scenario, evidence.get(scenario.title, []))
            for index, scenario in enumerate(scenarios, start=1)
        ]

        response = llm_client.generate_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt="\n\n".join(prompt_lines),
            response_model=DraftCaseCollection,
        )
        return {"draft_cases": response.test_cases}

    return draft_writer_node


def _format_scenario_prompt(index: int, scenario, evidence_refs: list) -> str:
    """格式化单个场景的 prompt 片段。

    将场景元信息（标题、类别、风险、理由）和关联证据
    组织为 LLM 易于理解的结构化文本。

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
