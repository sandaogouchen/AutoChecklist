from typing import get_type_hints

from app.domain.state import CaseGenState


def test_case_gen_state_type_hints_resolve_coverage_result() -> None:
    hints = get_type_hints(CaseGenState)

    assert "coverage_result" in hints
