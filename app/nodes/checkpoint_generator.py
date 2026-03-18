"""检查点生成节点。

调用 LLM 将 ResearchFact 列表转换为显式的 Checkpoint 列表。
每个 fact 可以展开为 1 到 N 个 checkpoint，作为后续用例生成的输入。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.clients.llm import LLMClient
from app.domain.checkpoint_models import Checkpoint, generate_checkpoint_id
from app.domain.research_models import ResearchFact
from app.domain.state import CaseGenState

logger = logging.getLogger(__name__)

# LLM 系统提示词：指导模型从事实列表中生成可验证的测试检查点
_SYSTEM_PROMPT = (
    "You are a QA expert. Given a list of product facts extracted from a PRD, "
    "generate explicit, verifiable test checkpoints. Each fact may produce 1 or more checkpoints. "
    "Each checkpoint should be a specific, testable verification point. "
    "Return structured JSON with a 'checkpoints' array.\n\n"
    "【语言要求】\n"
    "- 所有 title、objective、preconditions 等描述字段必须使用中文输出。\n"
    "- 英文专有名词必须保留原文，包括但不限于：产品名、品牌名、UI 按钮文案、"
    "字段名、枚举值、接口名、类名、函数名、变量名、ID、URL、配置项。\n"
    "- 中英文混排时采用「中文动作 + 原文对象」形式，例如：验证 `SMS code` 过期后被拒绝。\n"
    "- category、risk、branch_hint 保留英文枚举值不翻译。"
    "\n\n"
    "【输出 JSON 结构约束（严格遵守，违反将导致解析失败）】\n"
    "你必须严格遵守以下 JSON schema。不要输出 schema 中未定义的字段。\n\n"
    "每个 checkpoint 对象仅允许以下字段：\n"
    "- title (string): 必填，检查点标题\n"
    "- objective (string): 可选，检查点目标\n"
    "- category (string): 可选，默认 \"functional\"\n"
    "- risk (string): 可选，默认 \"medium\"\n"
    "- branch_hint (string): 可选\n"
    "- fact_ids (array of string): 可选，关联的 fact ID 列表\n"
    "- preconditions (array of string): 可选，前置条件列表。"
    "【重要】此字段必须是字符串数组，每个前置条件是数组中的一个独立元素。"
    "绝对不要将所有前置条件合并为一个字符串。\n\n"
    "禁止出现的字段（输出这些字段会导致解析失败）：\n"
    "- steps\n"
    "- expected_result / expected_results\n"
    "- checkpoint_id（由系统自动生成，不要手动填写）\n\n"
    "正确示例：\n"
    '{"checkpoints": [{"title": "验证...", "preconditions": ["条件1", "条件2"], '
    '"fact_ids": ["FACT-001"]}]}\n\n'
    "错误示例（preconditions 为字符串）：\n"
    '{"checkpoints": [{"title": "验证...", "preconditions": "条件1。条件2。"}]}'
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

    @model_validator(mode="before")
    @classmethod
    def coerce_and_strip_extra_fields(cls, values: Any) -> Any:
        """在 Pydantic 校验之前自动修复 LLM 返回的常见格式问题。

        修复逻辑：
        1. 移除 LLM 可能错误输出的多余字段（steps、expected_result 等）
        2. 如果 preconditions 是字符串而非列表，按常见分隔符拆分为列表
        """
        if not isinstance(values, dict):
            return values

        # 移除 LLM 可能错误输出的多余字段
        _EXTRA_FIELDS = {"steps", "expected_result", "expected_results", "checkpoint_id"}
        for key in _EXTRA_FIELDS:
            values.pop(key, None)

        # 如果 preconditions 是字符串，自动拆分为列表
        preconditions = values.get("preconditions")
        if isinstance(preconditions, str):
            parts = re.split(r'[。\n；;]', preconditions)
            values["preconditions"] = [p.strip() for p in parts if p.strip()]

        return values


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

        # ---- 模板驱动生成支持：将模板维度注入 checkpoint 生成 prompt ----
        template_data = state.get("template")
        template_section = ""
        if template_data:
            try:
                from app.domain.template_models import ChecklistTemplate
                template_obj = ChecklistTemplate(**template_data)
                template_section = template_obj.format_for_checkpoint_prompt()
                if template_section:
                    prompt = prompt + "\n\n" + template_section
                    logger.info("已将模板维度注入 checkpoint 生成 prompt")
            except Exception:
                logger.warning("模板数据解析失败，降级为无模板模式", exc_info=True)

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
        "Ensure checkpoint titles are unique and descriptive.\n\n"
        "【输出语言】\n"
        "- checkpoint 的 title 和 objective 请使用中文书写。\n"
        "- preconditions 请使用中文书写，其中的专有名词保留英文原文。\n"
        "- category / risk / branch_hint 保留英文枚举值。"
        "\n\n"
        "【再次强调】preconditions 字段必须是字符串数组 (JSON array of strings)。\n"
        "如果有多个前置条件，请拆分为数组中的多个元素。\n"
        "如果只有一个前置条件，也要写成只包含一个元素的数组。\n"
        "不要输出 steps、expected_result、checkpoint_id 等未定义字段。"
    )

    return "\n".join(lines)
