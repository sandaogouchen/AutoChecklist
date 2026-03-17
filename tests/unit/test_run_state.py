"""运行状态模型和仓储的单元测试。"""

from __future__ import annotations

from app.domain.run_state import (
    EvaluationDimension,
    EvaluationReport,
    IterationRecord,
    RetryDecision,
    RunStage,
    RunState,
    RunStatus,
)
from app.repositories.run_state_repository import RunStateRepository


# ===================== 运行状态模型测试 =====================


def test_run_state_defaults() -> None:
    """RunState 模型的默认值应正确设置。"""
    state = RunState(run_id="test-123")

    assert state.status == RunStatus.PENDING
    assert state.current_stage == RunStage.CONTEXT_RESEARCH
    assert state.iteration_index == 0
    assert state.max_iterations == 3
    assert state.last_evaluation_score == 0.0
    assert state.iteration_history == []
    assert state.retry_decisions == []
    assert state.error is None


def test_run_status_enum_values() -> None:
    """RunStatus 枚举应包含 PRD 要求的所有状态。"""
    assert RunStatus.PENDING.value == "pending"
    assert RunStatus.RUNNING.value == "running"
    assert RunStatus.EVALUATING.value == "evaluating"
    assert RunStatus.RETRYING.value == "retrying"
    assert RunStatus.SUCCEEDED.value == "succeeded"
    assert RunStatus.FAILED.value == "failed"


def test_run_stage_enum_values() -> None:
    """RunStage 枚举应包含 PRD 要求的所有阶段。"""
    assert RunStage.CONTEXT_RESEARCH.value == "context_research"
    assert RunStage.CHECKPOINT_GENERATION.value == "checkpoint_generation"
    assert RunStage.DRAFT_GENERATION.value == "draft_generation"
    assert RunStage.EVALUATION.value == "evaluation"
    assert RunStage.OUTPUT_DELIVERY.value == "output_delivery"


def test_evaluation_report_model() -> None:
    """EvaluationReport 模型应正确构建。"""
    report = EvaluationReport(
        overall_score=0.75,
        dimensions=[
            EvaluationDimension(name="fact_coverage", score=0.8),
            EvaluationDimension(name="checkpoint_coverage", score=0.7),
        ],
        critical_failures=["Fact X uncovered"],
        suggested_retry_stage="context_research",
    )

    assert report.overall_score == 0.75
    assert len(report.dimensions) == 2
    assert report.suggested_retry_stage == "context_research"


def test_iteration_record_model() -> None:
    """IterationRecord 模型应正确构建。"""
    record = IterationRecord(
        iteration_index=0,
        stage="context_research",
        evaluation_score=0.65,
        evaluation_summary="需要改进",
        retry_reason="fact 覆盖不足",
        retry_target_stage="context_research",
    )

    assert record.iteration_index == 0
    assert record.evaluation_score == 0.65


def test_retry_decision_model() -> None:
    """RetryDecision 模型应正确构建。"""
    decision = RetryDecision(
        iteration_index=1,
        retry_reason="checkpoint 覆盖不足",
        target_stage="checkpoint_generation",
        trigger_dimension="checkpoint_coverage",
        previous_score=0.45,
    )

    assert decision.target_stage == "checkpoint_generation"
    assert decision.trigger_dimension == "checkpoint_coverage"


def test_run_state_serialization() -> None:
    """RunState 应支持 JSON 序列化和反序列化。"""
    state = RunState(
        run_id="test-123",
        status=RunStatus.RUNNING,
        current_stage=RunStage.EVALUATION,
        iteration_index=1,
        last_evaluation_score=0.65,
        iteration_history=[
            IterationRecord(iteration_index=0, evaluation_score=0.5),
        ],
    )

    json_data = state.model_dump(mode="json")
    restored = RunState.model_validate(json_data)

    assert restored.run_id == "test-123"
    assert restored.status == RunStatus.RUNNING
    assert restored.iteration_index == 1
    assert len(restored.iteration_history) == 1


# ===================== 运行状态仓储测试 =====================


def test_run_state_repository_save_and_load(tmp_path) -> None:
    """RunStateRepository 应能正确保存和加载 run_state。"""
    repo = RunStateRepository(tmp_path)
    state = RunState(
        run_id="test-run",
        status=RunStatus.RUNNING,
        current_stage=RunStage.EVALUATION,
    )

    repo.save_run_state(state)
    loaded = repo.load_run_state("test-run")

    assert loaded.run_id == "test-run"
    assert loaded.status == RunStatus.RUNNING


def test_run_state_repository_save_evaluation_report(tmp_path) -> None:
    """RunStateRepository 应能保存和加载评估报告。"""
    repo = RunStateRepository(tmp_path)
    report = EvaluationReport(
        overall_score=0.75,
        dimensions=[EvaluationDimension(name="fact_coverage", score=0.8)],
    )

    repo.save_evaluation_report("test-run", report, iteration_index=0)
    loaded = repo.load_evaluation_report("test-run")

    assert loaded.overall_score == 0.75
    assert len(loaded.dimensions) == 1


def test_run_state_repository_save_iteration_log(tmp_path) -> None:
    """RunStateRepository 应能保存和加载迭代日志。"""
    repo = RunStateRepository(tmp_path)
    state = RunState(
        run_id="test-run",
        status=RunStatus.SUCCEEDED,
        iteration_history=[
            IterationRecord(iteration_index=0, evaluation_score=0.5),
            IterationRecord(iteration_index=1, evaluation_score=0.8),
        ],
        retry_decisions=[
            RetryDecision(
                iteration_index=1,
                retry_reason="coverage low",
                target_stage="draft_generation",
            ),
        ],
    )

    repo.save_iteration_log(state)
    loaded = repo.load_iteration_log("test-run")

    assert loaded["run_id"] == "test-run"
    assert loaded["total_iterations"] == 2
    assert len(loaded["iterations"]) == 2
    assert len(loaded["retry_decisions"]) == 1


def test_run_state_repository_exists_check(tmp_path) -> None:
    """run_state_exists 应正确判断状态文件是否存在。"""
    repo = RunStateRepository(tmp_path)

    assert not repo.run_state_exists("nonexistent")

    state = RunState(run_id="existing-run")
    repo.save_run_state(state)

    assert repo.run_state_exists("existing-run")


def test_run_state_repository_preserves_history_versions(tmp_path) -> None:
    """保存多轮评估报告时，应同时保留历史版本文件。"""
    repo = RunStateRepository(tmp_path)

    report_0 = EvaluationReport(overall_score=0.5)
    repo.save_evaluation_report("test-run", report_0, iteration_index=0)

    report_1 = EvaluationReport(overall_score=0.7)
    repo.save_evaluation_report("test-run", report_1, iteration_index=1)

    # 主文件应为最新版本
    latest = repo.load_evaluation_report("test-run")
    assert latest.overall_score == 0.7

    # 历史版本应存在
    history_path = tmp_path / "test-run" / "evaluation_report_iter_1.json"
    assert history_path.exists()
