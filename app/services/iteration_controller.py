"""迭代控制器模块。

负责管理迭代评估回路的控制逻辑，决定：
- 当前结果是否足够好，可以结束
- 是否需要回流到上游某个阶段重做
- 是否已经达到最大迭代次数，必须停止
- 是否因为多轮无改进而提前终止

支持的停止条件：
- 达到质量阈值
- 达到最大迭代数
- 连续两轮无明显改进
- 出现不可恢复错误
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from app.domain.run_state import (
    EvaluationReport,
    IterationRecord,
    RetryDecision,
    RunStage,
    RunState,
    RunStatus,
)


class IterationDecision:
    """迭代决策结果。"""

    def __init__(
        self,
        action: Literal["pass", "retry", "fail"],
        reason: str = "",
        target_stage: str = "",
    ) -> None:
        self.action = action
        self.reason = reason
        self.target_stage = target_stage


class IterationController:
    """迭代控制器。

    管理运行状态的生命周期，在每轮评估后决定下一步动作。

    Args:
        max_iterations: 最大迭代次数，默认 3。
        pass_threshold: 质量合格阈值，默认 0.7。
        min_improvement: 最小改进幅度，低于此值视为"无明显改进"，默认 0.03。
    """

    def __init__(
        self,
        max_iterations: int = 3,
        pass_threshold: float = 0.7,
        min_improvement: float = 0.03,
    ) -> None:
        self.max_iterations = max_iterations
        self.pass_threshold = pass_threshold
        self.min_improvement = min_improvement

    def initialize_state(self, run_id: str) -> RunState:
        """为新运行创建初始状态。"""
        now = _now_iso()
        return RunState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            current_stage=RunStage.CONTEXT_RESEARCH,
            iteration_index=0,
            max_iterations=self.max_iterations,
            timestamps={"created_at": now, "started_at": now},
        )

    def decide(
        self,
        state: RunState,
        evaluation: EvaluationReport,
    ) -> IterationDecision:
        """根据评估结果和当前状态做出迭代决策。

        Args:
            state: 当前运行状态。
            evaluation: 本轮评估报告。

        Returns:
            IterationDecision 指示下一步动作。
        """
        score = evaluation.overall_score

        # 条件 1: 达到质量阈值 → 通过
        if score >= self.pass_threshold:
            return IterationDecision(
                action="pass",
                reason=f"评估分数 {score:.4f} 达到阈值 {self.pass_threshold}",
            )

        # 条件 2: 达到最大迭代数 → 失败
        if state.iteration_index >= self.max_iterations - 1:
            return IterationDecision(
                action="fail",
                reason=f"已达最大迭代次数 {self.max_iterations}，最终分数 {score:.4f}",
            )

        # 条件 3: 连续两轮无明显改进 → 提前终止
        if self._no_improvement_streak(state, score):
            return IterationDecision(
                action="fail",
                reason=(
                    f"连续两轮无明显改进（改进幅度 < {self.min_improvement}），"
                    f"最终分数 {score:.4f}"
                ),
            )

        # 条件 4: 可恢复，需要回流
        target_stage = evaluation.suggested_retry_stage or "draft_generation"
        return IterationDecision(
            action="retry",
            reason=self._build_retry_reason(evaluation),
            target_stage=target_stage,
        )

    def update_state_after_evaluation(
        self,
        state: RunState,
        evaluation: EvaluationReport,
        decision: IterationDecision,
        artifacts_snapshot: dict[str, str] | None = None,
    ) -> RunState:
        """根据评估和决策更新运行状态。

        此方法会：
        1. 记录本轮迭代日志
        2. 更新状态中的评估分数和摘要
        3. 根据决策设置状态（succeeded/failed/retrying）
        4. 如果是 retry，记录回流决策

        Args:
            state: 当前运行状态。
            evaluation: 本轮评估报告。
            decision: 迭代决策。
            artifacts_snapshot: 本轮工件快照。

        Returns:
            更新后的运行状态。
        """
        now = _now_iso()

        # 记录迭代日志
        iteration_record = IterationRecord(
            iteration_index=state.iteration_index,
            stage=state.current_stage.value,
            evaluation_score=evaluation.overall_score,
            evaluation_summary=evaluation.improvement_summary,
            retry_reason=decision.reason if decision.action == "retry" else "",
            retry_target_stage=decision.target_stage if decision.action == "retry" else "",
            artifacts_snapshot=artifacts_snapshot or {},
            timestamp=now,
        )
        state.iteration_history.append(iteration_record)
        state.last_evaluation_score = evaluation.overall_score
        state.last_evaluation_summary = evaluation.improvement_summary
        state.timestamps["last_evaluated_at"] = now

        if decision.action == "pass":
            state.status = RunStatus.SUCCEEDED
            state.current_stage = RunStage.OUTPUT_DELIVERY
            state.timestamps["completed_at"] = now

        elif decision.action == "fail":
            state.status = RunStatus.FAILED
            state.retry_reason = decision.reason
            state.timestamps["failed_at"] = now

        elif decision.action == "retry":
            state.status = RunStatus.RETRYING
            state.retry_reason = decision.reason
            state.iteration_index += 1
            state.timestamps["last_retried_at"] = now

            # 映射回流目标到 RunStage
            stage_map = {
                "context_research": RunStage.CONTEXT_RESEARCH,
                "checkpoint_generation": RunStage.CHECKPOINT_GENERATION,
                "draft_generation": RunStage.DRAFT_GENERATION,
            }
            state.current_stage = stage_map.get(
                decision.target_stage, RunStage.DRAFT_GENERATION
            )

            # 记录回流决策
            retry_decision = RetryDecision(
                iteration_index=state.iteration_index,
                retry_reason=decision.reason,
                target_stage=decision.target_stage,
                trigger_dimension=self._find_weakest_dimension(evaluation),
                previous_score=evaluation.overall_score,
                timestamp=now,
            )
            state.retry_decisions.append(retry_decision)

        return state

    def mark_error(self, state: RunState, error: Exception) -> RunState:
        """标记运行状态为不可恢复错误。"""
        state.status = RunStatus.FAILED
        state.error = {
            "code": error.__class__.__name__,
            "message": str(error),
        }
        state.timestamps["failed_at"] = _now_iso()
        return state

    def _no_improvement_streak(self, state: RunState, current_score: float) -> bool:
        """检查是否连续两轮无明显改进。"""
        history = state.iteration_history
        if len(history) < 2:
            return False

        prev_score = history[-1].evaluation_score
        prev_prev_score = history[-2].evaluation_score

        # 最近两轮的改进幅度都很小
        improvement_1 = current_score - prev_score
        improvement_2 = prev_score - prev_prev_score

        return improvement_1 < self.min_improvement and improvement_2 < self.min_improvement

    def _build_retry_reason(self, evaluation: EvaluationReport) -> str:
        """构建回流原因说明。"""
        weak_dims = [d for d in evaluation.dimensions if d.score < 0.6]
        if not weak_dims:
            return f"总分 {evaluation.overall_score:.4f} 未达阈值 {self.pass_threshold}"

        reasons = [f"{d.name}={d.score:.2f}" for d in weak_dims]
        return f"以下维度不达标: {', '.join(reasons)}"

    def _find_weakest_dimension(self, evaluation: EvaluationReport) -> str:
        """找到最弱的评估维度。"""
        if not evaluation.dimensions:
            return ""
        weakest = min(evaluation.dimensions, key=lambda d: d.score)
        return weakest.name


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()
