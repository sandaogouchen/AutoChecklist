from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import GlobalState
from app.graphs.case_generation import build_case_generation_subgraph
from app.graphs.output_delivery import build_output_delivery_subgraph
from app.nodes.context_research import build_context_research_node
from app.nodes.input_parser import input_parser_node
from app.nodes.output_platform_writer import PlatformPublisher
from app.nodes.reflection import reflection_node
from app.repositories.run_repository import FileRunRepository


def build_workflow(
    llm_client: LLMClient,
    repository: FileRunRepository,
    platform_publisher: PlatformPublisher | None = None,
):
    case_generation_subgraph = build_case_generation_subgraph(llm_client)
    output_subgraph = build_output_delivery_subgraph(
        repository=repository,
        platform_publisher=platform_publisher,
    )
    builder = StateGraph(GlobalState)
    builder.add_node("input_parser", input_parser_node)
    builder.add_node("context_research", build_context_research_node(llm_client))
    builder.add_node("case_generation", _build_case_generation_node(case_generation_subgraph))
    builder.add_node("reflection", reflection_node)
    builder.add_node("output_delivery", _build_output_delivery_node(output_subgraph))
    builder.add_edge(START, "input_parser")
    builder.add_edge("input_parser", "context_research")
    builder.add_edge("context_research", "case_generation")
    builder.add_edge("case_generation", "reflection")
    builder.add_edge("reflection", "output_delivery")
    builder.add_edge("output_delivery", END)
    return builder.compile()


def _build_case_generation_node(case_generation_subgraph):
    def case_generation_node(state: GlobalState) -> GlobalState:
        subgraph_result = case_generation_subgraph.invoke(
            {
                "language": state.get("language", "zh-CN"),
                "parsed_document": state["parsed_document"],
                "research_output": state["research_output"],
            }
        )
        return {
            "planned_scenarios": subgraph_result.get("planned_scenarios", []),
            "mapped_evidence": subgraph_result.get("mapped_evidence", {}),
            "draft_cases": subgraph_result.get("draft_cases", []),
            "test_cases": subgraph_result.get("test_cases", []),
        }

    return case_generation_node


def _build_output_delivery_node(output_subgraph):
    def output_delivery_node(state: GlobalState) -> GlobalState:
        return output_subgraph.invoke(state)

    return output_delivery_node
