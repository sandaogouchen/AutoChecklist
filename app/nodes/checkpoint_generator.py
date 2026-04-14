"""检查点生成节点。

调用 LLM 将 ResearchFact 列表转换为显式的 Checkpoint 列表。
每个 fact 可以展开为 1 到 N 个 checkpoint，作为后续用例生成的输入。

变更：新增模版绑定能力，当 template_leaf_targets 非空时，
在 prompt 中注入模版叶子列表，引导 LLM 将每个 checkpoint 归类到最匹配的叶子节点，
并在后处理阶段校验、回填模版路径信息。

变更：新增 XMind 参考注入能力，当 state 中存在 xmind_reference_summary 时，
将参考 Checklist 的覆盖维度和组织方式注入 prompt，引导 LLM 生成结构和风格一致的检查点。

变更：新增 MR 代码事实注入能力，当 state 中存在 mr_code_facts 时，
将代码级别的事实一同注入 checkpoint 生成 prompt，使生成的检查点
同时覆盖 PRD 和代码变更维度。
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
from app.domain.template_models import TemplateLeafTarget
from app.services.prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)
_PROMPT_LOADER = get_prompt_loader()

# 低置信度阈值：低于此值的模版匹配将被标记为低置信度
_LOW_CONFIDENCE_THRESHOLD = 0.6

# LLM 系统提示词：指导模型从事实列表中生成可验证的测试检查点
_SYSTEM_PROMPT = _PROMPT_LOADER.load("nodes/checkpoint_generator/system.md")


class CheckpointDraft(BaseModel):
    """​LLM 返回的单个 checkpoint 草稿。

    不包含 checkpoint_id，由后处理步骤基于 fact_ids 和 title 稳定生成。
    """

    title: str
    objective: str = ""
    category: str = "functional"
    risk: str = "medium"
    branch_hint: str = ""
    fact_ids: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)

    # ---- 模版绑定字段（由 LLM 填写） ----
    template_leaf_id: str = ""
    template_match_confidence: float = 0.0
    template_match_low_confidence: bool = False
    template_match_reason: str = ""

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


def _build_xmind_reference_prompt(xmind_reference_summary) -> str:
    """Build XMind reference prompt section for checkpoint generation.

    When an XMind reference summary is available, returns a formatted
    prompt section that guides the LLM to align coverage dimensions.
    """
    if xmind_reference_summary is None:
        return ""
    if hasattr(xmind_reference_summary, "formatted_summary"):
        formatted = xmind_reference_summary.formatted_summary
    elif isinstance(xmind_reference_summary, dict):
        formatted = xmind_reference_summary.get("formatted_summary", "")
    else:
        return ""
    if not formatted:
        return ""
    return _PROMPT_LOADER.render(
        "nodes/checkpoint_generator/xmind_reference_user.md",
        formatted=formatted,
    )


def _build_mr_code_facts_prompt(mr_code_facts: list) -> str:
    """构建 MR 代码事实的 prompt 片段。

    当 state 中存在 mr_code_facts 时，将代码级别的事实格式化为
    prompt 文本，注入到 checkpoint 生成流程中，使生成的检查点
    同时覆盖代码变更维度。

    Args:
        mr_code_facts: MR 代码事实列表，每个元素可能是 MRCodeFact 对象或 dict。

    Returns:
        prompt 文本片段，若无事实则返回空字符串。
    """
    if not mr_code_facts:
        return ""

    lines: list[str] = []

    for i, fact in enumerate(mr_code_facts, start=1):
        if hasattr(fact, "description"):
            desc = fact.description
            file_path = getattr(fact, "source_file", getattr(fact, "file_path", ""))
            change_type = getattr(fact, "fact_type", getattr(fact, "change_type", ""))
            fact_id = getattr(fact, "fact_id", f"MR-FACT-{i:03d}")
        elif isinstance(fact, dict):
            desc = fact.get("description", "")
            file_path = fact.get("source_file", fact.get("file_path", ""))
            change_type = fact.get("fact_type", fact.get("change_type", ""))
            fact_id = fact.get("fact_id", f"MR-FACT-{i:03d}")
        else:
            continue

        line = f"- [{fact_id}]"
        if change_type:
            line += f" ({change_type})"
        line += f" {desc}"
        if file_path:
            line += f"  [文件: {file_path}]"
        lines.append(line)

    return _PROMPT_LOADER.render(
        "nodes/checkpoint_generator/mr_code_facts_user.md",
        facts_block="\n".join(lines),
    )


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
        3. 构造 prompt 发送给 LLM（如有模版叶子，注入绑定指令）
        4. 如果存在 mr_code_facts，注入代码变更事实到 prompt
        5. 为每个返回的 checkpoint 生成稳定 ID
        6. 关联证据引用
        7. 后处理：校验模版叶子 ID、回填路径、标记低置信度
        """
        research_output = state["research_output"]
        facts = research_output.facts

        # 读取模版叶子目标（可能为空列表）
        template_leaf_targets: list[TemplateLeafTarget] = state.get(
            "template_leaf_targets", []
        )

        # 向后兼容：如果 facts 为空，从现有字段合成基础 facts
        if not facts:
            facts = _synthesize_facts_from_legacy(research_output)

        if not facts:
            return {"checkpoints": []}

        prompt = _build_checkpoint_prompt(facts, state.get("language", "zh-CN"))

        # 如果存在模版叶子目标，注入模版绑定 prompt
        if template_leaf_targets:
            logger.info(
                "Template binding enabled for checkpoint generation: leaf_targets=%d. "
                "Logic: LLM chooses one template leaf id from the provided leaf targets; "
                "the system then validates the id, backfills template path ids/titles, "
                "and flags matches below %.2f as low confidence.",
                len(template_leaf_targets),
                _LOW_CONFIDENCE_THRESHOLD,
            )
            prompt += "\n\n" + _build_template_binding_prompt(template_leaf_targets)

        # ---- XMind 参考注入 ----
        xmind_ref_section = _build_xmind_reference_prompt(state.get("xmind_reference_summary"))
        if xmind_ref_section:
            prompt += xmind_ref_section

        # ---- MR 代码事实注入 ----
        mr_code_facts = state.get("mr_code_facts", [])
        if mr_code_facts:
            logger.info(
                "MR code facts available for checkpoint generation: %d facts",
                len(mr_code_facts),
            )
            mr_facts_section = _build_mr_code_facts_prompt(mr_code_facts)
            if mr_facts_section:
                prompt += mr_facts_section

        response = llm_client.generate_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            response_model=CheckpointDraftCollection,
        )

        # 构建 fact_id → fact 的查找表，用于关联证据引用
        fact_lookup = {f.fact_id: f for f in facts if f.fact_id}

        # 构建 leaf_id 合法集合，用于后处理校验
        valid_leaf_ids: set[str] = {lt.leaf_id for lt in template_leaf_targets}
        leaf_lookup: dict[str, TemplateLeafTarget] = {
            lt.leaf_id: lt for lt in template_leaf_targets
        }

        checkpoints: list[Checkpoint] = []
        bound_count = 0
        unbound_count = 0
        invalid_cleared_count = 0
        low_confidence_count = 0
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

            # ---- 模版绑定后处理 ----
            template_leaf_id = draft.template_leaf_id
            template_path_ids: list[str] = []
            template_path_titles: list[str] = []
            template_match_confidence = draft.template_match_confidence
            template_match_reason = draft.template_match_reason
            template_match_low_confidence = False
            binding_status = "unbound"

            if template_leaf_id and template_leaf_targets:
                if template_leaf_id not in valid_leaf_ids:
                    # LLM 返回了无效的 leaf_id，清空绑定
                    original_leaf_id = template_leaf_id
                    template_leaf_id = ""
                    template_match_confidence = 0.0
                    template_match_reason = ""
                    binding_status = "invalid_leaf_id_cleared"
                    invalid_cleared_count += 1
                    logger.info(
                        "Template binding result: checkpoint_id=%s status=%s "
                        "requested_leaf_id=%s reason=%s",
                        checkpoint_id,
                        binding_status,
                        original_leaf_id,
                        draft.template_match_reason or "-",
                    )
                else:
                    # 回填路径信息
                    leaf_target = leaf_lookup[template_leaf_id]
                    template_path_ids = leaf_target.path_ids
                    template_path_titles = leaf_target.path_titles
                    binding_status = "bound"
                    bound_count += 1

                    # 标记低置信度
                    if template_match_confidence < _LOW_CONFIDENCE_THRESHOLD:
                        template_match_low_confidence = True
                        low_confidence_count += 1

                    logger.info(
                        "Template binding result: checkpoint_id=%s status=%s leaf_id=%s "
                        "confidence=%.2f low_confidence=%s path=%s reason=%s",
                        checkpoint_id,
                        binding_status,
                        template_leaf_id,
                        template_match_confidence,
                        template_match_low_confidence,
                        " > ".join(template_path_titles) or "-",
                        template_match_reason or "-",
                    )
            elif template_leaf_targets:
                unbound_count += 1
                logger.info(
                    "Template binding result: checkpoint_id=%s status=unbound reason=%s",
                    checkpoint_id,
                    template_match_reason or "LLM did not return template_leaf_id",
                )

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
                    template_leaf_id=template_leaf_id,
                    template_path_ids=template_path_ids,
                    template_path_titles=template_path_titles,
                    template_match_confidence=template_match_confidence,
                    template_match_reason=template_match_reason,
                    template_match_low_confidence=template_match_low_confidence,
                )
            )

        if template_leaf_targets:
            logger.info(
                "Template binding summary: checkpoints=%d bound=%d low_confidence=%d "
                "unbound=%d invalid_cleared=%d",
                len(checkpoints),
                bound_count,
                low_confidence_count,
                unbound_count,
                invalid_cleared_count,
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
        if fact.requirement:
            lines.append(f"  Requirement: {fact.requirement}")
        if fact.branch_hint:
            lines.append(f"  Branch hint: {fact.branch_hint}")
        if fact.code_actual_implementation:
            lines.append(f"  Code implementation: {fact.code_actual_implementation}")
        if fact.code_todo:
            lines.append(f"  Code TODO: {fact.code_todo}")

    lines.append("")
    lines.append(
        "For each fact, generate 1 or more specific, verifiable test checkpoints. "
        "Include the source fact_ids in each checkpoint. "
        "Ensure checkpoint titles are unique and descriptive.\n\n"
        "If a fact contains Code TODO / Code implementation notes, "
        "carry that mismatch risk into the generated checkpoints so the checklist "
        "explicitly covers the pending discrepancy.\n\n"
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


def _build_template_binding_prompt(leaf_targets: list[TemplateLeafTarget]) -> str:
    """构造模版绑定的 prompt 片段。

    将所有叶子目标格式化为列表，注入到 checkpoint 生成 prompt 中，
    引导 LLM 为每个 checkpoint 选择最匹配的模版叶子节点。

    Args:
        leaf_targets: 拍平后的模版叶子目标列表。

    Returns:
        模版绑定指令的 prompt 文本。
    """
    lines = [
        "【模版归类要求（必须遵守）】",
        "以下是项目级 Checklist 模版的叶子节点列表，每个 checkpoint 必须绑定到最匹配的叶子节点。",
        "请为每个 checkpoint 设置以下字段：",
        "- template_leaf_id: 最匹配的叶子节点 ID（必须从下方列表中选择）",
        "- template_match_confidence: 匹配置信度（0.0-1.0，1.0 表示完全匹配）",
        "- template_match_reason: 简要说明为什么选择该叶子节点（中文）",
        "",
        "可选的叶子节点列表：",
    ]

    for lt in leaf_targets:
        lines.append(f"- ID: {lt.leaf_id} | 路径: {lt.path_text}")

    lines.append("")
    lines.append(
        "如果某个 checkpoint 确实无法匹配任何叶子节点，"
        "可以将 template_leaf_id 设为空字符串，template_match_confidence 设为 0.0。"
    )

    return "\n".join(lines)
