"""Unit tests for PreconditionGrouper."""

from __future__ import annotations

import time

import pytest

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.services.precondition_grouper import (
    PreconditionGrouper,
    _longest_common_prefix,
    _normalize_precondition,
    _normalize_precondition_list,
)


# ---------------------------------------------------------------------------
# _normalize_precondition
# ---------------------------------------------------------------------------

class TestNormalizePrecondition:
    """Tests for the lightweight normalization function."""

    def test_strips_whitespace(self) -> None:
        assert _normalize_precondition("  用户已登录  ") == "用户已登录"

    def test_nfkc_normalization(self) -> None:
        # ＡＢＣ (fullwidth)→ ABC
        assert _normalize_precondition("\uff21\uff22\uff23") == "ABC"

    def test_chinese_punctuation_mapped(self) -> None:
        assert _normalize_precondition("条件一，条件二") == "条件一,条件二"
        assert _normalize_precondition("步骤（一）") == "步骤(一)"
        assert _normalize_precondition("完成。") == "完成."

    def test_case_preserved(self) -> None:
        # 不做 casefold
        assert _normalize_precondition("Hello World") == "Hello World"

    def test_empty_string(self) -> None:
        assert _normalize_precondition("") == ""


# ---------------------------------------------------------------------------
# _normalize_precondition_list
# ---------------------------------------------------------------------------

class TestNormalizePreconditionList:
    """Tests for list normalization → sorted tuple."""

    def test_returns_tuple(self) -> None:
        result = _normalize_precondition_list(["b", "a"])
        assert isinstance(result, tuple)
        assert result == ("a", "b")

    def test_empty_list(self) -> None:
        assert _normalize_precondition_list([]) == ()


# ---------------------------------------------------------------------------
# _longest_common_prefix
# ---------------------------------------------------------------------------

class TestLongestCommonPrefix:
    """Tests for LCP helper."""

    def test_full_match(self) -> None:
        assert _longest_common_prefix(["abc", "abc"]) == "abc"

    def test_partial_match(self) -> None:
        assert _longest_common_prefix(["abcde", "abcfg"]) == "abc"

    def test_no_match(self) -> None:
        assert _longest_common_prefix(["abc", "xyz"]) == ""

    def test_empty_list(self) -> None:
        assert _longest_common_prefix([]) == ""

    def test_single_string(self) -> None:
        assert _longest_common_prefix(["hello"]) == "hello"


# ---------------------------------------------------------------------------
# PreconditionGrouper
# ---------------------------------------------------------------------------

def _tc(
    tc_id: str,
    title: str = "test",
    preconditions: list[str] | None = None,
    steps: list[str] | None = None,
    expected_results: list[str] | None = None,
) -> TestCase:
    """Helper to build a minimal TestCase."""
    return TestCase(
        id=tc_id,
        title=title,
        preconditions=preconditions or [],
        steps=steps or ["step1"],
        expected_results=expected_results or ["expected1"],
    )


class TestPreconditionGrouper:
    """Tests for the grouping engine."""

    def test_empty_input(self) -> None:
        grouper = PreconditionGrouper()
        assert grouper.group([]) == []

    def test_single_case_no_group(self) -> None:
        """Single case should NOT create a group (below _MIN_GROUP_SIZE)."""
        cases = [_tc("TC-001", preconditions=["用户已登录"])]
        result = PreconditionGrouper().group(cases)
        assert len(result) == 1
        assert result[0].node_type == "case"

    def test_shared_preconditions_create_group(self) -> None:
        """Two cases with identical preconditions → one group."""
        cases = [
            _tc("TC-001", preconditions=["用户已登录", "网络正常"]),
            _tc("TC-002", preconditions=["用户已登录", "网络正常"]),
        ]
        result = PreconditionGrouper().group(cases)
        assert len(result) == 1
        group = result[0]
        assert group.node_type == "precondition_group"
        assert len(group.children) == 2

    def test_no_preconditions_no_group(self) -> None:
        """Cases without preconditions are never grouped."""
        cases = [_tc("TC-001"), _tc("TC-002")]
        result = PreconditionGrouper().group(cases)
        # Empty key → each case becomes independent
        assert all(n.node_type == "case" for n in result)

    def test_mixed_grouped_and_ungrouped(self) -> None:
        """Mix of groupable and ungroupable cases."""
        cases = [
            _tc("TC-001", preconditions=["登录"]),
            _tc("TC-002", preconditions=["登录"]),
            _tc("TC-003", preconditions=["未登录"]),
        ]
        result = PreconditionGrouper().group(cases)
        types = [n.node_type for n in result]
        assert "precondition_group" in types
        assert "case" in types

    def test_different_preconditions_separate_groups(self) -> None:
        """Different precondition sets → separate groups."""
        cases = [
            _tc("TC-001", preconditions=["A", "B"]),
            _tc("TC-002", preconditions=["A", "B"]),
            _tc("TC-003", preconditions=["C", "D"]),
            _tc("TC-004", preconditions=["C", "D"]),
        ]
        result = PreconditionGrouper().group(cases)
        groups = [n for n in result if n.node_type == "precondition_group"]
        assert len(groups) == 2

    def test_punctuation_normalization_groups_together(self) -> None:
        """Chinese vs English punctuation should be treated as identical."""
        cases = [
            _tc("TC-001", preconditions=["条件一，条件二"]),
            _tc("TC-002", preconditions=["条件一,条件二"]),
        ]
        result = PreconditionGrouper().group(cases)
        groups = [n for n in result if n.node_type == "precondition_group"]
        assert len(groups) == 1

    def test_additional_preconditions_in_case_node(self) -> None:
        """Case node should only contain additional preconditions."""
        cases = [
            _tc("TC-001", preconditions=["共享条件", "额外条件A"]),
            _tc("TC-002", preconditions=["共享条件", "额外条件B"]),
        ]
        # Both share "共享条件" but differ on second item → not grouped
        # (different tuple keys)
        result = PreconditionGrouper().group(cases)
        # Each case has a unique precondition set → case nodes, not grouped
        assert len(result) == 2

    def test_data_preservation(self) -> None:
        """Case node preserves steps, expected_results, priority, etc."""
        tc = _tc(
            "TC-001",
            title="验证登录",
            preconditions=["已注册"],
            steps=["输入密码", "点击登录"],
            expected_results=["登录成功"],
        )
        tc.priority = "P0"
        tc.category = "functional"
        tc.checkpoint_id = "CP-abc123"

        result = PreconditionGrouper().group([tc])
        assert len(result) == 1
        node = result[0]
        assert node.title == "验证登录"
        assert node.steps == ["输入密码", "点击登录"]
        assert node.expected_results == ["登录成功"]
        assert node.priority == "P0"
        assert node.checkpoint_id == "CP-abc123"

    def test_node_id_formats(self) -> None:
        """Verify node_id naming conventions."""
        cases = [
            _tc("TC-001", preconditions=["登录"]),
            _tc("TC-002", preconditions=["登录"]),
        ]
        result = PreconditionGrouper().group(cases)
        group = result[0]
        assert group.node_id.startswith("GRP-")
        for child in group.children:
            assert child.node_id.startswith("CASE-")

    def test_performance_100_cases(self) -> None:
        """100 cases should complete within 1 second."""
        cases = [
            _tc(
                f"TC-{i:03d}",
                preconditions=[f"前置条件{i % 10}"],
            )
            for i in range(100)
        ]
        start = time.time()
        result = PreconditionGrouper().group(cases)
        elapsed = time.time() - start
        assert elapsed < 1.0
        assert len(result) > 0
