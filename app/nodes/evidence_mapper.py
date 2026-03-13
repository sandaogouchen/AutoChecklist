from __future__ import annotations

import re

from app.domain.research_models import EvidenceRef
from app.domain.state import CaseGenState


def evidence_mapper_node(state: CaseGenState) -> CaseGenState:
    parsed_document = state["parsed_document"]
    mapped_evidence: dict[str, list[EvidenceRef]] = {}

    for scenario in state["planned_scenarios"]:
        scenario_tokens = set(_tokenize(scenario.title))
        evidence_refs: list[EvidenceRef] = []
        for section in parsed_document.sections:
            heading_tokens = set(_tokenize(section.heading))
            content_tokens = set(_tokenize(section.content))
            if scenario_tokens & (heading_tokens | content_tokens):
                evidence_refs.append(
                    EvidenceRef(
                        section_title=section.heading,
                        excerpt=section.content[:200],
                        line_start=section.line_start,
                        line_end=section.line_end,
                        confidence=0.85,
                    )
                )
        if not evidence_refs and parsed_document.sections:
            section = parsed_document.sections[0]
            evidence_refs.append(
                EvidenceRef(
                    section_title=section.heading,
                    excerpt=section.content[:200],
                    line_start=section.line_start,
                    line_end=section.line_end,
                    confidence=0.4,
                )
            )
        mapped_evidence[scenario.title] = evidence_refs

    return {"mapped_evidence": mapped_evidence}


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", value.casefold())
