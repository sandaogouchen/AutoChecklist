"""评估节点和迭代控制器的单元测试。"""

from __future__ import annotations

from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint
from app.domain.research_models import EvidenceRef, ResearchFact, ResearchOutput
from app.domain.run_state import (
    EvaluationReport,
    IterationRecord,
    RunStage,
    RunState,
    RunStatus,
)
from app.nodes.evaluation import evaluate
from app.services.iteration_controller import IterationController, IterationDecision


# ===================== 评估节点测试 =====================


def test_evaluate_returns_structured_report() -> None:
    """evaluate() 应返回结构化评估报告。"""
    test_cases = [
        TestCase(
            id="TC-001",
            title="Login test",
            steps=["Open page"],
            expected_results=["Success"],
            checkpoint_id="CP-001",
            evidence_refs=[
                EvidenceRef(section_title="Login", excerpt="test", confidence=0.9)
            ],
        )
    ]
    checkpoints = [
        Checkpoint(
            checkpoint_id="CP-001",
            title="Verify login",
            fact_ids=["FACT-001"],
        )
    ]
    research = ResearchOutput(
        facts=[
            ResearchFact(
                fact_id="FACT-001",
                description="User can log in",
                category="behavior",
            )
        ]
    )

    report = evaluate(
        test_cases=test_cases,
        checkpoints=checkpoints,
        research_output=research,
    )

    assert isinstance(report, EvaluationReport)
    assert report.overall_score > 0
    assert len(report.dimensions) == 6
    dim_names = {d.name for d in report.dimensions}
    assert "fact_coverage" in dim_names
    assert "checkpoint_coverage" in dim_names
    assert "evidence_completeness" in dim_names
    assert "duplicate_rate" in dim_names
    assert "case_completeness" in dim_names
    assert "branch_coverage" in dim_names


def test_evaluate_detects_uncovered_facts() -> None:
    """evaluate() 应检测出未被 checkpoint 覆盖的 facts。"""
    test_cases = []
    checkpoints = [
        Checkpoint(checkpoint_id="CP-001", title="Verify login", fact_ids=["FACT-001"])
    ]
    research = ResearchOutput(
        facts=[
            ResearchFact(fact_id="FACT-001", description="Login", category="behavior"),
            ResearchFact(fact_id="FACT-002", description="Logout", category="behavior"),
        ]
    )

    report = evaluate(
        test_cases=test_cases,
        checkpoints=checkpoints,
        research_output=research,
    )

    fact_dim = next(d for d in report.dimensions if d.name == "fact_coverage")
    assert fact_dim.score < 1.0
    assert any("FACT-002" in item for item in fact_dim.failed_items)


def test_evaluate_detects_uncovered_checkpoints() -> None:
    """evaluate() 应检测出未被 testcase 覆盖的 checkpoints。"""
    test_cases = [
        TestCase(
            id="TC-001",
            title="Test A",
            steps=["Step 1"],
            expected_results=["Result"],
            checkpoint_id="CP-001",
        )
    ]
    checkpoints = [
        Checkpoint(checkpoint_id="CP-001", title="Check A"),
        Checkpoint(checkpoint_id="CP-002", title="Check B"),
    ]

    report = evaluate(test_cases=test_cases, checkpoints=checkpoints)

    cp_dim = next(d for d in report.dimensions if d.name == "checkpoint_coverage")
    assert cp_dim.score == 0.5
    assert any("CP-002" in item for item in cp_dim.failed_items)


def test_evaluate_detects_missing_evidence() -> None:
    """evaluate() 应检测缺少 evidence 引用的 testcase。"""
    test_cases = [
        TestCase(
            id="TC-001",
            title="Test A",
            steps=["Step 1"],
            expected_results=["Result"],
            evidence_refs=[],
        )
    ]

    report = evaluate(test_cases=test_cases, checkpoints=[])

    ev_dim = next(d for d in report.dimensions if d.name == "evidence_completeness")
    assert ev_dim.score == 0.0


def test_evaluate_detects_duplicates() -> None:
    """evaluate() 应检测重复标题的 testcase。"""
    test_cases = [
        TestCase(id="TC-001", title="Login test", steps=["Step 1"], expected_results=["OK"]),
        TestCase(id="TC-002", title="Login test", steps=["Step 2"], expected_results=["OK"]),
    ]

    report = evaluate(test_cases=test_cases, checkpoints=[])

    dup_dim = next(d for d in report.dimensions if d.name == "duplicate_rate")
    assert dup_dim.score < 1.0


def test_evaluate_detects_incomplete_cases() -> None:
    """evaluate() 应检测缺步骤或缺预期结果的 testcase。"""
    test_cases = [
        TestCase(id="TC-001", title="Test A", steps=[], expected_results=["Result"]),
        TestCase(id="TC-002", title="Test B", steps=["Step 1"], expected_results=[]),
    ]

    report = evaluate(test_cases=test_cases, checkpoints=[])

    comp_dim = next(d for d in report.dimensions if d.name == "case_completeness")
    assert comp_dim.score == 0.0


