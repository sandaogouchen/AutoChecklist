"""Unit tests for checklist_optimizer_node."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.case_models import TestCase
from app.nodes.checklist_optimizer import checklist_optimizer_node


def _tc(tc_id: str, preconditions: list[str] | None = None) -> TestCase:
    """Helper to build a minimal TestCase."""
    return TestCase(
        id=tc_id,
        title=f"Test {tc_id}",
        preconditions=preconditions or [],
        steps=["step1"],
        expected_results=["expected1"],
    )


class TestChecklistOptimizerNode:
    """Tests for the LangGraph optimizer node."""

    def test_empty_test_cases(self) -> None:
        """Empty test_cases → empty tree, no error."""
        result = checklist_optimizer_node({"test_cases": []})
        assert result["test_cases"] == []
        assert result["optimized_tree"] == []

    def test_missing_test_cases_key(self) -> None:
        """Missing key → treated as empty."""
        result = checklist_optimizer_node({})
        assert result["test_cases"] == []
        assert result["optimized_tree"] == []

    @patch("app.nodes.checklist_optimizer.get_settings")
    def test_config_disabled(self, mock_settings) -> None:
        """When config disabled → returns empty tree."""
        settings = MagicMock()
        settings.enable_checklist_optimization = False
        mock_settings.return_value = settings

        cases = [_tc("TC-001", ["登录"])]
        result = checklist_optimizer_node({"test_cases": cases})
        assert result["test_cases"] == cases
        assert result["optimized_tree"] == []

    @patch("app.nodes.checklist_optimizer.get_settings")
    def test_normal_grouping(self, mock_settings) -> None:
        """Normal operation → produces optimized_tree."""
        settings = MagicMock()
        settings.enable_checklist_optimization = True
        mock_settings.return_value = settings

        cases = [
            _tc("TC-001", ["用户已登录"]),
            _tc("TC-002", ["用户已登录"]),
        ]
        result = checklist_optimizer_node({"test_cases": cases})
        assert result["test_cases"] == cases
        assert len(result["optimized_tree"]) > 0

    @patch("app.nodes.checklist_optimizer.get_settings")
    @patch("app.nodes.checklist_optimizer.PreconditionGrouper")
    def test_graceful_degradation(self, mock_grouper_cls, mock_settings) -> None:
        """Exception in grouper → empty tree, no crash."""
        settings = MagicMock()
        settings.enable_checklist_optimization = True
        mock_settings.return_value = settings

        mock_grouper = MagicMock()
        mock_grouper.group.side_effect = RuntimeError("boom")
        mock_grouper_cls.return_value = mock_grouper

        cases = [_tc("TC-001", ["登录"])]
        result = checklist_optimizer_node({"test_cases": cases})
        assert result["test_cases"] == cases
        assert result["optimized_tree"] == []

    @patch("app.nodes.checklist_optimizer.get_settings")
    def test_does_not_modify_test_cases(self, mock_settings) -> None:
        """Node must not mutate the input test_cases list."""
        settings = MagicMock()
        settings.enable_checklist_optimization = True
        mock_settings.return_value = settings

        cases = [_tc("TC-001", ["条件A"]), _tc("TC-002", ["条件A"])]
        original_ids = [tc.id for tc in cases]
        result = checklist_optimizer_node({"test_cases": cases})
        assert [tc.id for tc in result["test_cases"]] == original_ids
