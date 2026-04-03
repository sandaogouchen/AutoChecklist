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
- 新增可选 codebase_root / coco_settings 参数，支持 MR 代码分析
- 桥接节点新增 MR 相关字段映射（mr_input, mr_code_facts, mr_consistency_issues 等）
"""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import GlobalState
from app.graphs.case_generation import build_case_generation_subgraph
from app.nodes.context_research import build_context_research_node
from app.nodes.input_parser import input_parser_node
from app.nodes.reflection import reflection_node
from app.nodes.template_loader import build_template_loader_node
from app.utils.timing import maybe_wrap

logger = logging.getLogger(__name__)


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
    builder.add_node("case_generation", maybe_wrap("case_generation", _build_case_generation_bridge(case_generation_subgraph), timer, iteration_index))
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


def _build_case_generation_bridge(case_generation_subgraph):
    """构建主图与用例生成子图之间的桥接节点。

    变更：
    - 新增 mandatory_skeleton 字段的传入与传出映射
    - 新增 xmind_reference_summary 字段的传入与传出映射
    - 新增 coverage_result 字段的传出映射
    - 新增 MR 相关字段的传入与传出映射
    """

    def case_generation_node(state: GlobalState) -> GlobalState:
        subgraph_input = {
            "run_id": state.get("run_id"),
            "run_output_dir": state.get("run_output_dir"),
            "language": state.get("language", "zh-CN"),
            "parsed_document": state["parsed_document"],
            "research_output": state["research_output"],
            "project_context_summary": state.get("project_context_summary", ""),
            # ---- 模版相关字段传入子图 ----
            "template_leaf_targets": state.get("template_leaf_targets", []),
            "project_template": state.get("project_template"),
            # ---- 强制骨架传入子图 ----
            "mandatory_skeleton": state.get("mandatory_skeleton"),
            # ---- XMind 参考传入子图 ----
            "xmind_reference_summary": state.get("xmind_reference_summary"),
            # ---- MR 分析相关字段传入子图 ----
            "frontend_mr_config": state.get("frontend_mr_config"),
            "backend_mr_config": state.get("backend_mr_config"),
            "mr_input": state.get("mr_input"),
            "mr_code_facts": state.get("mr_code_facts", []),
            "mr_consistency_issues": state.get("mr_consistency_issues", []),
            "mr_combined_summary": state.get("mr_combined_summary", ""),
            "mr_analysis_result": state.get("mr_analysis_result"),
            "coco_cache_dir": state.get("coco_cache_dir", ""),
            "coco_cache_run_id": state.get("coco_cache_run_id", ""),
        }

        # 清理 None 值
        subgraph_input = {k: v for k, v in subgraph_input.items() if v is not None}

        try:
            subgraph_result = case_generation_subgraph.invoke(subgraph_input)
        except Exception as exc:
            logger.exception(
                "case_generation subgraph failed: error_type=%s, input_keys=%s, "
                "has_frontend_mr=%s, has_backend_mr=%s, has_mr_input=%s",
                exc.__class__.__name__,
                sorted(subgraph_input.keys()),
                bool(subgraph_input.get("frontend_mr_config")),
                bool(subgraph_input.get("backend_mr_config")),
                bool(subgraph_input.get("mr_input")),
            )
            raise

        return {
            "research_output": subgraph_result.get("research_output", state["research_output"]),
            "planned_scenarios": subgraph_result.get("planned_scenarios", []),
            "checkpoints": subgraph_result.get("checkpoints", []),
            "checkpoint_coverage": subgraph_result.get("checkpoint_coverage", []),
            "checkpoint_paths": subgraph_result.get("checkpoint_paths", []),
            "canonical_outline_nodes": subgraph_result.get("canonical_outline_nodes", []),
            "mapped_evidence": subgraph_result.get("mapped_evidence", {}),
            "draft_cases": subgraph_result.get("draft_cases", []),
            "test_cases": subgraph_result.get("test_cases", []),
            "optimized_tree": subgraph_result.get("optimized_tree", []),
            # ---- 覆盖检测结果回传 ----
            "coverage_result": subgraph_result.get("coverage_result"),
            # ---- MR 分析结果回传 ----
            "mr_analysis_result": subgraph_result.get("mr_analysis_result"),
            "mr_code_facts": subgraph_result.get("mr_code_facts", []),
            "mr_consistency_issues": subgraph_result.get("mr_consistency_issues", []),
            "mr_combined_summary": subgraph_result.get("mr_combined_summary", ""),
            "frontend_mr_result": subgraph_result.get("frontend_mr_result"),
            "backend_mr_result": subgraph_result.get("backend_mr_result"),
            "coco_validation_summary": subgraph_result.get("coco_validation_summary", {}),
            "coco_artifacts": subgraph_result.get("coco_artifacts", {}),
            "coco_cache_dir": subgraph_result.get("coco_cache_dir", state.get("coco_cache_dir", "")),
            "coco_cache_run_id": subgraph_result.get("coco_cache_run_id", state.get("coco_cache_run_id", "")),
        }

    return case_generation_node
