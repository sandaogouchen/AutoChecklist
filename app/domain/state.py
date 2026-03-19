"""工作流状态定义模块。

使用 TypedDict 定义 LangGraph 工作流中流转的状态结构：
- ``GlobalState``：主工作流的全局状态
- ``CaseGenState``：用例生成子图的局部状态

TypedDict 的 ``total=False`` 表示所有字段均为可选，
这与 LangGraph 的增量更新模式一致——每个节点只需返回自己修改的字段。
"""

from __future__ import annotations

from typing import TypedDict

from app.domain.api_models import CaseGenerationRequest, ErrorInfo, ModelConfigOverride
from app.domain.case_models import QualityReport, TestCase
from app.domain.checkpoint_models import Checkpoint, CheckpointCoverage
from app.domain.checklist_models import (
    CanonicalOutlineNode,
    ChecklistNode,
    CheckpointPathMapping,
)
from app.domain.document_models import ParsedDocument
from app.domain.research_models import EvidenceRef, PlannedScenario, ResearchOutput
from app.domain.run_state import EvaluationReport, RunState


class GlobalState(TypedDict, total=False):
    """主工作流全局状态。

    新增字段：
    - optimized_tree: 前置条件分组优化后的 ChecklistNode 树
    """

    run_id: str
    file_path: str
    language: str
    request: CaseGenerationRequest
    model_config: ModelConfigOverride
    parsed_document: ParsedDocument
    research_output: ResearchOutput
    planned_scenarios: list[PlannedScenario]
    checkpoints: list[Checkpoint]
    checkpoint_coverage: list[CheckpointCoverage]
    checkpoint_paths: list[CheckpointPathMapping]
    canonical_outline_nodes: list[CanonicalOutlineNode]
    mapped_evidence: dict[str, list[EvidenceRef]]
    draft_cases: list[TestCase]
    test_cases: list[TestCase]
    optimized_tree: list[ChecklistNode]
    quality_report: QualityReport
    artifacts: dict[str, str]
    error: ErrorInfo

    # ---- 迭代评估回路字段 ----
    run_state: RunState
    evaluation_report: EvaluationReport
    iteration_index: int

    # ---- 项目上下文字段 ----
    project_id: str
    project_context_summary: str

    # ---- 模板驱动生成支持 ----
    template: dict | None
    template_id: str | None


class CaseGenState(TypedDict, total=False):
    """用例生成子图状态。

    新增字段：
    - optimized_tree: 前置条件分组优化后的 ChecklistNode 树
    """

    language: str
    parsed_document: ParsedDocument
    research_output: ResearchOutput
    planned_scenarios: list[PlannedScenario]
    checkpoints: list[Checkpoint]
    checkpoint_coverage: list[CheckpointCoverage]
    checkpoint_paths: list[CheckpointPathMapping]
    canonical_outline_nodes: list[CanonicalOutlineNode]
    mapped_evidence: dict[str, list[EvidenceRef]]
    draft_cases: list[TestCase]
    test_cases: list[TestCase]
    optimized_tree: list[ChecklistNode]
    project_context_summary: str

    # ---- 模板驱动生成支持 ----
    template: dict | None
