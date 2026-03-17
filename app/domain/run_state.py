"""运行状态领域模型。

定义了迭代评估回路中的核心状态模型，包括：
- ``RunStatus``：运行状态枚举
- ``RunStage``：运行阶段枚举
- ``EvaluationDimension``：单个评估维度结果
- ``EvaluationReport``：结构化评估报告
- ``IterationRecord``：单轮迭代记录
- ``RetryDecision``：回流决策
- ``RunState``：完整运行状态对象
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    """运行状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    EVALUATING = "evaluating"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunStage(str, Enum):
    """运行阶段枚举。"""

    CONTEXT_RESEARCH = "context_research"
    CHECKPOINT_GENERATION = "checkpoint_generation"
    DRAFT_GENERATION = "draft_generation"
    EVALUATION = "evaluation"
    OUTPUT_DELIVERY = "output_delivery"


class EvaluationDimension(BaseModel):
    """单个评估维度的结果。"""

    name: str
    score: float = 0.0
    max_score: float = 1.0
    details: str = ""
    failed_items: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """结构化评估报告。

    对应 PRD 要求的 evaluation_report.json，
    包含总体分数、各维度分数、关键失败项、建议回流阶段等。
    """

    overall_score: float = 0.0
    dimensions: list[EvaluationDimension] = Field(default_factory=list)
    critical_failures: list[str] = Field(default_factory=list)
    suggested_retry_stage: str | None = None
    improvement_summary: str = ""
    comparison_with_previous: str = ""
    pass_threshold: float = 0.7


class RetryDecision(BaseModel):
    """回流决策记录。

    记录每次回流的原因、目标阶段和触发条件。
    """

    iteration_index: int
    retry_reason: str
    target_stage: str
    trigger_dimension: str = ""
    previous_score: float = 0.0
    timestamp: str = ""


class IterationRecord(BaseModel):
    """单轮迭代记录。

    对应 PRD 要求的 iteration_log.json 中的一条记录。
    """

    iteration_index: int
    stage: str = ""
    evaluation_score: float = 0.0
    evaluation_summary: str = ""
    retry_reason: str = ""
    retry_target_stage: str = ""
    artifacts_snapshot: dict[str, str] = Field(default_factory=dict)
    timestamp: str = ""


class RunState(BaseModel):
    """完整运行状态对象。

    对应 PRD 要求的 run_state.json，为每个 run 维护可持久化的状态。
    包含 run_id、status、current_stage、迭代信息、评估信息和工件路径。
    """

    run_id: str
    status: RunStatus = RunStatus.PENDING
    current_stage: RunStage = RunStage.CONTEXT_RESEARCH
    iteration_index: int = 0
    max_iterations: int = 3
    last_evaluation_score: float = 0.0
    last_evaluation_summary: str = ""
    retry_reason: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)
    timestamps: dict[str, str] = Field(default_factory=dict)
    iteration_history: list[IterationRecord] = Field(default_factory=list)
    retry_decisions: list[RetryDecision] = Field(default_factory=list)
    error: dict[str, Any] | None = None
