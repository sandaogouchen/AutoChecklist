"""用例生成子图定义。
使用 LangGraph 构建测试用例生成的子工作流：
scenario_planner → checkpoint_generator → checkpoint_evaluator
→ coverage_detector → checkpoint_outline_planner → evidence_mapper
→ draft_writer → structure_assembler
其中 ``coverage_detector`` 检测 checkpoint 与参考 XMind 叶子的覆盖关系。
其中 ``checkpoint_outline_planner`` 在 testcase 草稿前规划共享层级，
提前产出稳定的 ``optimized_tree``。

变更：
- 新增可选 timer / iteration_index 参数，支持子图内节点级耗时计量
- 新增可选 mr_analyzer / mr_checkpoint_injector / coco_consistency_validator 节点，
  支持 MR 代码分析流水线
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import CaseGenState
from app.nodes.checkpoint_evaluator import checkpoint_evaluator_node
from app.nodes.checkpoint_generator import build_checkpoint_generator_node
from app.nodes.coco_consistency_validator import build_coco_consistency_validator_node
from app.nodes.draft_writer import DraftWriterNode
from app.nodes.evidence_mapper import evidence_mapper_node
from app.nodes.mr_analyzer import build_mr_analyzer_node
from app.nodes.mr_checkpoint_injector import build_mr_checkpoint_injector_node
from app.nodes.scenario_planner import scenario_planner_node
from app.nodes.structure_assembler import structure_assembler_node
from app.services.checkpoint_outline_planner import build_checkpoint_outline_planner_node
from app.services.coverage_detector import CoverageDetector
from app.utils.timing import maybe_wrap


def _coverage_detector_node(state: dict) -> dict:
    """检测 checkpoint 与参考 XMind 叶子的覆盖关系。"""
    xmind_summary = state.get("xmind_reference_summary")
    checkpoints = state.get("checkpoints", [])

    if not xmind_summary or not getattr(xmind_summary, "all_leaf_titles", None):
        return {
            "coverage_result": None,
            "uncovered_checkpoints": checkpoints,
        }

    detector = CoverageDetector()
    result = detector.detect(checkpoints, xmind_summary.all_leaf_titles)

    uncovered = [
        cp for cp in checkpoints
        if getattr(cp, "id", "") not in set(result.covered_checkpoint_ids)
    ]

    return {
        "coverage_result": result,
        "uncovered_checkpoints": uncovered,
    }


def build_case_generation_subgraph(
    llm_client: LLMClient,
    timer=None,
    iteration_index: int = 0,
    codebase_root: str | None = None,
    coco_settings=None,
):
    """构建并编译用例生成子图。

    子图结构（线性流水线）：
    ```
    START → mr_analyzer → scenario_planner
    → checkpoint_generator → checkpoint_evaluator → mr_checkpoint_injector
    → coverage_detector → checkpoint_outline_planner → evidence_mapper
    → draft_writer → coco_consistency_validator → structure_assembler → END
    ```

    各节点职责：
    - mr_analyzer：分析 MR 代码变更，提取代码事实（可选）
    - mr_checkpoint_injector：将 MR 代码事实转换为 checkpoint 并注入（可选）
    - scenario_planner：从研究输出中规划测试场景
    - checkpoint_generator：将 facts 转化为显式 checkpoints
    - checkpoint_evaluator：对 checkpoints 去重、归一化
    - coverage_detector：检测 checkpoint 与参考 XMind 叶子的覆盖关系
    - checkpoint_outline_planner：为 checkpoints 规划共享层级并构建 optimized_tree
    - evidence_mapper：为每个场景匹配 PRD 文档证据
    - draft_writer：基于 checkpoint 与固定路径上下文生成叶子级草稿
    - coco_consistency_validator：通过 Coco Agent 验证 checkpoint 与代码一致性（可选）
    - structure_assembler：标准化用例结构，补全缺失字段

    Args:
        llm_client: LLM 客户端实例，传递给需要 LLM 的节点。
        timer: 可选的 ``NodeTimer`` 实例，传入时自动包装每个节点以记录耗时。
        iteration_index: 当前迭代轮次索引。
        codebase_root: 可选的本地代码库根路径，传递给 mr_analyzer。
        coco_settings: 可选的 CocoSettings 实例，传递给 coco_consistency_validator。

    Returns:
        编译后的 LangGraph 可执行子图。
    """
    builder = StateGraph(CaseGenState)

    # ---- MR 分析节点（可选） ----
    mr_analyzer_node = build_mr_analyzer_node(
        llm_client=llm_client,
        codebase_root=codebase_root,
        coco_settings=coco_settings,
    )
    builder.add_node("mr_analyzer", maybe_wrap("mr_analyzer", mr_analyzer_node, timer, iteration_index))

    mr_checkpoint_injector_node = build_mr_checkpoint_injector_node()
    builder.add_node("mr_checkpoint_injector", maybe_wrap("mr_checkpoint_injector", mr_checkpoint_injector_node, timer, iteration_index))

    builder.add_node("scenario_planner", maybe_wrap("scenario_planner", scenario_planner_node, timer, iteration_index))
    builder.add_node("checkpoint_generator", maybe_wrap("checkpoint_generator", build_checkpoint_generator_node(llm_client), timer, iteration_index))
    builder.add_node("checkpoint_evaluator", maybe_wrap("checkpoint_evaluator", checkpoint_evaluator_node, timer, iteration_index))
    builder.add_node("coverage_detector", maybe_wrap("coverage_detector", _coverage_detector_node, timer, iteration_index))
    builder.add_node(
        "checkpoint_outline_planner",
        maybe_wrap("checkpoint_outline_planner", build_checkpoint_outline_planner_node(llm_client), timer, iteration_index),
    )
    builder.add_node("evidence_mapper", maybe_wrap("evidence_mapper", evidence_mapper_node, timer, iteration_index))
    builder.add_node("draft_writer", maybe_wrap("draft_writer", DraftWriterNode(llm_client), timer, iteration_index))

    # ---- Coco 一致性验证节点（可选） ----
    coco_validator_node = build_coco_consistency_validator_node(
        llm_client=llm_client,
        coco_settings=coco_settings,
    )
    builder.add_node("coco_consistency_validator", maybe_wrap("coco_consistency_validator", coco_validator_node, timer, iteration_index))

    builder.add_node("structure_assembler", maybe_wrap("structure_assembler", structure_assembler_node, timer, iteration_index))

    # ---- 边连接 ----
    builder.add_edge(START, "mr_analyzer")
    builder.add_edge("mr_analyzer", "scenario_planner")
    builder.add_edge("scenario_planner", "checkpoint_generator")
    builder.add_edge("checkpoint_generator", "checkpoint_evaluator")
    builder.add_edge("checkpoint_evaluator", "mr_checkpoint_injector")
    builder.add_edge("mr_checkpoint_injector", "coverage_detector")
    builder.add_edge("coverage_detector", "checkpoint_outline_planner")
    builder.add_edge("checkpoint_outline_planner", "evidence_mapper")
    builder.add_edge("evidence_mapper", "draft_writer")
    builder.add_edge("draft_writer", "coco_consistency_validator")
    builder.add_edge("coco_consistency_validator", "structure_assembler")
    builder.add_edge("structure_assembler", END)

    return builder.compile()
