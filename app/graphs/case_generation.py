from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import CaseGenState
from app.nodes.draft_writer import build_draft_writer_node
from app.nodes.evidence_mapper import evidence_mapper_node
from app.nodes.scenario_planner import scenario_planner_node
from app.nodes.structure_assembler import structure_assembler_node


def build_case_generation_subgraph(llm_client: LLMClient):
    builder = StateGraph(CaseGenState)
    builder.add_node("scenario_planner", scenario_planner_node)
    builder.add_node("evidence_mapper", evidence_mapper_node)
    builder.add_node("draft_writer", build_draft_writer_node(llm_client))
    builder.add_node("structure_assembler", structure_assembler_node)
    builder.add_edge(START, "scenario_planner")
    builder.add_edge("scenario_planner", "evidence_mapper")
    builder.add_edge("evidence_mapper", "draft_writer")
    builder.add_edge("draft_writer", "structure_assembler")
    builder.add_edge("structure_assembler", END)
    return builder.compile()
