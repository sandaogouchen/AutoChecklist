"""LangGraph node that loads the ProjectContext for the current run and
injects a textual summary into the shared state.

This node should execute as the *first* step in the main workflow so that
every downstream node has access to the project context.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.project_models import ProjectContext
from app.services.project_context_service import ProjectContextService

logger = logging.getLogger(__name__)

# Module-level service instance (shared with the API layer).
_project_service = ProjectContextService()


def load_project_context(state: dict[str, Any]) -> dict[str, Any]:
    """Read ``project_id`` from *state*, resolve the :class:`ProjectContext`,
    and write its ``summary_text()`` back into state under the key
    ``project_context_summary``.

    If the project cannot be found the node logs a warning and writes an
    empty string so downstream nodes still function (graceful degradation).
    """
    project_id: str | None = state.get("project_id")
    if not project_id:
        logger.info("No project_id in state \u2013 skipping project context load.")
        state["project_context_summary"] = ""
        return state

    project: ProjectContext | None = _project_service.get_project(project_id)
    if project is None:
        logger.warning("Project '%s' not found \u2013 continuing without context.", project_id)
        state["project_context_summary"] = ""
        return state

    summary = project.summary_text()
    logger.info("Loaded project context for '%s' (%d chars).", project.name, len(summary))
    state["project_context_summary"] = summary
    return state
