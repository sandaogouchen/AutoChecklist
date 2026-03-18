"""研究分析领域模型。

定义了 PRD 上下文研究阶段的数据结构，包括：
- ``EvidenceRef``：PRD 原文中的证据引用
- ``ResearchFact``：从 PRD 中提取的业务变化事实
- ``PlannedScenario``：规划的测试场景
- ``ResearchOutput``：上下文研究的完整输出
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, model_validator


EVIDENCE_REF_PATTERN = re.compile(
    r"^\s*(?P<section>.+?)\s*\((?P<line_start>\d+)(?:-(?P<line_end>\d+))?\)\s*:\s*(?P<excerpt>.*)\s*$"
)


class EvidenceRef(BaseModel):
    """PRD 原文证据引用。

    将测试用例与 PRD 原文建立可追溯的关联，
    记录引用来源的章节标题、摘录片段、行号范围及置信度。
    """

    section_title: str
    excerpt: str = ""
    line_start: int = 0
    line_end: int = 0
    confidence: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def coerce_string_reference(cls, value: Any) -> Any:
        if isinstance(value, dict):
            normalized_value = dict(value)
            if "section_title" not in normalized_value and isinstance(normalized_value.get("section"), str):
                normalized_value["section_title"] = normalized_value["section"].strip()
            if "excerpt" not in normalized_value and isinstance(normalized_value.get("quote"), str):
                normalized_value["excerpt"] = normalized_value["quote"].strip()
            return normalized_value

        if not isinstance(value, str):
            return value

        normalized_value = value.strip()
        if not normalized_value:
            return {"section_title": "generated_ref"}

        pattern_match = EVIDENCE_REF_PATTERN.match(normalized_value)
        if pattern_match:
            line_start = int(pattern_match.group("line_start"))
            line_end = int(pattern_match.group("line_end") or line_start)
            return {
                "section_title": pattern_match.group("section").strip(),
                "excerpt": pattern_match.group("excerpt").strip(),
                "line_start": line_start,
                "line_end": line_end,
            }

        section_title, separator, excerpt = normalized_value.partition(":")
        if separator:
            return {
                "section_title": section_title.strip(),
                "excerpt": excerpt.strip(),
            }

        return {"section_title": normalized_value}

class ResearchFact(BaseModel):
    """从 PRD 中提取的业务变化事实。

    每个 fact 代表一条独立的、可被进一步拆分为 checkpoint 的业务信息。

    Attributes:
        fact_id: 事实的唯一标识（如 FACT-001）。
        description: 事实的文字描述。
        source_section: 该事实来源的文档章节标题。
        evidence_refs: 关联的 PRD 原文证据引用。
        category: 事实类别（requirement / constraint / assumption / behavior）。
    """

    fact_id: str = ""
    description: str
    source_section: str = ""
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    category: str = "requirement"
    requirement: str = ""
    branch_hint: str = ""

    @model_validator(mode="before")
    @classmethod
    def coerce_requirement_object(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized_value = dict(value)
        if not normalized_value.get("fact_id") and isinstance(normalized_value.get("id"), str):
            normalized_value["fact_id"] = normalized_value["id"].strip()
        if not normalized_value.get("description"):
            legacy_summary = normalized_value.get("summary")
            if isinstance(legacy_summary, str) and legacy_summary.strip():
                normalized_value["description"] = legacy_summary.strip()
        if not normalized_value.get("source_section") and isinstance(normalized_value.get("section_title"), str):
            normalized_value["source_section"] = normalized_value["section_title"].strip()
        if not normalized_value.get("category") and isinstance(normalized_value.get("change_type"), str):
            normalized_value["category"] = normalized_value["change_type"].strip()

        requirement = normalized_value.get("requirement")
        if not isinstance(requirement, dict):
            return normalized_value

        scope = str(requirement.get("scope", "")).strip()
        detail = str(requirement.get("detail", "")).strip()
        parts = [part for part in (scope, detail) if part]
        normalized_value["requirement"] = " | ".join(parts)
        return normalized_value


class PlannedScenario(BaseModel):
    """规划的测试场景。

    由 scenario_planner 节点根据研究输出生成，
    每个场景对应一个待测试的用户行为或功能点。

    Attributes:
        title: 场景标题。
        category: 场景类别（functional / edge_case / performance）。
        risk: 风险等级（low / medium / high）。
        rationale: 选择该场景的理由或依据。
    """

    title: str
    fact_id: str = ""
    category: str = "functional"
    risk: str = "medium"
    rationale: str = ""
    branch_hint: str = ""


# ---------------------------------------------------------------------------
# 辅助函数：将 LLM 返回的 dict 元素智能转换为 str
# ---------------------------------------------------------------------------

def _value_to_str(value: object) -> str:
    """将任意值转换为紧凑的字符串表示。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [str(i).strip() for i in value if str(i).strip()]
        return ", ".join(parts) if parts else ""
    if value is None:
        return ""
    return str(value).strip()


