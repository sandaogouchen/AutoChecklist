"""主工作流图定义。

使用 LangGraph 构建 AutoChecklist 的主处理流水线：
  input_parser → context_research → case_generation（子图） → reflection

每个节点接收并返回 ``GlobalState``，通过增量更新的方式传递数据。

F5 变更：桥接节点新增 ``optimized_tree`` 字段的转发，使子图中
checklist_optimizer 的合并结果能透传回 GlobalState，供下游
PlatformDispatcher 用于 Markdown / XMind 渲染。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import GlobalState
from app.graphs.case_generation import build_case_generation_subgraph
from app.nodes.context_research import build_context_research_node
from app.nodes.input_parser import input_parser_node
from app.nodes.reflection import reflection_node


def build_workflow(llm_client: LLMClient, project_context_loader=None):
    """构建并编译主工作流图。

    工作流结构（线性流水线）：
    ```
    START → input_parser → [project_context_loader] → context_research → case_generation → reflection → END
    ```

    Args:
        llm_client: LLM 客户端实例，传递给需要调用 LLM 的节点。
        project_context_loader: 可选的项目上下文加载节点（闭包 callable），
            插入在 input_parser 之后。由
            ``build_project_context_loader(service)`` 工厂函数创建。

    Returns:
        编译后的 LangGraph 可执行工作流。
    """
    case_generation_subgraph = build_case_generation_subgraph(llm_client)

    builder = StateGraph(GlobalState)
    builder.add_node("input_parser", input_parser_node)
    if project_context_loader is not None:
        builder.add_node("project_context_loader", project_context_loader)
    builder.add_node("context_research", build_context_research_node(llm_client))
    builder.add_node("case_generation", _build_case_generation_bridge(case_generation_subgraph))
    builder.add_node("reflection", reflection_node)

    builder.add_edge(START, "input_parser")
    if project_context_loader is not None:
        builder.add_edge("input_parser", "project_context_loader")
        builder.add_edge("project_context_loader", "context_research")
    else:
        builder.add_edge("input_parser", "context_research")
    builder.add_edge("context_research", "case_generation")
    builder.add_edge("case_generation", "reflection")
    builder.add_edge("reflection", END)

    return builder.compile()


def _build_case_generation_bridge(case_generation_subgraph):
    """构建主图与用例生成子图之间的桥接节点。

    职责：
    1. 从 GlobalState 中提取子图所需的字段，构造 CaseGenState
    2. 调用子图执行
    3. 将子图输出映射回 GlobalState 的增量更新

    这种桥接模式将主图与子图的状态结构解耦，
    使两者可以独立演化而不互相影响。

    F5 变更：新增 ``optimized_tree`` 字段的转发。
    """

    def case_generation_node(state: GlobalState) -> GlobalState:
        # 从全局状态中提取子图所需的输入字段
        subgraph_input = {
            "language": state.get("language", "zh-CN"),
            "parsed_document": state["parsed_document"],
            "research_output": state["research_output"],
            # 传递项目上下文摘要到子图，供 draft_writer 等节点使用
            "project_context_summary": state.get("project_context_summary", ""),
        }
        subgraph_result = case_generation_subgraph.invoke(subgraph_input)

        # 将子图输出映射回全局状态，包含新增的 checkpoint 字段
        return {
            "planned_scenarios": subgraph_result.get("planned_scenarios", []),
            "checkpoints": subgraph_result.get("checkpoints", []),
            "checkpoint_coverage": subgraph_result.get("checkpoint_coverage", []),
            "mapped_evidence": subgraph_result.get("mapped_evidence", {}),
            "draft_cases": subgraph_result.get("draft_cases", []),
            "test_cases": subgraph_result.get("test_cases", []),
            # F5: 转发 checklist_optimizer 的合并结果
            "optimized_tree": subgraph_result.get("optimized_tree", []),
        }

    return case_generation_node
