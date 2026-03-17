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
from app.domain.document_models import ParsedDocument
from app.domain.research_models import EvidenceRef, PlannedScenario, ResearchOutput


class GlobalState(TypedDict, total=False):
    """主工作流全局状态。

    贯穿 input_parser → context_research → case_generation → reflection
    四个阶段，每个节点读取所需字段并写回产出字段。
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
    mapped_evidence: dict[str, list[EvidenceRef]]
    draft_cases: list[TestCase]
    test_cases: list[TestCase]
    quality_report: QualityReport
    artifacts: dict[str, str]
    error: ErrorInfo


class CaseGenState(TypedDict, total=False):
    """用例生成子图状态。

    仅包含子图内部流转所需的字段，与 GlobalState 解耦，
    通过主工作流中的桥接节点完成状态映射。
    """

    language: str
    parsed_document: ParsedDocument
    research_output: ResearchOutput
    planned_scenarios: list[PlannedScenario]
    checkpoints: list[Checkpoint]
    checkpoint_coverage: list[CheckpointCoverage]
    mapped_evidence: dict[str, list[EvidenceRef]]
    draft_cases: list[TestCase]
    test_cases: list[TestCase]
