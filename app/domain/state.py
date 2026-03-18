"""LangGraph 状态模型定义。"""
from __future__ import annotations

from typing import Optional, TypedDict

from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint, CheckpointCoverage
from app.domain.document_models import ParsedDocument
from app.domain.project_models import ProjectContext
from app.domain.research_models import PlannedScenario, ResearchFact, ResearchOutput
from app.domain.run_state import EvaluationReport


class GlobalState(TypedDict, total=False):
    """主工作流全局状态。"""
    raw_input: str
    file_path: str
    language: str
    parsed_document: ParsedDocument
    research_output: ResearchOutput
    facts: list[ResearchFact]
    scenarios: list[PlannedScenario]
    checkpoints: list[Checkpoint]
    coverage: CheckpointCoverage
    test_cases: list[TestCase]
    evaluation_report: Optional[EvaluationReport]
    project_context: Optional[ProjectContext]
    project_id: Optional[str]
    llm_config: Optional[dict]
    iteration_index: int
    max_iterations: int
    # ---- 模板驱动生成支持 ----
    template: Optional[dict]          # 已加载的模板数据（序列化后的 dict）
    template_id: Optional[str]        # 请求中指定的模板 ID


class CaseGenState(TypedDict, total=False):
    """用例生成子图状态。"""
    checkpoints: list[Checkpoint]
    scenarios: list[PlannedScenario]
    facts: list[ResearchFact]
    test_cases: list[TestCase]
    parsed_document: ParsedDocument
    project_context: Optional[ProjectContext]
    language: str
    llm_config: Optional[dict]
    iteration_index: int
    # ---- 模板驱动生成支持 ----
    template: Optional[dict]          # 从主状态桥接而来的模板数据
