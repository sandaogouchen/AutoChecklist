"""Node: draft_writer

Produces an initial checklist draft from the research output.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def draft_writer(state: dict[str, Any]) -> dict[str, Any]:
    """Create a first-pass checklist from research output."""

    research = state.get("context_research_output", "")
    project_summary = state.get("project_context_summary", "")

    logger.info("Drafting checklist (research=%d chars, project_ctx=%d chars).",
                len(research), len(project_summary))

    # Placeholder draft \u2013 a real implementation calls an LLM.
    draft = [
        {"item": "Verify requirement coverage", "source": "research"},
    ]

    if project_summary:
        draft.append({"item": "Validate against project standards", "source": "project_context"})

    state["draft_checklist"] = draft
    return state
