"""LangGraph node that loads the ProjectContext for the current run and
injects a textual summary into the shared state.

This node should execute as the *first* step in the main workflow so that
every downstream node has access to the project context.

Usage::

    from app.nodes.project_context_loader import build_project_context_loader

    loader = build_project_context_loader(project_context_service)
    # ``loader`` is now a callable with signature (state: dict) -> dict
    # suitable for registering as a LangGraph node.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.domain.project_models import ProjectContext
from app.services.project_context_service import ProjectContextService

logger = logging.getLogger(__name__)


def build_project_context_loader(
    service: ProjectContextService,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Factory that returns a LangGraph-compatible node function.

    The returned closure captures *service* so that the node can look up
    project context at **runtime** (when LangGraph passes in the state dict)
    rather than at graph-build time.

    Args:
        service: The application-wide :class:`ProjectContextService` instance.

    Returns:
        A callable ``(state: dict) -> dict`` that reads ``project_id`` from
        *state* and writes ``project_context_summary`` back.
    """

    def _load_project_context(state: dict[str, Any]) -> dict[str, Any]:
        """Read ``project_id`` from *state*, resolve the
        :class:`ProjectContext`, and write its ``summary_text()`` back
        into state under the key ``project_context_summary``.

        If the project cannot be found the node logs a warning and writes
        an empty string so downstream nodes still function (graceful
        degradation).
        """
        project_id: str | None = state.get("project_id")
        if not project_id:
            logger.info("No project_id in state \u2013 skipping project context load.")
            return {"project_context_summary": ""}

        try:
            project: ProjectContext | None = service.get_project(project_id)
        except Exception:
            logger.error(
                "Failed to load project '%s' \u2013 continuing without context.",
                project_id,
                exc_info=True,
            )
            return {"project_context_summary": ""}

        if project is None:
            logger.warning(
                "Project '%s' not found \u2013 continuing without context.", project_id
            )
            return {"project_context_summary": ""}

        try:
            summary = project.summary_text()
        except Exception:
            logger.error(
                "Failed to generate summary for project '%s' \u2013 continuing without context.",
                project_id,
                exc_info=True,
            )
            return {"project_context_summary": ""}

        logger.info(
            "Loaded project context for '%s' (%d chars).", project.name, len(summary)
        )
        return {"project_context_summary": summary}

    return _load_project_context
