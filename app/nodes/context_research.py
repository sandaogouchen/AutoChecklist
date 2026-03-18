"""Node: context_research

Gathers external or internal context needed to build the checklist.
Now also consumes the project context summary produced by the
project_context_loader node.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def context_research(state: dict[str, Any]) -> dict[str, Any]:
    """Perform research given ``case_id`` and optional project context."""

    case_id = state.get("case_id", "unknown")
    project_summary = state.get("project_context_summary", "")

    logger.info("Running context research for case '%s'.", case_id)

    research_parts: list[str] = []

    if project_summary:
        research_parts.append(f"[Project Context]\n{project_summary}")
        logger.info("Injected project context (%d chars) into research.", len(project_summary))

    # Placeholder: real implementation would call an LLM or retrieval tool.
    research_parts.append(f"[Case Research]\nResearch output for case {case_id}.")

    state["context_research_output"] = "\n\n".join(research_parts)
    return state
