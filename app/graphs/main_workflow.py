"""Assembles the main LangGraph workflow for AutoChecklist.

Graph topology
--------------
project_context_loader  -->  context_research  -->  draft_writer  -->  reflection
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.domain.state import WorkflowState
from app.nodes.context_research import context_research
from app.nodes.draft_writer import draft_writer
from app.nodes.project_context_loader import load_project_context
from app.nodes.reflection import reflection


def build_workflow() -> StateGraph:
    """Return the compiled LangGraph :class:`StateGraph`."""

    graph = StateGraph(WorkflowState)

    # -- nodes -------------------------------------------------------------
    graph.add_node("project_context_loader", load_project_context)
    graph.add_node("context_research", context_research)
    graph.add_node("draft_writer", draft_writer)
    graph.add_node("reflection", reflection)

    # -- edges -------------------------------------------------------------
    graph.set_entry_point("project_context_loader")
    graph.add_edge("project_context_loader", "context_research")
    graph.add_edge("context_research", "draft_writer")
    graph.add_edge("draft_writer", "reflection")
    graph.add_edge("reflection", END)

    return graph
