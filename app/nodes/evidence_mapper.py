"""证据映射节点。

将规划的测试场景与 PRD 文档章节进行关联匹配，
为每个场景找到最相关的文档证据（``EvidenceRef``）。
"""

from __future__ import annotations

import re

from app.domain.research_models import EvidenceRef
from app.domain.state import CaseGenState

# 证据摘录的最大字符数
_EXCERPT_MAX_LENGTH = 200

# 无匹配时使用首章节作为兆底证据的默认置信度
_FALLBACK_CONFIDENCE = 0.4

# 关键词命中时的默认置信度
_MATCH_CONFIDENCE = 0.85


def evidence_mapper_node(state: CaseGenState) -> CaseGenState:
    """为每个测试场景匹配 PRD 文档中的证据。

    匹配策略：基于关键词交集——将场景标题和章节标题/内容分别分词，
    若存在交集则视为匹配。当某场景无任何匹配时，使用文档首章节作为兆底。

    Returns:
        包含 ``mapped_evidence`` 的状态增量（场景标题 → 证据列表的映射）。
    """
    parsed_document = state["parsed_document"]
    mapped_evidence: dict[str, list[EvidenceRef]] = {}

    for scenario in state["planned_scenarios"]:
        scenario_tokens = set(_tokenize(scenario.title))
        evidence_refs: list[EvidenceRef] = []

        # 遍历所有章节，通过关键词交集判断是否匹配
        for section in parsed_document.sections:
            heading_tokens = set(_tokenize(section.heading))
            content_tokens = set(_tokenize(section.content))
            if scenario_tokens & (heading_tokens | content_tokens):
                evidence_refs.append(
                    EvidenceRef(
                        section_title=section.heading,
                        excerpt=section.content[:_EXCERPT_MAX_LENGTH],
                        line_start=section.line_start,
                        line_end=section.line_end,
                        confidence=_MATCH_CONFIDENCE,
                    )
                )

        # 兆底：无匹配时使用首章节，并标记为低置信度
        if not evidence_refs and parsed_document.sections:
            first_section = parsed_document.sections[0]
            evidence_refs.append(
                EvidenceRef(
                    section_title=first_section.heading,
                    excerpt=first_section.content[:_EXCERPT_MAX_LENGTH],
                    line_start=first_section.line_start,
                    line_end=first_section.line_end,
                    confidence=_FALLBACK_CONFIDENCE,
                )
            )

        mapped_evidence[scenario.title] = evidence_refs

    return {"mapped_evidence": mapped_evidence}


def _tokenize(value: str) -> list[str]:
    """将文本分词为小写关键词列表。

    同时支持英文单词和中文单字的提取，使用正则表达式匹配
    连续的字母数字序列和 CJK 统一表意文字。
    """
    return re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", value.casefold())
