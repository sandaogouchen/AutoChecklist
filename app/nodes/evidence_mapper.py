from __future__ import annotations

import re

from app.domain.research_models import EvidenceRef
from app.domain.state import CaseGenState


def evidence_mapper_node(state: CaseGenState) -> CaseGenState:
    parsed_document = state["parsed_document"]
    fact_lookup = {
        fact.id.strip(): fact
        for fact in state["research_output"].facts
        if fact.id.strip()
    }
    mapped_evidence: dict[str, list[EvidenceRef]] = {}

    for scenario in state["planned_scenarios"]:
        scenario_tokens = set(_tokenize(f"{scenario.title} {scenario.rationale}"))
        evidence_refs = list(fact_lookup.get(scenario.fact_id, None).evidence_refs) if scenario.fact_id in fact_lookup else []
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
        mapped_evidence[_scenario_key(scenario)] = _dedupe_evidence(evidence_refs)

    return {"mapped_evidence": mapped_evidence}


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", value.casefold())


def _scenario_key(scenario) -> str:
    return scenario.fact_id.strip() or scenario.title.strip()


def _dedupe_evidence(evidence_refs: list[EvidenceRef]) -> list[EvidenceRef]:
    deduped: list[EvidenceRef] = []
    seen: set[tuple[str, int, int, str]] = set()
    for ref in evidence_refs:
        key = (ref.section_title, ref.line_start, ref.line_end, ref.excerpt)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped
