"""结构化评估节点。

作为独立的 evaluation 阶段，对生成的测试用例进行多维度结构化评估。
评估维度包括：
- fact 覆盖率
- checkpoint 覆盖率
- evidence 完整度
- testcase 重复率
- testcase 缺步骤/缺预期结果比例
- 分支覆盖或异常路径覆盖情况

评估输出为结构化的 EvaluationReport，而非自然语言 warning。
"""

from __future__ import annotations

from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint
from app.domain.research_models import ResearchOutput
from app.domain.run_state import EvaluationDimension, EvaluationReport


def evaluate(
    *,
    test_cases: list[TestCase],
    checkpoints: list[Checkpoint],
    research_output: ResearchOutput | None = None,
    previous_score: float = 0.0,
) -> EvaluationReport:
    """对当前生成结果执行多维度结构化评估。

    Args:
        test_cases: 当前轮次生成的测试用例。
        checkpoints: 当前轮次的检查点列表。
        research_output: 上下文研究输出（含 facts）。
        previous_score: 上一轮评估分数，用于比较。

    Returns:
        结构化评估报告。
    """
    dimensions: list[EvaluationDimension] = []

    # 维度 1: fact 覆盖率
    fact_dim = _evaluate_fact_coverage(checkpoints, research_output)
    dimensions.append(fact_dim)

    # 维度 2: checkpoint 覆盖率
    checkpoint_dim = _evaluate_checkpoint_coverage(test_cases, checkpoints)
    dimensions.append(checkpoint_dim)

    # 维度 3: evidence 完整度
    evidence_dim = _evaluate_evidence_completeness(test_cases)
    dimensions.append(evidence_dim)

    # 维度 4: testcase 重复率
    duplicate_dim = _evaluate_duplicate_rate(test_cases)
    dimensions.append(duplicate_dim)

    # 维度 5: testcase 完整性（缺步骤/缺预期结果）
    completeness_dim = _evaluate_case_completeness(test_cases)
    dimensions.append(completeness_dim)

    # 维度 6: 分支/异常路径覆盖
    branch_dim = _evaluate_branch_coverage(test_cases, checkpoints)
    dimensions.append(branch_dim)

    # 计算总体分数（各维度加权平均）
    if dimensions:
        total_weight = len(dimensions)
        overall_score = sum(d.score for d in dimensions) / total_weight
    else:
        overall_score = 0.0

    # 收集关键失败项
    critical_failures: list[str] = []
    for dim in dimensions:
        if dim.score < 0.5:
            critical_failures.extend(dim.failed_items[:3])

    # 确定建议回流阶段
    suggested_stage = _determine_retry_stage(dimensions)

    # 生成与上一轮的比较说明
    comparison = ""
    if previous_score > 0:
        delta = overall_score - previous_score
        if delta > 0.05:
            comparison = f"相较上轮提升 {delta:.2f}（{previous_score:.2f} → {overall_score:.2f}）"
        elif delta < -0.05:
            comparison = f"相较上轮退化 {abs(delta):.2f}（{previous_score:.2f} → {overall_score:.2f}）"
        else:
            comparison = f"与上轮基本持平（{previous_score:.2f} → {overall_score:.2f}）"

    return EvaluationReport(
        overall_score=round(overall_score, 4),
        dimensions=dimensions,
        critical_failures=critical_failures,
        suggested_retry_stage=suggested_stage,
        improvement_summary=_generate_improvement_summary(dimensions),
        comparison_with_previous=comparison,
    )


def _evaluate_fact_coverage(
    checkpoints: list[Checkpoint],
    research_output: ResearchOutput | None,
) -> EvaluationDimension:
    """评估 fact 覆盖率：有多少 fact 被至少一个 checkpoint 引用。"""
    if not research_output or not research_output.facts:
        return EvaluationDimension(
            name="fact_coverage",
            score=1.0,
            details="无 facts 需要覆盖",
        )

    all_fact_ids = {f.fact_id for f in research_output.facts if f.fact_id}
    covered_fact_ids: set[str] = set()
    for cp in checkpoints:
        covered_fact_ids.update(cp.fact_ids)

    if not all_fact_ids:
        return EvaluationDimension(name="fact_coverage", score=1.0, details="无有效 fact_id")

    covered = len(all_fact_ids & covered_fact_ids)
    total = len(all_fact_ids)
    score = covered / total if total > 0 else 1.0
    uncovered = all_fact_ids - covered_fact_ids

    return EvaluationDimension(
        name="fact_coverage",
        score=round(score, 4),
        details=f"共 {total} 个 fact，已覆盖 {covered} 个",
        failed_items=[f"Fact '{fid}' 未被任何 checkpoint 覆盖" for fid in sorted(uncovered)],
    )


