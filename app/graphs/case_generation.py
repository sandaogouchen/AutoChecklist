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
- CaseGenState 新增 abstracted_reference_schema 字段，
  由主图桥接传入，供 checkpoint_outline_planner 使用维度引导
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import CaseGenState
from app.nodes.checkpoint_evaluator import checkpoint_evaluator_node
from app.nodes.checkpoint_generator import build_checkpoint_generator_node
from app.nodes.draft_writer import DraftWriterNode
from app.nodes.evidence_mapper import evidence_mapper_node
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
):
    """构建并编译用例生成子图。

    子图结构（线性流水线）：
    ```
    START → scenario_planner → checkpoint_generator → checkpoint_evaluator
    → coverage_detector → checkpoint_outline_planner → evidence_mapper
    → draft_writer → structure_assembler → END
    ```

    各节点职责：
    - scenario_planner：从研究输出中规划测试场景
    - checkpoint_generator：将 facts 转化为显式 checkpoints
    - checkpoint_evaluator：对 checkpoints 去重、归一化
    - coverage_detector：检测 checkpoint 与参考 XMind 叶子的覆盖关系
    - checkpoint_outline_planner：为 checkpoints 规划共享层级并构建 optimized_tree
      （改造后使用维度引导式全量规划，通过 abstracted_reference_schema 获取维度引导）
    - evidence_mapper：为每个场景匹配 PRD 文档证据
    - draft_writer：基于 checkpoint 与固定路径上下文生成叶子级草稿
    - structure_assembler：标准化用例结构，补全缺失字段

    状态字段说明：
    - abstracted_reference_schema 由主图通过桥接节点传入 CaseGenState，
      在子图中作为透传字段流转到 checkpoint_outline_planner 节点使用。
      子图内部无需额外处理该字段——它通过 CaseGenState TypedDict 自然流转。

    Args:
        llm_client: LLM 客户端实例，传递给需要 LLM 的节点。
        timer: 可选的 ``NodeTimer`` 实例，传入时自动包装每个节点以记录耗时。
        iteration_index: 当前迭代轮次索引。

    Returns:
        编译后的 LangGraph 可执行子图。
    """
    builder = StateGraph(CaseGenState)

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
    builder.add_node("structure_assembler", maybe_wrap("structure_assembler", structure_assembler_node, timer, iteration_index))

    builder.add_edge(START, "scenario_planner")
    builder.add_edge("scenario_planner", "checkpoint_generator")
    builder.add_edge("checkpoint_generator", "checkpoint_evaluator")
    builder.add_edge("checkpoint_evaluator", "coverage_detector")
    builder.add_edge("coverage_detector", "checkpoint_outline_planner")
    builder.add_edge("checkpoint_outline_planner", "evidence_mapper")
    builder.add_edge("evidence_mapper", "draft_writer")
    builder.add_edge("draft_writer", "structure_assembler")
    builder.add_edge("structure_assembler", END)

    return builder.compile()
