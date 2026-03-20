"""主工作流图定义。

使用 LangGraph 构建 AutoChecklist 的主处理流水线：
  input_parser → template_loader → context_research → case_generation（子图） → reflection

每个节点接收并返回 ``GlobalState``，通过增量更新的方式传递数据。

变更：
- 桥接节点新增 mandatory_skeleton 字段映射
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import GlobalState
from app.graphs.case_generation import build_case_generation_subgraph
from app.nodes.context_research import build_context_research_node
from app.nodes.input_parser import input_parser_node
from app.nodes.reflection import reflection_node
from app.nodes.template_loader import build_template_loader_node


def build_workflow(llm_client: LLMClient, project_context_loader=None):
    """构建并编译主工作流图。"""
    case_generation_subgraph = build_case_generation_subgraph(llm_client)

    builder = StateGraph(GlobalState)
    builder.add_node("input_parser", input_parser_node)
    builder.add_node("template_loader", build_template_loader_node())
    if project_context_loader is not None:
        builder.add_node("project_context_loader", project_context_loader)
    builder.add_node("context_research", build_context_research_node(llm_client))
    builder.add_node("case_generation", _build_case_generation_bridge(case_generation_subgraph))
    builder.add_node("reflection", reflection_node)

    builder.add_edge(START, "input_parser")
    builder.add_edge("input_parser", "template_loader")
    if project_context_loader is not None:
        builder.add_edge("template_loader", "project_context_loader")
        builder.add_edge("project_context_loader", "context_research")
    else:
        builder.add_edge("template_loader", "context_research")
    builder.add_edge("context_research", "case_generation")
    builder.add_edge("case_generation", "reflection")
    builder.add_edge("reflection", END)

    return builder.compile()


def _build_case_generation_bridge(case_generation_subgraph):
    """构建主图与用例生成子图之间的桥接节点。

    变更：
    - 新增 mandatory_skeleton 字段的传入与传出映射
    """

    def case_generation_node(state: GlobalState) -> GlobalState:
        subgraph_input = {
            "language": state.get("language", "zh-CN"),
            "parsed_document": state["parsed_document"],
            "research_output": state["research_output"],
            "project_context_summary": state.get("project_context_summary", ""),
            # ---- 模版相关字段传入子图 ----
            "template_leaf_targets": state.get("template_leaf_targets", []),
            "project_template": state.get("project_template"),
            # ---- 强制骨架传入子图 ----
            "mandatory_skeleton": state.get("mandatory_skeleton"),
        }

        # 清理 None 值
        subgraph_input = {k: v for k, v in subgraph_input.items() if v is not None}

        subgraph_result = case_generation_subgraph.invoke(subgraph_input)

        return {
            "planned_scenarios": subgraph_result.get("planned_scenarios", []),
            "checkpoints": subgraph_result.get("checkpoints", []),
            "checkpoint_coverage": subgraph_result.get("checkpoint_coverage", []),
            "checkpoint_paths": subgraph_result.get("checkpoint_paths", []),
            "canonical_outline_nodes": subgraph_result.get("canonical_outline_nodes", []),
            "mapped_evidence": subgraph_result.get("mapped_evidence", {}),
            "draft_cases": subgraph_result.get("draft_cases", []),
            "test_cases": subgraph_result.get("test_cases", []),
            "optimized_tree": subgraph_result.get("optimized_tree", []),
        }

    return case_generation_node
