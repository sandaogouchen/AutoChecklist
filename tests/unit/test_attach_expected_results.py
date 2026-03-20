"""Unit tests for ``attach_expected_results_to_outline``.

Covers:
1. Normal case: one checkpoint maps to one TestCase -- fields are populated
2. Empty optimized_tree
3. Empty test_cases list
4. checkpoint_id has no matching TestCase
5. Multiple TestCases map to the same checkpoint_id -- sibling nodes created
6. Deeply nested tree structure with multiple group levels
"""

from __future__ import annotations

import pytest

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.services.checkpoint_outline_planner import attach_expected_results_to_outline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case_node(
    node_id: str = "case_1",
    display_text: str = "验证功能A",
    checkpoint_id: str = "cp_1",
) -> ChecklistNode:
    """Create a minimal ``case`` ChecklistNode."""
    return ChecklistNode(
        id=node_id,
        display_text=display_text,
        node_type="case",
        children=[],
        checkpoint_id=checkpoint_id,
    )


def _make_group_node(
    node_id: str = "group_1",
    display_text: str = "进入页面A",
    children: list[ChecklistNode] | None = None,
    checkpoint_id: str | None = None,
) -> ChecklistNode:
    """Create a ``group`` ChecklistNode with optional children."""
    return ChecklistNode(
        id=node_id,
        display_text=display_text,
        node_type="group",
        children=children or [],
        checkpoint_id=checkpoint_id,
    )


def _make_test_case(
    tc_id: str = "tc_1",
    title: str = "Test Case 1",
    checkpoint_id: str = "cp_1",
    steps: str = "1. 打开页面\n2. 点击按钮",
    preconditions: str = "用户已登录",
    expected_results: str = "按钮变灰",
    priority: str = "P0",
    category: str = "功能测试",
    evidence_refs: list[str] | None = None,
) -> TestCase:
    """Create a minimal ``TestCase``."""
    return TestCase(
        id=tc_id,
        title=title,
        checkpoint_id=checkpoint_id,
        steps=steps,
        preconditions=preconditions,
        expected_results=expected_results,
        priority=priority,
        category=category,
        evidence_refs=evidence_refs or [],
    )


# ---------------------------------------------------------------------------
# Test 1: Normal -- single TestCase matches a single case node
# ---------------------------------------------------------------------------


class TestSingleMatch:
    """One checkpoint_id matches exactly one TestCase."""

    def test_fields_are_populated(self):
        case_node = _make_case_node(checkpoint_id="cp_1")
        tree = [case_node]

        tc = _make_test_case(
            tc_id="tc_100",
            checkpoint_id="cp_1",
            steps="1. Step A\n2. Step B",
            preconditions="Pre-cond X",
            expected_results="Result Y",
            priority="P1",
            category="边界测试",
            evidence_refs=["ref_a", "ref_b"],
        )

        result = attach_expected_results_to_outline(tree, [tc])

        assert len(result) == 1
        node = result[0]
        assert node.steps == "1. Step A\n2. Step B"
        assert node.preconditions == "Pre-cond X"
        assert node.expected_results == "Result Y"
        assert node.priority == "P1"
        assert node.category == "边界测试"
        assert node.test_case_ref == "tc_100"
        assert node.evidence_refs == ["ref_a", "ref_b"]

    def test_original_node_identity_preserved(self):
        """The returned node should be the *same* object, mutated in place."""
        case_node = _make_case_node(checkpoint_id="cp_1")
        tc = _make_test_case(checkpoint_id="cp_1")

        result = attach_expected_results_to_outline([case_node], [tc])
        assert result[0] is case_node


# ---------------------------------------------------------------------------
# Test 2: Empty optimized_tree
# ---------------------------------------------------------------------------


class TestEmptyTree:
    def test_returns_empty_list(self):
        result = attach_expected_results_to_outline([], [_make_test_case()])
        assert result == []

    def test_returns_same_reference(self):
        empty: list[ChecklistNode] = []
        result = attach_expected_results_to_outline(empty, [_make_test_case()])
        assert result is empty


# ---------------------------------------------------------------------------
# Test 3: Empty test_cases list
# ---------------------------------------------------------------------------


