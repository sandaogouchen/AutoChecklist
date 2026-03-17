"""反思与质量检查节点。

作为工作流的最后一个节点，对生成的测试用例进行质量审查：
- 按标题去重，记录重复组
- 检查必要字段的完整性（预期结果、证据引用）
- 评估场景覆盖率
"""

from __future__ import annotations

from app.domain.case_models import QualityReport, TestCase
from app.domain.state import GlobalState


def reflection_node(state: GlobalState) -> GlobalState:
    """对最终用例列表进行去重和质量检查。

    检查项：
    1. 标题去重 — 相同标题（大小写不敏感）的用例只保留首个
    2. 字段完整性 — 检查每个用例是否包含预期结果和证据引用
    3. 覆盖率评估 — 对比生成用例数与规划场景数

    Returns:
        包含去重后的 ``test_cases`` 和 ``quality_report`` 的状态增量。
    """
    cases = state.get("test_cases", [])
    deduped_cases, quality_report = deduplicate_cases(cases)

    warnings = list(quality_report.warnings)
    repaired_fields = list(quality_report.repaired_fields)

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

    quality_report.warnings = warnings
    quality_report.repaired_fields = repaired_fields
    return {"test_cases": deduped_cases, "quality_report": quality_report}


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