def _extract_text_from_dict(d: dict, primary_key: str) -> str:
    """从 LLM 返回的 dict 中提取人类可读的字符串。

    提取策略：
    1. 如果 *primary_key* 存在于 *d* 中，以其值为主文本；
       将其他有意义的字符串值用 " | " 拼接在后面。
    2. 否则，退化为取 dict 中第一个非空字符串值。
    3. 最后兜底使用 ``str(d)``。
    """
    if primary_key in d:
        main_text = _value_to_str(d[primary_key])
        extras: list[str] = []
        for k, v in d.items():
            if k == primary_key:
                continue
            v_str = _value_to_str(v)
            if v_str:
                extras.append(v_str)
        if extras:
            return main_text + " | " + " | ".join(extras)
        return main_text

    # 退化：取第一个非空字符串值
    for v in d.values():
        if isinstance(v, str) and v.strip():
            return v.strip()

    # 最终兜底
    return str(d)


# 字段名 -> dict 中预期主键的映射
_PRIMARY_KEY_MAP: dict[str, str] = {
    "feature_topics": "topic",
    "user_scenarios": "scenario",
    "constraints": "constraint",
    "ambiguities": "ambiguity",
    "test_signals": "signal",
}


class ResearchOutput(BaseModel):
    """上下文研究输出。

    由 LLM 从 PRD 文档中提取的、与测试相关的结构化信息，
    作为后续场景规划和用例生成的输入依据。

    ``facts`` 字段是新增的结构化事实列表，默认为空列表以保持向后兼容。

    ``model_validator`` 负责将 LLM 可能返回的 ``list[dict]`` 格式
    智能转换为 ``list[str]``，从而兼容不同 LLM 的输出风格。
    """

    feature_topics: list[str] = Field(default_factory=list)
    user_scenarios: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    test_signals: list[str] = Field(default_factory=list)
    facts: list[ResearchFact] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_dict_items_to_str(cls, values: Any) -> Any:
        """将列表字段中的 dict 元素智能转换为 str。

        LLM 有时会返回结构化 dict 而非纯字符串。例如::

            feature_topics: [{"topic": "...", "details": [...]}]

        本 validator 会将其透明地转换为::

            feature_topics: ["... | detail1, detail2"]

        确保下游 Pydantic 字段校验不会失败。
        """
        if not isinstance(values, dict):
            return values

        for field_name, primary_key in _PRIMARY_KEY_MAP.items():
            raw_list = values.get(field_name)
            if not isinstance(raw_list, list):
                continue

            coerced: list[str] = []
            for item in raw_list:
                if isinstance(item, str):
                    coerced.append(item)
                elif isinstance(item, dict):
                    coerced.append(_extract_text_from_dict(item, primary_key))
                else:
                    coerced.append(str(item))
            values[field_name] = coerced

        return values