def test_evaluate_suggests_retry_stage_for_low_fact_coverage() -> None:
    """当 fact 覆盖率低时，应建议回到 context_research。"""
    research = ResearchOutput(
        facts=[
            ResearchFact(fact_id="FACT-001", description="A", category="behavior"),
            ResearchFact(fact_id="FACT-002", description="B", category="behavior"),
            ResearchFact(fact_id="FACT-003", description="C", category="behavior"),
        ]
    )
    checkpoints = [
        Checkpoint(checkpoint_id="CP-001", title="Check A", fact_ids=["FACT-001"])
    ]

    report = evaluate(
        test_cases=[], checkpoints=checkpoints, research_output=research
    )

    assert report.suggested_retry_stage == "context_research"


def test_evaluate_comparison_with_previous() -> None:
    """有前一轮分数时，应生成比较说明。"""
    test_cases = [
        TestCase(
            id="TC-001",
            title="Test",
            steps=["Step"],
            expected_results=["Result"],
            checkpoint_id="CP-001",
            evidence_refs=[EvidenceRef(section_title="S", excerpt="E", confidence=0.9)],
        )
    ]
    checkpoints = [Checkpoint(checkpoint_id="CP-001", title="Check", fact_ids=["F1"])]

    report = evaluate(
        test_cases=test_cases,
        checkpoints=checkpoints,
        previous_score=0.3,
    )

    assert report.comparison_with_previous != ""


# ===================== 迭代控制器测试 =====================


def test_controller_passes_on_high_score() -> None:
    """分数达到阈值时，控制器应返回 pass。"""
    controller = IterationController(pass_threshold=0.7)
    state = controller.initialize_state("test-run")

    evaluation = EvaluationReport(overall_score=0.85)
    decision = controller.decide(state, evaluation)

    assert decision.action == "pass"


def test_controller_retries_on_low_score() -> None:
    """分数未达阈值且未到最大轮次时，控制器应返回 retry。"""
    controller = IterationController(max_iterations=3, pass_threshold=0.7)
    state = controller.initialize_state("test-run")

    evaluation = EvaluationReport(
        overall_score=0.4,
        suggested_retry_stage="draft_generation",
    )
    decision = controller.decide(state, evaluation)

    assert decision.action == "retry"
    assert decision.target_stage == "draft_generation"


def test_controller_fails_on_max_iterations() -> None:
    """达到最大迭代次数时，控制器应返回 fail。"""
    controller = IterationController(max_iterations=2, pass_threshold=0.9)
    state = controller.initialize_state("test-run")
    state.iteration_index = 1  # 已经是最后一轮

    evaluation = EvaluationReport(overall_score=0.5)
    decision = controller.decide(state, evaluation)

    assert decision.action == "fail"


def test_controller_fails_on_no_improvement_streak() -> None:
    """连续两轮无明显改进时，控制器应返回 fail。"""
    controller = IterationController(
        max_iterations=5, pass_threshold=0.9, min_improvement=0.03
    )
    state = controller.initialize_state("test-run")

    # 模拟两轮历史记录，分数基本没变
    state.iteration_history = [
        IterationRecord(iteration_index=0, evaluation_score=0.5),
        IterationRecord(iteration_index=1, evaluation_score=0.51),
    ]
    state.iteration_index = 2

    evaluation = EvaluationReport(overall_score=0.52)
    decision = controller.decide(state, evaluation)

    assert decision.action == "fail"
    assert "无明显改进" in decision.reason


def test_controller_update_state_after_pass() -> None:
    """pass 决策后，状态应更新为 succeeded。"""
    controller = IterationController()
    state = controller.initialize_state("test-run")

    evaluation = EvaluationReport(overall_score=0.85)
    decision = IterationDecision(action="pass", reason="达标")

    updated = controller.update_state_after_evaluation(state, evaluation, decision)

    assert updated.status == RunStatus.SUCCEEDED
    assert updated.current_stage == RunStage.OUTPUT_DELIVERY
    assert len(updated.iteration_history) == 1
    assert "completed_at" in updated.timestamps


def test_controller_update_state_after_retry() -> None:
    """retry 决策后，状态应更新为 retrying。"""
    controller = IterationController()
    state = controller.initialize_state("test-run")

    evaluation = EvaluationReport(
        overall_score=0.4,
        suggested_retry_stage="checkpoint_generation",
    )
    decision = IterationDecision(
        action="retry",
        reason="覆盖不足",
        target_stage="checkpoint_generation",
    )

    updated = controller.update_state_after_evaluation(state, evaluation, decision)

    assert updated.status == RunStatus.RETRYING
    assert updated.current_stage == RunStage.CHECKPOINT_GENERATION
    assert updated.iteration_index == 1
    assert len(updated.retry_decisions) == 1
    assert updated.retry_decisions[0].target_stage == "checkpoint_generation"


def test_controller_update_state_after_fail() -> None:
    """fail 决策后，状态应更新为 failed。"""
    controller = IterationController()
    state = controller.initialize_state("test-run")

    evaluation = EvaluationReport(overall_score=0.3)
    decision = IterationDecision(action="fail", reason="超过最大轮次")

    updated = controller.update_state_after_evaluation(state, evaluation, decision)

    assert updated.status == RunStatus.FAILED
    assert "failed_at" in updated.timestamps


def test_controller_mark_error() -> None:
    """mark_error 应将状态设为 failed 并记录错误信息。"""
    controller = IterationController()
    state = controller.initialize_state("test-run")

    error = ValueError("Something went wrong")
    updated = controller.mark_error(state, error)

    assert updated.status == RunStatus.FAILED
    assert updated.error is not None
    assert updated.error["code"] == "ValueError"
    assert "failed_at" in updated.timestamps