def _evaluate_checkpoint_coverage(
    test_cases: list[TestCase],
    checkpoints: list[Checkpoint],
) -> EvaluationDimension:
    """评估 checkpoint 覆盖率：有多少 checkpoint 被至少一个 testcase 覆盖。"""
    if not checkpoints:
        return EvaluationDimension(
            name="checkpoint_coverage",
            score=1.0,
            details="无 checkpoint 需要覆盖",
        )

    all_cp_ids = {cp.checkpoint_id for cp in checkpoints if cp.checkpoint_id}
    covered_cp_ids: set[str] = set()
    for tc in test_cases:
        if tc.checkpoint_id:
            covered_cp_ids.add(tc.checkpoint_id)

    if not all_cp_ids:
        return EvaluationDimension(
            name="checkpoint_coverage", score=1.0, details="无有效 checkpoint_id"
        )

    covered = len(all_cp_ids & covered_cp_ids)
    total = len(all_cp_ids)
    score = covered / total if total > 0 else 1.0
    uncovered = all_cp_ids - covered_cp_ids

    return EvaluationDimension(
        name="checkpoint_coverage",
        score=round(score, 4),
        details=f"共 {total} 个 checkpoint，已覆盖 {covered} 个",
        failed_items=[
            f"Checkpoint '{cpid}' 未被任何 testcase 覆盖" for cpid in sorted(uncovered)
        ],
    )


def _evaluate_evidence_completeness(
    test_cases: list[TestCase],
) -> EvaluationDimension:
    """评估 evidence 完整度：有多少 testcase 关联了 evidence_refs。"""
    if not test_cases:
        return EvaluationDimension(
            name="evidence_completeness",
            score=1.0,
            details="无 testcase 需要评估",
        )

    total = len(test_cases)
    with_evidence = sum(1 for tc in test_cases if tc.evidence_refs)
    score = with_evidence / total if total > 0 else 0.0
    missing = [tc.id for tc in test_cases if not tc.evidence_refs]

    return EvaluationDimension(
        name="evidence_completeness",
        score=round(score, 4),
        details=f"共 {total} 个用例，{with_evidence} 个有 evidence 引用",
        failed_items=[f"TestCase '{tid}' 缺少 evidence 引用" for tid in missing[:5]],
    )


def _evaluate_duplicate_rate(
    test_cases: list[TestCase],
) -> EvaluationDimension:
    """评估 testcase 重复率：按标题检测重复。"""
    if not test_cases:
        return EvaluationDimension(
            name="duplicate_rate", score=1.0, details="无 testcase 需要评估"
        )

    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for tc in test_cases:
        key = tc.title.strip().casefold()
        if key in seen:
            duplicates.append(f"'{tc.id}' 与 '{seen[key]}' 标题重复")
        else:
            seen[key] = tc.id

    total = len(test_cases)
    unique_count = total - len(duplicates)
    score = unique_count / total if total > 0 else 1.0

    return EvaluationDimension(
        name="duplicate_rate",
        score=round(score, 4),
        details=f"共 {total} 个用例，{len(duplicates)} 组重复",
        failed_items=duplicates[:5],
    )


