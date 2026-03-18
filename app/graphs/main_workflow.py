"""主工作流 DAG 定义。"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import CaseGenState, GlobalState
from app.graphs.case_generation import build_case_generation_subgraph
from app.nodes.checkpoint_evaluator import build_checkpoint_evaluator
from app.nodes.checkpoint_generator import build_checkpoint_generator
from app.nodes.context_research import build_context_research
from app.nodes.evaluation import build_evaluation_node
from app.nodes.evidence_mapper import build_evidence_mapper
from app.nodes.input_parser import build_input_parser
from app.nodes.project_context_loader import build_project_context_loader
from app.nodes.reflection import build_reflection_node
from app.nodes.scenario_planner import build_scenario_planner


def build_main_graph(llm_client: LLMClient) -> StateGraph:
    """构建主工作流状态图。"""
    graph = StateGraph(GlobalState)

    # 注册节点
    graph.add_node("input_parser", build_input_parser())
    graph.add_node("project_context_loader", build_project_context_loader())
    graph.add_node("context_research", build_context_research(llm_client))
    graph.add_node("scenario_planner", build_scenario_planner(llm_client))
    graph.add_node("checkpoint_generator", build_checkpoint_generator(llm_client))
    graph.add_node("checkpoint_evaluator", build_checkpoint_evaluator())
    graph.add_node("evidence_mapper", build_evidence_mapper())

    # 用例生成子图
    case_gen_subgraph = build_case_generation_subgraph(llm_client)

    def bridge_to_case_gen(state: GlobalState) -> CaseGenState:
        """主状态 -> 子图状态桥接。"""
        return CaseGenState(
            checkpoints=state.get("checkpoints", []),
            scenarios=state.get("scenarios", []),
            facts=state.get("facts", []),
            test_cases=[],
            parsed_document=state.get("parsed_document"),
            project_context=state.get("project_context"),
            language=state.get("language", "en"),
            llm_config=state.get("llm_config"),
            iteration_index=state.get("iteration_index", 0),
            # ---- 模板驱动生成支持：将模板数据传递到子图 ----
            template=state.get("template"),
        )

    def bridge_from_case_gen(state: CaseGenState) -> dict:
        """子图状态 -> 主状态桥接。"""
        return {"test_cases": state.get("test_cases", [])}

    graph.add_node("case_generation", case_gen_subgraph)
    graph.add_node("evaluation", build_evaluation_node(llm_client))
    graph.add_node("reflection", build_reflection_node(llm_client))

    # 边
    graph.set_entry_point("input_parser")
    graph.add_edge("input_parser", "project_context_loader")
    graph.add_edge("project_context_loader", "context_research")
    graph.add_edge("context_research", "scenario_planner")
    graph.add_edge("scenario_planner", "checkpoint_generator")
    graph.add_edge("checkpoint_generator", "checkpoint_evaluator")
    graph.add_edge("checkpoint_evaluator", "evidence_mapper")
    graph.add_edge("evidence_mapper", "case_generation")
    graph.add_edge("case_generation", "evaluation")
    graph.add_edge("evaluation", "reflection")
    graph.add_edge("reflection", END)

    return graph.compile()
