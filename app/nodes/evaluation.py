"""评估引擎节点。

实现 6+1 维评估框架：
- fact_coverage: 事实覆盖率
- checkpoint_coverage: 检查点覆盖率
- evidence_completeness: 证据完整性
- duplicate_rate: 重复率
- case_completeness: 用例完整性
- branch_coverage: 分支覆盖率
- template_compliance: 模板合规率（仅当使用模板时启用）
"""
from __future__ import annotations

import logging
from typing import Any

from app.clients.llm import LLMClient
from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint, CheckpointCoverage
from app.domain.research_models import ResearchFact
from app.domain.run_state import EvaluationDimension, EvaluationReport
from app.domain.state import GlobalState
from app.domain.template_models import ChecklistTemplate

logger = logging.getLogger(__name__)


def build_evaluation_node(llm_client: LLMClient):
    """构建评估引擎节点。"""

    async def evaluation_node(state: GlobalState) -> dict[str, Any]:
        """执行 6+1 维质量评估。"""
        facts = state.get("facts", [])
        checkpoints = state.get("checkpoints", [])
        test_cases = state.get("test_cases", [])
        coverage = state.get("coverage")

        dimensions: list[EvaluationDimension] = []

        # 维度 1: 事实覆盖率
        fact_score = _compute_fact_coverage(facts, checkpoints)
        dimensions.append(EvaluationDimension(
            name="fact_coverage", score=fact_score, weight=0.2,
        ))

        # 维度 2: 检查点覆盖率
        cp_score = _compute_checkpoint_coverage(checkpoints, test_cases)
        dimensions.append(EvaluationDimension(
            name="checkpoint_coverage", score=cp_score, weight=0.2,
        ))

        # 维度 3: 证据完整性
        evidence_score = _compute_evidence_completeness(test_cases)
        dimensions.append(EvaluationDimension(
            name="evidence_completeness", score=evidence_score, weight=0.15,
        ))

        # 维度 4: 重复率
        dup_score = _compute_duplicate_rate(test_cases)
        dimensions.append(EvaluationDimension(
            name="duplicate_rate", score=dup_score, weight=0.15,
        ))

        # 维度 5: 用例完整性
        completeness_score = _compute_case_completeness(test_cases)
        dimensions.append(EvaluationDimension(
            name="case_completeness", score=completeness_score, weight=0.15,
        ))

        # 维度 6: 分支覆盖率
        branch_score = _compute_branch_coverage(checkpoints, test_cases)
        dimensions.append(EvaluationDimension(
            name="branch_coverage", score=branch_score, weight=0.15,
        ))

        # ---- 维度 7（可选）: 模板合规率 ----
        # 仅当状态中携带了模板数据时才启用此维度。
        # 计算逻辑：模板中定义的维度（categories）总数为分母，
        # 至少有一个 checkpoint 关联到的维度数为分子。
        template_dict = state.get("template")
        if template_dict:
            try:
                tpl = ChecklistTemplate.model_validate(template_dict)
                template_score = _compute_template_compliance(tpl, checkpoints)
                dimensions.append(EvaluationDimension(
                    name="template_compliance", score=template_score, weight=0.10,
                ))
                logger.info("模板合规率: %.4f", template_score)
            except Exception:
                logger.warning("模板合规率计算失败，跳过该维度", exc_info=True)

        # 加权总分
        total_weight = sum(d.weight for d in dimensions)
        overall_score = sum(d.score * d.weight for d in dimensions) / total_weight if total_weight else 0.0

        passed = overall_score >= 0.7

        report = EvaluationReport(
            dimensions=dimensions,
            overall_score=overall_score,
            passed=passed,
            improvement_summary=_build_improvement_summary(dimensions, overall_score),
        )

        logger.info(
            "评估完成: overall=%.4f, passed=%s, dimensions=%d",
            overall_score, passed, len(dimensions),
        )
        return {"evaluation_report": report}

    return evaluation_node


def _compute_fact_coverage(facts: list[ResearchFact], checkpoints: list[Checkpoint]) -> float:
    if not facts:
        return 1.0
    covered_fact_ids = set()
    for cp in checkpoints:
        covered_fact_ids.update(cp.fact_ids)
    all_fact_ids = {f.fact_id for f in facts if f.fact_id}
    if not all_fact_ids:
        return 1.0
    return len(covered_fact_ids & all_fact_ids) / len(all_fact_ids)


def _compute_checkpoint_coverage(checkpoints: list[Checkpoint], test_cases: list[TestCase]) -> float:
    if not checkpoints:
        return 1.0
    covered_cp_ids = {tc.checkpoint_id for tc in test_cases if tc.checkpoint_id}
    all_cp_ids = {cp.checkpoint_id for cp in checkpoints if cp.checkpoint_id}
    if not all_cp_ids:
        return 1.0
    return len(covered_cp_ids & all_cp_ids) / len(all_cp_ids)


def _compute_evidence_completeness(test_cases: list[TestCase]) -> float:
    if not test_cases:
        return 0.0
    with_evidence = sum(1 for tc in test_cases if tc.evidence_refs)
    return with_evidence / len(test_cases)


def _compute_duplicate_rate(test_cases: list[TestCase]) -> float:
    if not test_cases:
        return 1.0
    titles = [tc.title.strip().lower() for tc in test_cases]
    unique = len(set(titles))
    return unique / len(titles)


def _compute_case_completeness(test_cases: list[TestCase]) -> float:
    if not test_cases:
        return 0.0
    complete = sum(
        1 for tc in test_cases
        if tc.steps and tc.expected_results and tc.title
    )
    return complete / len(test_cases)


def _compute_branch_coverage(checkpoints: list[Checkpoint], test_cases: list[TestCase]) -> float:
    if not checkpoints:
        return 1.0
    categories = {cp.category for cp in checkpoints}
    covered_categories = {tc.category for tc in test_cases}
    if not categories:
        return 1.0
    return len(covered_categories & categories) / len(categories)


def _compute_template_compliance(
    template: ChecklistTemplate,
    checkpoints: list[Checkpoint],
) -> float:
    """计算模板合规率。

    分母：模板中定义的维度（category）总数。
    分子：至少有一个 checkpoint 的 template_category 匹配到的维度数。

    当模板无维度定义时返回 1.0（无约束 = 完全合规）。
    """
    template_categories = set()
    for cat in template.categories:
        template_categories.add(cat.name)

    if not template_categories:
        return 1.0

    covered_categories = set()
    for cp in checkpoints:
        if cp.template_category and cp.template_category in template_categories:
            covered_categories.add(cp.template_category)

    return len(covered_categories) / len(template_categories)


def _build_improvement_summary(dimensions: list[EvaluationDimension], overall_score: float) -> str:
    weak = [d for d in dimensions if d.score < 0.6]
    if not weak:
        return f"总体评分 {overall_score:.2f}，所有维度达标"
    names = ", ".join(f"{d.name}({d.score:.2f})" for d in weak)
    return f"总体评分 {overall_score:.2f}，以下维度需要改进: {names}"
