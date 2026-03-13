from __future__ import annotations

from app.domain.case_models import QualityReport, TestCase
from app.domain.state import GlobalState


def reflection_node(state: GlobalState) -> GlobalState:
    cases = state.get("test_cases", [])
    deduped_cases, quality_report = deduplicate_cases(cases)
    warnings = list(quality_report.warnings)
    repaired_fields = list(quality_report.repaired_fields)

    for case in deduped_cases:
        if not case.expected_results:
            warnings.append(f"{case.id} is missing expected results")
        if not case.evidence_refs:
            warnings.append(f"{case.id} is missing evidence references")

    planned_count = len(state.get("planned_scenarios", []))
    if planned_count and len(deduped_cases) < planned_count:
        quality_report.coverage_notes.append(
            f"Generated {len(deduped_cases)} cases for {planned_count} planned scenarios."
        )

    quality_report.warnings = warnings
    quality_report.repaired_fields = repaired_fields
    return {"test_cases": deduped_cases, "quality_report": quality_report}


def deduplicate_cases(cases: list[TestCase]) -> tuple[list[TestCase], QualityReport]:
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
