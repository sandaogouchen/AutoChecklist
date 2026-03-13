from __future__ import annotations

from app.domain.output_models import OutputBundle
from app.domain.state import GlobalState


def output_bundle_builder_node(state: GlobalState) -> GlobalState:
    bundle = OutputBundle.from_state(
        run_id=state["run_id"],
        request=state["request"],
        parsed_document=state["parsed_document"],
        research_output=state["research_output"],
        test_cases=state["test_cases"],
        quality_report=state["quality_report"],
    )
    return {"output_bundle": bundle}
