"""用例生成子图定义。

使用 LangGraph 构建测试用例生成的子工作流：
  scenario_planner → checkpoint_generator → checkpoint_evaluator
  → evidence_mapper → draft_writer → structure_assembler → checklist_optimizer

该子图接收 ``CaseGenState``，与主图的 ``GlobalState`` 通过桥接节点交互。
新增的 checkpoint_generator 和 checkpoint_evaluator 节点在 scenario_planner
之后、evidence_mapper 之前执行，将 facts 转化为显式 checkpoints。

F5 变更：在 structure_assembler 之后插入 checklist_optimizer 节点，
执行前置操作合并与文本精炼（F1 + F2），结果写入 optimized_tree。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import CaseGenState
from app.nodes.checklist_optimizer import checklist_optimizer_node
from app.nodes.checkpoint_evaluator import checkpoint_evaluator_node
from app.nodes.checkpoint_generator import build_checkpoint_generator_node
from app.nodes.draft_writer import build_draft_writer_node
from app.nodes.evidence_mapper import evidence_mapper_node
from app.nodes.scenario_planner import scenario_planner_node
from app.nodes.structure_assembler import structure_assembler_node


def build_case_generation_subgraph(llm_client: LLMClient):
    """构建并编译用例生成子图。

    子图结构（线性流水线）：
    ```
    START → scenario_planner → checkpoint_generator → checkpoint_evaluator
          → evidence_mapper → draft_writer → structure_assembler
          → checklist_optimizer → END
    ```

    各节点职责：
    - scenario_planner：从研究输出中规划测试场景
    - checkpoint_generator：将 facts 转化为显式 checkpoints（新增）
    - checkpoint_evaluator：对 checkpoints 去重、归一化（新增）
    - evidence_mapper：为每个场景匹配 PRD 文档证据
    - draft_writer：基于 checkpoints 调用 LLM 生成测试用例草稿
    - structure_assembler：标准化用例结构，补全缺失字段
    - checklist_optimizer：前置操作合并 + 文本精炼（F1 + F2，F5 新增）

    Args:
        llm_client: LLM 客户端实例，传递给需要 LLM 的节点。

    Returns:
        编译后的 LangGraph 可执行子图。
    """
    builder = StateGraph(CaseGenState)

    builder.add_node("scenario_planner", scenario_planner_node)
    builder.add_node("checkpoint_generator", build_checkpoint_generator_node(llm_client))
    builder.add_node("checkpoint_evaluator", checkpoint_evaluator_node)
    builder.add_node("evidence_mapper", evidence_mapper_node)
    builder.add_node("draft_writer", build_draft_writer_node(llm_client))
    builder.add_node("structure_assembler", structure_assembler_node)
    builder.add_node("checklist_optimizer", checklist_optimizer_node)

    builder.add_edge(START, "scenario_planner")
    builder.add_edge("scenario_planner", "checkpoint_generator")
    builder.add_edge("checkpoint_generator", "checkpoint_evaluator")
    builder.add_edge("checkpoint_evaluator", "evidence_mapper")
    builder.add_edge("evidence_mapper", "draft_writer")
    builder.add_edge("draft_writer", "structure_assembler")
    builder.add_edge("structure_assembler", "checklist_optimizer")
    builder.add_edge("checklist_optimizer", END)

    return builder.compile()
