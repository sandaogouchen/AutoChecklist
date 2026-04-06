"""主工作流图定义。
使用 LangGraph 构建 AutoChecklist 的主处理流水线：
input_parser → template_loader → [xmind_reference_loader] → [project_context_loader]
→ [knowledge_retrieval] → context_research → case_generation（子图） → reflection

每个节点接收并返回 ``GlobalState``，通过增量更新的方式传递数据。

变更：
- 新增 template_loader 节点，始终添加（无模版时自动跳过）
- 新增可选 xmind_reference_loader 节点，在 template_loader 之后加载参考 XMind 文件
- 桥接节点新增 template_leaf_targets 和 project_template 字段映射
- 桥接节点新增 mandatory_skeleton 字段映射
- 桥接节点新增 xmind_reference_summary 字段映射
- 桥接节点新增 coverage_result 字段回传映射
- 边连接链路调整为 input_parser → template_loader → [xmind_reference_loader]
  → [project_context_loader] → [knowledge_retrieval] → context_research
- 新增可选 knowledge_retrieval 节点，在 context_research 前注入知识检索结果
- 新增可选 timer / iteration_index 参数，支持节点级耗时计量
- 使用 state_bridge.build_bridge 替代手动桥接函数，实现自动字段转发
- 出向回传采用显式 allowlist，避免子图内部中间态默认泄漏回主图
- 新增可选 codebase_root / coco_settings 参数，支持 MR 代码分析
- 桥接节点新增 MR 相关字段映射（mr_input, mr_code_facts, mr_consistency_issues 等）
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import CaseGenState, GlobalState
from app.graphs.case_generation import build_case_generation_subgraph
from app.graphs.state_bridge import build_bridge
from app.nodes.context_research import build_context_research_node
from app.nodes.input_parser import input_parser_node
from app.nodes.reflection import reflection_node
from app.nodes.template_loader import build_template_loader_node
from app.utils.timing import maybe_wrap


def build_workflow(
    llm_client: LLMClient,
    project_context_loader=None,
    knowledge_retrieval_node=None,
    xmind_reference_loader_node=None,
    timer=None,
    iteration_index: int = 0,
    codebase_root: str | None = None,
    coco_settings=None,
):
    """构建并编译主工作流图。

    工作流结构（线性流水线）：
    ```
    START → input_parser → template_loader → [xmind_reference_loader]
    → [project_context_loader] → [knowledge_retrieval]
    → context_research → case_generation → reflection → END
    ```

    template_loader 始终添加，当未提供模版文件路径时自动跳过（返回空增量）。
    xmind_reference_loader 为可选节点，仅在启用 XMind 参考时添加。
    knowledge_retrieval 为可选节点，仅在启用知识检索时添加。

    Args:
        llm_client: LLM 客户端实例，传递给需要调用 LLM 的节点。
        project_context_loader: 可选的项目上下文加载节点（闭包 callable），
            插入在 xmind_reference_loader（或 template_loader）之后。
        knowledge_retrieval_node: 可选的知识检索节点（闭包 callable），
            插入在 project_context_loader（或 template_loader）之后、
            context_research 之前。
        xmind_reference_loader_node: 可选的 XMind 参考加载节点（闭包 callable），
            插入在 template_loader 之后、project_context_loader 之前。
        timer: 可选的 ``NodeTimer`` 实例，传入时自动包装每个节点以记录耗时。
        iteration_index: 当前迭代轮次索引，用于在 timer 中区分不同轮次。
        codebase_root: 可选的本地代码库根路径，传递给 MR 分析节点。
        coco_settings: 可选的 CocoSettings 实例，传递给 Coco 相关节点。

    Returns:
        编译后的 LangGraph 可执行工作流。
    """
    case_generation_subgraph = build_case_generation_subgraph(
        llm_client,
        timer=timer,
        iteration_index=iteration_index,
        codebase_root=codebase_root,
        coco_settings=coco_settings,
    )

    # 使用自动状态桥接替代手动字段映射。
    #
    # 设计说明：
    # 1. 入向（主图 -> 子图）默认使用 shared keys 自动转发，降低新增字段时遗漏接线的概率。
    # 2. 出向（子图 -> 主图）必须显式 include_out allowlist，避免子图内部中间态字段
    #    因为“恰好同名”被自动暴露到主图，放宽工作流状态边界。
    # 3. 后续若业务上需要新增某个主图可见输出字段，必须：
    #    - 在 include_out 中显式登记
    #    - 同步补充对应测试，说明该字段成为主图契约的一部分是有意设计。
    case_gen_bridge = build_bridge(
        subgraph=case_generation_subgraph,
        parent_type=GlobalState,
        child_type=CaseGenState,
        override_in={
            "language": "zh-CN",
            "project_context_summary": "",
            "template_leaf_targets": [],
        },
        include_out={
            "planned_scenarios",
            "checkpoints",
            "checkpoint_coverage",
            "draft_cases",
            "test_cases",
            "optimized_tree",
            "coverage_result",
        },
    )

    builder = StateGraph(GlobalState)

    builder.add_node("input_parser", maybe_wrap("input_parser", input_parser_node, timer, iteration_index))
    builder.add_node("template_loader", maybe_wrap("template_loader", build_template_loader_node(), timer, iteration_index))

    if xmind_reference_loader_node is not None:
        builder.add_node("xmind_reference_loader", maybe_wrap("xmind_reference_loader", xmind_reference_loader_node, timer, iteration_index))

    if project_context_loader is not None:
        builder.add_node("project_context_loader", maybe_wrap("project_context_loader", project_context_loader, timer, iteration_index))

    if knowledge_retrieval_node is not None:
        builder.add_node("knowledge_retrieval", maybe_wrap("knowledge_retrieval", knowledge_retrieval_node, timer, iteration_index))

    builder.add_node("context_research", maybe_wrap("context_research", build_context_research_node(llm_client), timer, iteration_index))
    builder.add_node("case_generation", maybe_wrap("case_generation", case_gen_bridge, timer, iteration_index))
    builder.add_node("reflection", maybe_wrap("reflection", reflection_node, timer, iteration_index))

    # 边连接：input_parser → template_loader → [xmind_reference_loader]
    # → [project_context_loader] → [knowledge_retrieval] → context_research
    builder.add_edge(START, "input_parser")
    builder.add_edge("input_parser", "template_loader")

    # 确定 template_loader 之后的链路
    prev_node = "template_loader"

    if xmind_reference_loader_node is not None:
        builder.add_edge(prev_node, "xmind_reference_loader")
        prev_node = "xmind_reference_loader"

    if project_context_loader is not None:
        builder.add_edge(prev_node, "project_context_loader")
        prev_node = "project_context_loader"

    if knowledge_retrieval_node is not None:
        builder.add_edge(prev_node, "knowledge_retrieval")
        prev_node = "knowledge_retrieval"

    builder.add_edge(prev_node, "context_research")
    builder.add_edge("context_research", "case_generation")
    builder.add_edge("case_generation", "reflection")
    builder.add_edge("reflection", END)

    return builder.compile()


# ---- DEPRECATED: 旧手动桥接函数，保留用于回滚 ----
# 如需回滚到手动桥接，将 build_workflow 中的 case_gen_bridge 替换为
# _build_case_generation_bridge(case_generation_subgraph) 即可。
def _build_case_generation_bridge(case_generation_subgraph):  # pragma: no cover
    """[DEPRECATED] 手动桥接节点，已被 state_bridge.build_bridge 替代。

    保留此函数仅用于紧急回滚。正常开发应使用 build_bridge 自动桥接。
    变更：
    - 新增 mandatory_skeleton 字段的传入与传出映射
    - 新增 xmind_reference_summary 字段的传入与传出映射
    - 新增 coverage_result 字段的传出映射
    - 新增 MR 相关字段的传入与传出映射
    """

    def case_generation_node(state: GlobalState) -> GlobalState:
        subgraph_input = {
            "language": state.get("language", "zh-CN"),
            "parsed_document": state["parsed_document"],
            "research_output": state["research_output"],
            "project_context_summary": state.get("project_context_summary", ""),
            "template_leaf_targets": state.get("template_leaf_targets", []),
            "project_template": state.get("project_template"),
            "mandatory_skeleton": state.get("mandatory_skeleton"),
            "xmind_reference_summary": state.get("xmind_reference_summary"),
            # ---- MR 分析相关字段传入子图 ----
            "frontend_mr_config": state.get("frontend_mr_config"),
            "backend_mr_config": state.get("backend_mr_config"),
            "mr_input": state.get("mr_input"),
            "mr_code_facts": state.get("mr_code_facts", []),
            "mr_consistency_issues": state.get("mr_consistency_issues", []),
            "mr_combined_summary": state.get("mr_combined_summary", ""),
            "mr_analysis_result": state.get("mr_analysis_result"),
        }

        subgraph_input = {k: v for k, v in subgraph_input.items() if v is not None}

        subgraph_result = case_generation_subgraph.invoke(subgraph_input)

        return {
            "planned_scenarios": subgraph_result.get("planned_scenarios", []),
            "checkpoints": subgraph_result.get("checkpoints", []),
            "checkpoint_coverage": subgraph_result.get("checkpoint_coverage", []),
            "draft_cases": subgraph_result.get("draft_cases", []),
            "test_cases": subgraph_result.get("test_cases", []),
            "optimized_tree": subgraph_result.get("optimized_tree", []),
            "coverage_result": subgraph_result.get("coverage_result"),
            # ---- MR 分析结果回传 ----
            "mr_analysis_result": subgraph_result.get("mr_analysis_result"),
            "mr_code_facts": subgraph_result.get("mr_code_facts", []),
            "mr_consistency_issues": subgraph_result.get("mr_consistency_issues", []),
            "mr_combined_summary": subgraph_result.get("mr_combined_summary", ""),
            "frontend_mr_result": subgraph_result.get("frontend_mr_result"),
            "backend_mr_result": subgraph_result.get("backend_mr_result"),
        }

    return case_generation_node
