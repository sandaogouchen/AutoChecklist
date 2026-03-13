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
            refs = evidence.get(scenario.title, [])
            prompt_lines.append(
                "\n".join(
                    [
                        f"Scenario {index}: {scenario.title}",
                        f"Category: {scenario.category}",
                        f"Risk: {scenario.risk}",
                        f"Rationale: {scenario.rationale}",
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
                "You write concise manual QA test cases as structured JSON. "
                "Always include ids, steps, expected_results, and evidence_refs."
            ),
            user_prompt="\n\n".join(prompt_lines),
            response_model=DraftCaseCollection,
        )
        return {"draft_cases": response.test_cases}

    return draft_writer_node
