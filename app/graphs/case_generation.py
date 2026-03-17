"""用例生成子图定义。

使用 LangGraph 构建测试用例生成的子工作流：
  scenario_planner → evidence_mapper → draft_writer → structure_assembler

该子图接收 ``CaseGenState``，与主图的 ``GlobalState`` 通过桥接节点交互。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.clients.llm import LLMClient
from app.domain.state import CaseGenState
from app.nodes.draft_writer import build_draft_writer_node
from app.nodes.evidence_mapper import evidence_mapper_node
from app.nodes.scenario_planner import scenario_planner_node
from app.nodes.structure_assembler import structure_assembler_node


def build_case_generation_subgraph(llm_client: LLMClient):
    """构建并编译用例生成子图。

    子图结构（线性流水线）：
    ```
    START → scenario_planner → evidence_mapper → draft_writer → structure_assembler → END
    ```

    各节点职责：
    - scenario_planner：从研究输出中规划测试场景
    - evidence_mapper：为每个场景匹配 PRD 文档证据
    - draft_writer：调用 LLM 生成测试用例草稿
    - structure_assembler：标准化用例结构，补全缺失字段

    Args:
        llm_client: LLM 客户端实例，传递给 draft_writer 节点。

    Returns:
        编译后的 LangGraph 可执行子图。
    """
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
