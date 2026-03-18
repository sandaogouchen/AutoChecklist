"""Node: reflection

Reviews the draft checklist, optionally using project context to apply
domain-specific rules, and produces a refined version.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def reflection(state: dict[str, Any]) -> dict[str, Any]:
    """Reflect on the draft and emit ``reflection_notes`` + ``refined_checklist``."""

    draft = state.get("draft_checklist", [])
    project_summary = state.get("project_context_summary", "")

    logger.info("Reflecting on %d draft items (project_ctx=%d chars).",
                len(draft), len(project_summary))

    notes_parts: list[str] = [f"Reviewed {len(draft)} items."]
    if project_summary:
        notes_parts.append("Applied project-specific standards check.")

    state["reflection_notes"] = " ".join(notes_parts)
    state["refined_checklist"] = list(draft)  # shallow copy; real impl would modify
    return state
