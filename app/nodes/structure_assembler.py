from __future__ import annotations

from app.domain.case_models import TestCase
from app.domain.state import CaseGenState


def structure_assembler_node(state: CaseGenState) -> CaseGenState:
    assembled_cases: list[TestCase] = []
    evidence_lookup = state.get("mapped_evidence", {})

    for index, case in enumerate(state.get("draft_cases", []), start=1):
        assembled_cases.append(
            case.model_copy(
                update={
                    "id": case.id or f"TC-{index:03d}",
                    "preconditions": case.preconditions or [],
                    "steps": case.steps or [],
                    "expected_results": case.expected_results or [],
                    "priority": case.priority or "P2",
                    "category": case.category or "functional",
                    "evidence_refs": case.evidence_refs or evidence_lookup.get(case.title, []),
                }
            )
        )

    return {"test_cases": assembled_cases}