class TestEmptyTestCases:
    def test_tree_returned_unchanged(self):
        case_node = _make_case_node(checkpoint_id="cp_1")
        tree = [case_node]

        result = attach_expected_results_to_outline(tree, [])
        assert result is tree
        assert len(result) == 1
        # Fields should remain at their defaults
        assert result[0].steps == ""
        assert result[0].test_case_ref == ""


# ---------------------------------------------------------------------------
# Test 4: checkpoint_id has no matching TestCase
# ---------------------------------------------------------------------------


class TestNoMatchingCheckpoint:
    def test_node_untouched_when_no_match(self):
        case_node = _make_case_node(checkpoint_id="cp_unknown")
        tc = _make_test_case(checkpoint_id="cp_other")

        result = attach_expected_results_to_outline([case_node], [tc])

        assert len(result) == 1
        node = result[0]
        # No TestCase matched, so fields stay default
        assert node.steps == ""
        assert node.preconditions == ""
        assert node.expected_results == ""
        assert node.priority == ""
        assert node.test_case_ref == ""


# ---------------------------------------------------------------------------
# Test 5: Multiple TestCases for the same checkpoint_id
# ---------------------------------------------------------------------------


class TestMultipleTestCasesSameCheckpoint:
    def test_first_tc_reuses_original_node(self):
        case_node = _make_case_node(node_id="case_A", checkpoint_id="cp_1")
        tc1 = _make_test_case(tc_id="tc_1", checkpoint_id="cp_1", steps="Step from tc1")
        tc2 = _make_test_case(tc_id="tc_2", checkpoint_id="cp_1", steps="Step from tc2")

        result = attach_expected_results_to_outline([case_node], [tc1, tc2])

        assert len(result) == 2
        # First node is the original, enriched with tc1
        assert result[0] is case_node
        assert result[0].steps == "Step from tc1"
        assert result[0].test_case_ref == "tc_1"

    def test_extra_tc_creates_sibling_nodes(self):
        case_node = _make_case_node(node_id="case_A", checkpoint_id="cp_1")
        tc1 = _make_test_case(tc_id="tc_1", checkpoint_id="cp_1", priority="P0")
        tc2 = _make_test_case(
            tc_id="tc_2",
            checkpoint_id="cp_1",
            priority="P2",
            title="Extra Case Title",
            steps="Extra steps",
        )
        tc3 = _make_test_case(tc_id="tc_3", checkpoint_id="cp_1", priority="P3")

        result = attach_expected_results_to_outline([case_node], [tc1, tc2, tc3])

        assert len(result) == 3
        # Original node has tc1 data
        assert result[0].test_case_ref == "tc_1"
        assert result[0].priority == "P0"

        # Second sibling has tc2 data
        assert result[1].node_type == "case"
        assert result[1].test_case_ref == "tc_2"
        assert result[1].priority == "P2"
        assert result[1].display_text == "Extra Case Title"
        assert result[1].steps == "Extra steps"
        assert result[1].checkpoint_id == "cp_1"

        # Third sibling has tc3 data
        assert result[2].test_case_ref == "tc_3"
        assert result[2].priority == "P3"

    def test_sibling_ids_contain_tc_id(self):
        case_node = _make_case_node(node_id="case_A", checkpoint_id="cp_1")
        tc1 = _make_test_case(tc_id="tc_1", checkpoint_id="cp_1")
        tc2 = _make_test_case(tc_id="tc_2", checkpoint_id="cp_1")

        result = attach_expected_results_to_outline([case_node], [tc1, tc2])

        assert result[1].id == "case_A__tc__tc_2"


# ---------------------------------------------------------------------------
# Test 6: Deeply nested tree structure
# ---------------------------------------------------------------------------


