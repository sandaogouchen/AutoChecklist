"""反思与质量检查节点。

作为工作流的最后一个节点，对生成的测试用例进行质量审查：
- 按标题去重，记录重复组
- 检查必要字段的完整性（预期结果、证据引用）
- 评估场景覆盖率
- 检查 checkpoint 层面的覆盖与质量
"""

from __future__ import annotations

from app.domain.case_models import QualityReport, TestCase
from app.domain.checkpoint_models import CheckpointCoverage
from app.domain.state import GlobalState


def reflection_node(state: GlobalState) -> GlobalState:
    """对最终用例列表进行去重、质量检查和 checkpoint 覆盖评估。

    检查项：
    1. 标题去重 — 相同标题（大小写不敏感）的用例只保留首个
    2. 字段完整性 — 检查每个用例是否包含预期结果和证据引用
    3. 覆盖率评估 — 对比生成用例数与规划场景数
    4. Checkpoint 覆盖 — 检查 facts 和 checkpoints 的覆盖情况

    Returns:
        包含去重后的 ``test_cases``、``quality_report`` 和
        ``checkpoint_coverage`` 的状态增量。
    """
    cases = state.get("test_cases", [])
    deduped_cases, quality_report = deduplicate_cases(cases)

    warnings = list(quality_report.warnings)
    repaired_fields = list(quality_report.repaired_fields)
    checkpoint_warnings: list[str] = []

    # 检查每个用例的关键字段是否缺失
    for case in deduped_cases:
        if not case.expected_results:
            warnings.append(f"{case.id} is missing expected results")
        if not case.evidence_refs:
            warnings.append(f"{case.id} is missing evidence references")

    # 评估场景覆盖率：生成用例数 vs 规划场景数
    planned_count = len(state.get("planned_scenarios", []))
    if planned_count and len(deduped_cases) < planned_count:
        quality_report.coverage_notes.append(
            f"Generated {len(deduped_cases)} cases for {planned_count} planned scenarios."
        )

    # ---- Checkpoint 感知的质量检查 ----
    checkpoints = state.get("checkpoints", [])
    research_output = state.get("research_output")

    if checkpoints:
        checkpoint_warnings = _check_checkpoint_quality(
            checkpoints=checkpoints,
            test_cases=deduped_cases,
            research_output=research_output,
        )

    # ---- 项目上下文感知的检查 ----
    project_context_summary = state.get("project_context_summary", "")
    if project_context_summary:
        warnings.append(
            f"Project context was applied. Review test cases for project-specific coverage."
        )

    # 更新 checkpoint 覆盖状态
    updated_coverage = _compute_checkpoint_coverage(checkpoints, deduped_cases)

    quality_report.warnings = warnings
    quality_report.repaired_fields = repaired_fields
    quality_report.checkpoint_warnings = checkpoint_warnings

    result: dict = {
        "test_cases": deduped_cases,
        "quality_report": quality_report,
    }

    if updated_coverage:
        result["checkpoint_coverage"] = updated_coverage

    return result


def _check_checkpoint_quality(
    checkpoints: list,
    test_cases: list[TestCase],
    research_output,
) -> list[str]:
    """执行 checkpoint 层面的质量检查。

    检查项：
    1. 是否存在未生成 checkpoint 的 fact
    2. 是否存在未被 testcase 覆盖的 checkpoint
    3. 是否存在 evidence 不足的 checkpoint
    4. 是否存在重复或语义重叠的 checkpoint（按标题检测）
    """
    warnings: list[str] = []

    # 1. 检查未生成 checkpoint 的 fact
    if research_output and hasattr(research_output, "facts") and research_output.facts:
        all_fact_ids_in_checkpoints: set[str] = set()
        for cp in checkpoints:
            all_fact_ids_in_checkpoints.update(cp.fact_ids)

        for fact in research_output.facts:
            if fact.fact_id and fact.fact_id not in all_fact_ids_in_checkpoints:
                warnings.append(
                    f"Fact '{fact.fact_id}' ({fact.description[:50]}) has no corresponding checkpoint."
                )

    # 2. 检查未被 testcase 覆盖的 checkpoint
    covered_checkpoint_ids: set[str] = set()
    for case in test_cases:
        if case.checkpoint_id:
            covered_checkpoint_ids.add(case.checkpoint_id)

    for cp in checkpoints:
        if cp.checkpoint_id not in covered_checkpoint_ids:
            warnings.append(
                f"Checkpoint '{cp.checkpoint_id}' ({cp.title[:50]}) is not covered by any test case."
            )

    # 3. 检查 evidence 不足的 checkpoint
    for cp in checkpoints:
        if not cp.evidence_refs:
            warnings.append(
                f"Checkpoint '{cp.checkpoint_id}' ({cp.title[:50]}) has no evidence references."
            )

    # 4. 检查标题重叠的 checkpoint（前面已去重，这里检测相似性）
    titles = [cp.title.strip().casefold() for cp in checkpoints]
    for i, title_i in enumerate(titles):
        for j in range(i + 1, len(titles)):
            # 简单的包含关系检测
            if title_i in titles[j] or titles[j] in title_i:
                warnings.append(
                    f"Checkpoints '{checkpoints[i].checkpoint_id}' and "
                    f"'{checkpoints[j].checkpoint_id}' may have overlapping titles."
                )

    return warnings


def _compute_checkpoint_coverage(
    checkpoints: list,
    test_cases: list[TestCase],
) -> list[CheckpointCoverage]:
    """计算每个 checkpoint 的用例覆盖状态。

    遍历所有测试用例，根据 checkpoint_id 建立覆盖映射，
    更新每个 checkpoint 的覆盖状态。
    """
    if not checkpoints:
        return []

    # 建立 checkpoint_id → 覆盖的 test_ids 映射
    coverage_map: dict[str, list[str]] = {cp.checkpoint_id: [] for cp in checkpoints}

    for case in test_cases:
        if case.checkpoint_id and case.checkpoint_id in coverage_map:
            coverage_map[case.checkpoint_id].append(case.id)

    return [
        CheckpointCoverage(
            checkpoint_id=cp_id,
            covered_by_test_ids=test_ids,
            coverage_status="covered" if test_ids else "uncovered",
        )
        for cp_id, test_ids in coverage_map.items()
    ]


def deduplicate_cases(
    cases: list[TestCase],
) -> tuple[list[TestCase], QualityReport]:
    """按标题对测试用例进行去重。

    使用 ``casefold()`` 进行大小写不敏感的标题比较，
    保留首次出现的用例，将重复项的 ID 对记录到质量报告中。

    Args:
        cases: 待去重的用例列表。

    Returns:
        二元组：(去重后的用例列表, 包含重复组信息的质量报告)。
    """
    deduped_cases: list[TestCase] = []
    duplicate_groups: list[list[str]] = []
    seen_by_title: dict[str, TestCase] = {}

    for case in cases:
        key = case.title.strip().casefold()
        existing = seen_by_title.get(key)
        if existing is not None:
            duplicate_groups.append([existing.id, case.id])
            continue
        seen_by_title[key] = case
        deduped_cases.append(case)

    return deduped_cases, QualityReport(duplicate_groups=duplicate_groups)
