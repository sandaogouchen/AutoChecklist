from __future__ import annotations

from pydantic import BaseModel, Field

from app.clients.llm import LLMClient
from app.domain.case_models import TestCase
from app.domain.state import CaseGenState


class DraftCaseCollection(BaseModel):
    test_cases: list[TestCase] = Field(default_factory=list)


def build_draft_writer_node(llm_client: LLMClient):
    def draft_writer_node(state: CaseGenState) -> CaseGenState:
        scenarios = state["planned_scenarios"]
        evidence = state["mapped_evidence"]
        prompt_lines = []
        for index, scenario in enumerate(scenarios, start=1):
            refs = evidence.get(scenario.fact_id or scenario.title, [])
            prompt_lines.append(
                "\n".join(
                    [
                        f"Scenario {index}: {scenario.title}",
                        f"Fact ID: {scenario.fact_id or f'FACT-{index:03d}'}",
                        f"Category: {scenario.category}",
                        f"Risk: {scenario.risk}",
                        f"Rationale: {scenario.rationale}",
                        f"Branch Hint: {scenario.branch_hint}",
                        "Evidence:",
                        *[
                            f"- {ref.section_title} ({ref.line_start}-{ref.line_end}): {ref.excerpt}"
                            for ref in refs
                        ],
                    ]
                )
            )
        response = llm_client.generate_structured(
            system_prompt=(
                "You write concise manual QA checklist graphs as structured JSON. "
                'Return exactly one JSON object with top-level shape {"test_cases": [...]} '
                "and never return a bare array. Each checklist node must include "
                '"id", "fact_id", "node_type", "title", "branch", "parent", "root", '
                '"prev", "next", "steps", "expected_results", and "evidence_refs". '
                'Use node_type="root" for the fact root node. Use null '
                "for missing parent/root/prev/next pointers before normalization. "
                '"evidence_refs" must be an '
                'array of objects using the shape {"section_title": string, "excerpt": string, '
                '"line_start": number, "line_end": number, "confidence": number}. '
                "Never emit evidence_refs as strings."
            ),
            user_prompt="\n\n".join(prompt_lines),
            response_model=DraftCaseCollection,
        )
        return {"draft_cases": response.test_cases}

    return draft_writer_node