def _evaluate_case_completeness(
    test_cases: list[TestCase],
) -> EvaluationDimension:
    """评估 testcase 完整性：检查缺少步骤或预期结果的用例。"""
    if not test_cases:
        return EvaluationDimension(
            name="case_completeness", score=1.0, details="无 testcase 需要评估"
        )

    total = len(test_cases)
    incomplete: list[str] = []
    for tc in test_cases:
        issues = []
        if not tc.steps:
            issues.append("缺步骤")
        if not tc.expected_results:
            issues.append("缺预期结果")
        if issues:
            incomplete.append(f"TestCase '{tc.id}' {', '.join(issues)}")

    complete_count = total - len(incomplete)
    score = complete_count / total if total > 0 else 1.0

    return EvaluationDimension(
        name="case_completeness",
        score=round(score, 4),
        details=f"共 {total} 个用例，{len(incomplete)} 个不完整",
        failed_items=incomplete[:5],
    )


def _evaluate_branch_coverage(
    test_cases: list[TestCase],
    checkpoints: list[Checkpoint],
) -> EvaluationDimension:
    """评估分支/异常路径覆盖：检查是否有 edge_case 类别的覆盖。"""
    if not checkpoints:
        return EvaluationDimension(
            name="branch_coverage", score=1.0, details="无 checkpoint 需要评估"
        )

    # 统计非 functional 类别（如 edge_case, boundary, error_handling 等）的覆盖
    non_functional_cps = [
        cp for cp in checkpoints if cp.category.lower() != "functional"
    ]

    if not non_functional_cps:
        # 没有非功能性 checkpoint，检查是否有异常路径的 testcase
        edge_cases = [tc for tc in test_cases if tc.category.lower() != "functional"]
        if test_cases and not edge_cases:
            return EvaluationDimension(
                name="branch_coverage",
                score=0.5,
                details="所有用例均为 functional 类别，缺少异常路径覆盖",
                failed_items=["建议增加边界条件和异常路径的测试用例"],
            )
        return EvaluationDimension(
            name="branch_coverage", score=0.8, details="无非功能性 checkpoint"
        )

    covered_cp_ids: set[str] = set()
    for tc in test_cases:
        if tc.checkpoint_id:
            covered_cp_ids.add(tc.checkpoint_id)

    nf_ids = {cp.checkpoint_id for cp in non_functional_cps if cp.checkpoint_id}
    covered = len(nf_ids & covered_cp_ids)
    total = len(nf_ids) if nf_ids else 1
    score = covered / total if total > 0 else 0.0
    uncovered = nf_ids - covered_cp_ids

    return EvaluationDimension(
        name="branch_coverage",
        score=round(score, 4),
        details=f"共 {len(nf_ids)} 个非功能性 checkpoint，已覆盖 {covered} 个",
        failed_items=[
            f"非功能性 Checkpoint '{cpid}' 未被覆盖" for cpid in sorted(uncovered)
        ][:5],
    )


def _determine_retry_stage(dimensions: list[EvaluationDimension]) -> str | None:
    """根据评估维度确定建议的回流阶段。

    回流规则：
    - fact 覆盖率低 → 回到 context_research
    - checkpoint 覆盖率低 → 回到 checkpoint_generation
    - testcase 质量差（重复/不完整/缺证据）→ 回到 draft_generation
    - 所有维度合格 → 无需回流
    """
    dim_map = {d.name: d for d in dimensions}

    # 优先级：fact > checkpoint > testcase 质量
    fact_cov = dim_map.get("fact_coverage")
    if fact_cov and fact_cov.score < 0.6:
        return "context_research"

    cp_cov = dim_map.get("checkpoint_coverage")
    if cp_cov and cp_cov.score < 0.6:
        return "checkpoint_generation"

    # 检查 testcase 质量相关维度
    quality_dims = ["evidence_completeness", "duplicate_rate", "case_completeness", "branch_coverage"]
    low_quality = [
        dim_map[name] for name in quality_dims if name in dim_map and dim_map[name].score < 0.6
    ]
    if low_quality:
        return "draft_generation"

    return None


def _generate_improvement_summary(dimensions: list[EvaluationDimension]) -> str:
    """生成改进建议摘要。"""
    weak_dims = [d for d in dimensions if d.score < 0.7]
    if not weak_dims:
        return "各维度评估均达标，质量良好。"

    summaries = []
    for dim in weak_dims:
        summaries.append(f"- {dim.name}: {dim.score:.2f} — {dim.details}")

    return "以下维度需要改进：\n" + "\n".join(summaries)
