"""工作流状态定义模块。

使用 TypedDict 定义 LangGraph 工作流中流转的状态结构：
- ``GlobalState``：主工作流的全局状态
- ``CaseGenState``：用例生成子图的局部状态

TypedDict 的 ``total=False`` 表示所有字段均为可选，
这与 LangGraph 的增量更新模式一致——每个节点只需返回自己修改的字段。

新增模版相关状态字段，支持项目级 Checklist 模版的加载与传递。
新增 mandatory_skeleton 字段，支持强制层级约束在管道中传播。
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
from app.domain.template_models import (
    MandatorySkeletonNode,
    ProjectChecklistTemplateFile,
    TemplateLeafTarget,
)


class GlobalState(TypedDict, total=False):
    """主工作流全局状态。

    新增字段：
    - optimized_tree: 前置条件分组优化后的 ChecklistNode 树
    - template_file_path: 项目级 Checklist 模版文件路径
    - project_template: 解析后的模版文件对象
    - template_leaf_targets: 拍平后的模版叶子目标列表
    - mandatory_skeleton: 强制骨架树（从模版中提取的强制节点子树）
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

    # ---- 模版相关字段 ----
    template_file_path: str
    project_template: ProjectChecklistTemplateFile
    template_leaf_targets: list[TemplateLeafTarget]

    # ---- 强制骨架字段 ----
    mandatory_skeleton: MandatorySkeletonNode


class CaseGenState(TypedDict, total=False):
    """用例生成子图状态。

    新增字段：
    - optimized_tree: 前置条件分组优化后的 ChecklistNode 树
    - template_leaf_targets: 拍平后的模版叶子目标列表
    - project_template: 解析后的模版文件对象
    - mandatory_skeleton: 强制骨架树
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

    # ---- 模版相关字段 ----
    template_leaf_targets: list[TemplateLeafTarget]
    project_template: ProjectChecklistTemplateFile

    # ---- 强制骨架字段 ----
    mandatory_skeleton: MandatorySkeletonNode