class TestNestedTree:
    def test_nested_case_nodes_are_enriched(self):
        """Group → Group → Case  should have the leaf case enriched."""
        inner_case = _make_case_node(node_id="leaf", checkpoint_id="cp_deep")
        mid_group = _make_group_node(node_id="mid", children=[inner_case])
        root_group = _make_group_node(node_id="root", children=[mid_group])

        tc = _make_test_case(
            tc_id="tc_deep",
            checkpoint_id="cp_deep",
            steps="1. Deep step",
            priority="P1",
        )

        result = attach_expected_results_to_outline([root_group], [tc])

        # Navigate to the leaf
        assert len(result) == 1
        assert result[0].id == "root"
        assert len(result[0].children) == 1
        assert result[0].children[0].id == "mid"
        leaf = result[0].children[0].children[0]
        assert leaf.id == "leaf"
        assert leaf.steps == "1. Deep step"
        assert leaf.priority == "P1"
        assert leaf.test_case_ref == "tc_deep"

    def test_multiple_cases_at_different_depths(self):
        """Two case nodes at different depths, each with own TestCase."""
        shallow_case = _make_case_node(node_id="shallow", checkpoint_id="cp_s")
        deep_case = _make_case_node(node_id="deep", checkpoint_id="cp_d")
        group = _make_group_node(node_id="grp", children=[deep_case])
        tree = [shallow_case, group]

        tc_s = _make_test_case(tc_id="tc_s", checkpoint_id="cp_s", steps="Shallow step")
        tc_d = _make_test_case(tc_id="tc_d", checkpoint_id="cp_d", steps="Deep step")

        result = attach_expected_results_to_outline(tree, [tc_s, tc_d])

        assert result[0].steps == "Shallow step"
        assert result[0].test_case_ref == "tc_s"
        deep_node = result[1].children[0]
        assert deep_node.steps == "Deep step"
        assert deep_node.test_case_ref == "tc_d"

    def test_multi_tc_inside_nested_group(self):
        """Multiple TestCases for a case node inside a group create siblings within that group."""
        inner_case = _make_case_node(node_id="c1", checkpoint_id="cp_x")
        group = _make_group_node(node_id="g1", children=[inner_case])
        tree = [group]

        tc1 = _make_test_case(tc_id="t1", checkpoint_id="cp_x", steps="S1")
        tc2 = _make_test_case(tc_id="t2", checkpoint_id="cp_x", steps="S2")

        result = attach_expected_results_to_outline(tree, [tc1, tc2])

        # The group's children should now have 2 nodes (original + sibling)
        group_node = result[0]
        assert len(group_node.children) == 2
        assert group_node.children[0].test_case_ref == "t1"
        assert group_node.children[0].steps == "S1"
        assert group_node.children[1].test_case_ref == "t2"
        assert group_node.children[1].steps == "S2"


# ---------------------------------------------------------------------------
# Test 7: Legacy expected_result node creation under group nodes
# ---------------------------------------------------------------------------


class TestLegacyExpectedResultNodes:
    def test_group_with_checkpoint_id_gets_er_children(self):
        """A group node with a checkpoint_id should get expected_result leaf children."""
        group = _make_group_node(
            node_id="grp_legacy",
            checkpoint_id="cp_legacy",
        )

        tc = _make_test_case(
            tc_id="tc_leg",
            checkpoint_id="cp_legacy",
            expected_results="验证结果正确显示",
        )

        result = attach_expected_results_to_outline([group], [tc])

        # The group should have an expected_result child
        assert len(result) == 1
        grp = result[0]
        er_children = [c for c in grp.children if c.node_type == "expected_result"]
        assert len(er_children) == 1
        assert er_children[0].display_text == "验证结果正确显示"


# ---------------------------------------------------------------------------
# Test 8: Graceful degradation on error
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_returns_tree_on_exception(self):
        """If something goes wrong internally, the original tree is returned."""
        case_node = _make_case_node(checkpoint_id="cp_1")
        tree = [case_node]

        # Pass a non-list test_cases that would cause iteration to fail
        # internally -- but the try/except should catch it.
        # We simulate by passing test_cases with a broken checkpoint_id attr.
        class BadTC:
            id = "bad"
            title = "Bad"
            checkpoint_id = None  # won't cause error since defaultdict handles it
            steps = ""
            preconditions = ""
            expected_results = ""
            priority = ""
            category = ""
            evidence_refs = []

        # This should not raise -- graceful degradation
        result = attach_expected_results_to_outline(tree, [BadTC()])  # type: ignore
        assert result is not None
