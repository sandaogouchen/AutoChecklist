"""Shared workflow state definitions.

Every LangGraph node reads from and writes to this state dict.  Defining
the keys here avoids magic-string proliferation.
"""

from __future__ import annotations

from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    """Top-level state that flows through the LangGraph graph."""

    # -- identifiers -------------------------------------------------------
    case_id: str
    project_id: str  # NEW \u2013 optional link to a ProjectContext

    # -- project context (populated by project_context_loader) -------------
    project_context_summary: str

    # -- research phase ----------------------------------------------------
    context_research_output: str

    # -- drafting phase ----------------------------------------------------
    draft_checklist: list[dict[str, Any]]

    # -- reflection phase --------------------------------------------------
    reflection_notes: str
    refined_checklist: list[dict[str, Any]]

    # -- meta --------------------------------------------------------------
    run_id: str
    status: str
    error: str
