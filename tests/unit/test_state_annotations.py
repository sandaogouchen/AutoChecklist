"""State annotation 测试。

验证 TypedDict 类型注解的正确性，以及 GlobalState ↔ CaseGenState 的
交集字段符合预期。
"""

from typing import get_type_hints

from app.domain.state import CaseGenState, GlobalState
from app.graphs.state_bridge import compute_shared_keys


def test_case_gen_state_type_hints_resolve_coverage_result() -> None:
    hints = get_type_hints(CaseGenState)

    assert "coverage_result" in hints


def test_global_state_type_hints_resolve_coverage_result() -> None:
    """GlobalState 应包含 coverage_result 字段以支持自动桥接回传。"""
    hints = get_type_hints(GlobalState)

    assert "coverage_result" in hints


def test_shared_keys_include_expected_fields() -> None:
    """验证 GlobalState 和 CaseGenState 的交集包含所有预期的共享字段。"""
    shared = compute_shared_keys(GlobalState, CaseGenState)

    expected_shared = {
        "language",
        "parsed_document",
        "research_output",
        "planned_scenarios",
        "checkpoints",
        "checkpoint_coverage",
        "checkpoint_paths",
        "canonical_outline_nodes",
        "mapped_evidence",
        "draft_cases",
        "test_cases",
        "optimized_tree",
        "project_context_summary",
        "template_leaf_targets",
        "project_template",
        "mandatory_skeleton",
        "xmind_reference_summary",
        "draft_writer_timing",
        "coverage_result",
    }

    assert expected_shared <= shared, (
        f"Missing expected shared keys: {expected_shared - shared}"
    )


def test_shared_keys_exclude_parent_only_fields() -> None:
    """主图独有字段不应出现在交集中。"""
    shared = compute_shared_keys(GlobalState, CaseGenState)

    parent_only = {
        "run_id", "file_path", "request", "model_config",
        "quality_report", "artifacts", "error",
        "run_state", "evaluation_report", "iteration_index",
        "project_id", "template_file_path",
        "knowledge_context", "knowledge_sources", "knowledge_retrieval_success",
        "reference_xmind_path",
    }

    for key in parent_only:
        assert key not in shared, f"Parent-only key {key!r} should not be in shared keys"


def test_shared_keys_exclude_child_only_fields() -> None:
    """子图独有字段不应出现在交集中。"""
    shared = compute_shared_keys(GlobalState, CaseGenState)

    child_only = {"uncovered_checkpoints"}

    for key in child_only:
        assert key not in shared, f"Child-only key {key!r} should not be in shared keys"
