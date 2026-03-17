"""检查点生成节点。

调用 LLM 将 ResearchFact 列表转换为显式的 Checkpoint 列表。
每个 fact 可以展开为 1 到 N 个 checkpoint，作为后续用例生成的输入。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.clients.llm import LLMClient
from app.domain.checkpoint_models import Checkpoint, generate_checkpoint_id
from app.domain.research_models import ResearchFact
from app.domain.state import CaseGenState

# LLM 系统提示词：指导模型从事实列表中生成可验证的测试检查点
_SYSTEM_PROMPT = (
    "You are a QA expert. Given a list of product facts extracted from a PRD, "
    "generate explicit, verifiable test checkpoints. Each fact may produce 1 or more checkpoints. "
    "Each checkpoint should be a specific, testable verification point. "
    "Return structured JSON with a 'checkpoints' array."
)


class CheckpointDraft(BaseModel):
    """LLM 返回的单个 checkpoint 草稿。

    不包含 checkpoint_id，由后处理步骤基于 fact_ids 和 title 稳定生成。
    """

    title: str
    objective: str = ""
    category: str = "functional"
    risk: str = "medium"
    branch_hint: str = ""
    fact_ids: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)


class CheckpointDraftCollection(BaseModel):
    """LLM 返回的 checkpoint 草稿集合。"""

    checkpoints: list[CheckpointDraft] = Field(default_factory=list)


def build_checkpoint_generator_node(llm_client: LLMClient):
    """构建检查点生成节点的工厂函数。

    Args:
        llm_client: LLM 客户端实例，用于调用大模型生成 checkpoint。
    """

    def checkpoint_generator_node(state: CaseGenState) -> CaseGenState:
        """从研究事实中生成显式 checkpoint。

        流程：
        1. 从 research_output 中提取 facts
        2. 如果 facts 为空，则从 feature_topics / user_scenarios 合成基础 facts
        3. 构造 prompt 发送给 LLM
        4. 为每个返回的 checkpoint 生成稳定 ID
        5. 关联证据引用
        """
        research_output = state["research_output"]
        facts = research_output.facts

        # 向后兼容：如果 facts 为空，从现有字段合成基础 facts
        if not facts:
            facts = _synthesize_facts_from_legacy(research_output)

        if not facts:
            return {"checkpoints": []}

        prompt = _build_checkpoint_prompt(facts, state.get("language", "zh-CN"))

        response = llm_client.generate_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            response_model=CheckpointDraftCollection,
        )

        # 构建 fact_id → fact 的查找表，用于关联证据引用
        fact_lookup = {f.fact_id: f for f in facts if f.fact_id}

        checkpoints: list[Checkpoint] = []
        for draft in response.checkpoints:
            # 确保 fact_ids 不为空
            effective_fact_ids = draft.fact_ids or [facts[0].fact_id] if facts else []

            checkpoint_id = generate_checkpoint_id(effective_fact_ids, draft.title)

            # 从关联的 facts 中聚合证据引用
            evidence_refs = []
            for fid in effective_fact_ids:
                fact = fact_lookup.get(fid)
                if fact and fact.evidence_refs:
                    evidence_refs.extend(fact.evidence_refs)

            checkpoints.append(
                Checkpoint(
                    checkpoint_id=checkpoint_id,
                    title=draft.title,
                    objective=draft.objective,
                    category=draft.category,
                    risk=draft.risk,
                    branch_hint=draft.branch_hint,
                    fact_ids=effective_fact_ids,
                    evidence_refs=evidence_refs,
                    preconditions=draft.preconditions,
                    coverage_status="uncovered",
                )
            )

        return {"checkpoints": checkpoints}

    return checkpoint_generator_node


def _synthesize_facts_from_legacy(research_output) -> list[ResearchFact]:
    """从旧版 ResearchOutput 字段合成基础 facts。

    当 LLM 未返回结构化 facts 时，将 user_scenarios 和 feature_topics
    转换为 ResearchFact 对象，确保后续 checkpoint 生成流程可以继续。
    """
    facts: list[ResearchFact] = []
    index = 1

    for scenario in research_output.user_scenarios:
        if scenario.strip():
            facts.append(
                ResearchFact(
                    fact_id=f"FACT-{index:03d}",
                    description=scenario.strip(),
                    category="behavior",
                )
            )
            index += 1

    for topic in research_output.feature_topics:
        if topic.strip():
            facts.append(
                ResearchFact(
                    fact_id=f"FACT-{index:03d}",
                    description=f"Feature: {topic.strip()}",
                    category="requirement",
                )
            )
            index += 1

    for constraint in research_output.constraints:
        if constraint.strip():
            facts.append(
                ResearchFact(
                    fact_id=f"FACT-{index:03d}",
                    description=constraint.strip(),
                    category="constraint",
                )
            )
            index += 1

    return facts


def _build_checkpoint_prompt(facts: list[ResearchFact], language: str) -> str:
    """构造 checkpoint 生成的用户 prompt。

    将所有 facts 格式化为结构化文本，指导 LLM 生成对应的 checkpoints。
    """
    lines = [
        f"Language: {language}",
        f"Total facts: {len(facts)}",
        "",
        "Facts to convert into test checkpoints:",
        "",
    ]

    for fact in facts:
        lines.append(f"- [{fact.fact_id}] ({fact.category}) {fact.description}")
        if fact.source_section:
            lines.append(f"  Source: {fact.source_section}")

    lines.append("")
    lines.append(
        "For each fact, generate 1 or more specific, verifiable test checkpoints. "
        "Include the source fact_ids in each checkpoint. "
        "Ensure checkpoint titles are unique and descriptive."
    )

    return "\n".join(lines)
