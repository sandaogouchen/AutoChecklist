"""Unit tests for checklist optimizer node."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.nodes.checklist_optimizer import build_checklist_optimizer_node


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
        llm_client = MagicMock()
        node = build_checklist_optimizer_node(llm_client)

        result = node({"test_cases": []})

        assert result["test_cases"] == []
        assert result["optimized_tree"] == []
        llm_client.generate_structured.assert_not_called()

    def test_missing_test_cases_key(self) -> None:
        """Missing key → treated as empty."""
        llm_client = MagicMock()
        node = build_checklist_optimizer_node(llm_client)

        result = node({})

        assert result["test_cases"] == []
        assert result["optimized_tree"] == []
        llm_client.generate_structured.assert_not_called()

    @patch("app.nodes.checklist_optimizer.get_settings")
    def test_config_disabled(self, mock_settings) -> None:
        """When config disabled → returns empty tree."""
        settings = MagicMock()
        settings.enable_checklist_optimization = False
        mock_settings.return_value = settings

        llm_client = MagicMock()
        node = build_checklist_optimizer_node(llm_client)
        cases = [_tc("TC-001", ["登录"])]

        result = node({"test_cases": cases})

        assert result["test_cases"] == cases
        assert result["optimized_tree"] == []
        llm_client.generate_structured.assert_not_called()

    @patch("app.nodes.checklist_optimizer.get_settings")
    @patch("app.nodes.checklist_optimizer.ChecklistMerger")
    @patch("app.nodes.checklist_optimizer.SemanticPathNormalizer")
    def test_normal_grouping(
        self,
        mock_normalizer_cls,
        mock_merger_cls,
        mock_settings,
    ) -> None:
        """Normal operation → produces optimized_tree."""
        settings = MagicMock()
        settings.enable_checklist_optimization = True
        mock_settings.return_value = settings

        normalized_paths = [MagicMock()]
        optimized_tree = [
            ChecklistNode(
                node_id="GRP-001",
                title="进入页面",
                node_type="group",
            )
        ]

        mock_normalizer = MagicMock()
        mock_normalizer.normalize.return_value = normalized_paths
        mock_normalizer_cls.return_value = mock_normalizer

        mock_merger = MagicMock()
        mock_merger.merge.return_value = optimized_tree
        mock_merger_cls.return_value = mock_merger

        llm_client = MagicMock()
        node = build_checklist_optimizer_node(llm_client)
        cases = [_tc("TC-001", ["用户已登录"]), _tc("TC-002", ["用户已登录"])]

        result = node({"test_cases": cases})

        assert result["test_cases"] == cases
        assert result["optimized_tree"] == optimized_tree
        mock_normalizer_cls.assert_called_once_with(llm_client)
        mock_normalizer.normalize.assert_called_once_with(cases)
        mock_merger.merge.assert_called_once_with(normalized_paths)

    @patch("app.nodes.checklist_optimizer.get_settings")
    @patch("app.nodes.checklist_optimizer.SemanticPathNormalizer")
    def test_graceful_degradation(self, mock_normalizer_cls, mock_settings) -> None:
        """Exception in semantic optimizer → empty tree, no crash."""
        settings = MagicMock()
        settings.enable_checklist_optimization = True
        mock_settings.return_value = settings

        mock_normalizer = MagicMock()
        mock_normalizer.normalize.side_effect = RuntimeError("boom")
        mock_normalizer_cls.return_value = mock_normalizer

        llm_client = MagicMock()
        node = build_checklist_optimizer_node(llm_client)
        cases = [_tc("TC-001", ["登录"])]

        result = node({"test_cases": cases})

        assert result["test_cases"] == cases
        assert result["optimized_tree"] == []

    @patch("app.nodes.checklist_optimizer.get_settings")
    @patch("app.nodes.checklist_optimizer.ChecklistMerger")
    @patch("app.nodes.checklist_optimizer.SemanticPathNormalizer")
    def test_does_not_modify_test_cases(
        self,
        mock_normalizer_cls,
        mock_merger_cls,
        mock_settings,
    ) -> None:
        """Node must not mutate the input test_cases list."""
        settings = MagicMock()
        settings.enable_checklist_optimization = True
        mock_settings.return_value = settings

        mock_normalizer = MagicMock()
        mock_normalizer.normalize.return_value = [MagicMock()]
        mock_normalizer_cls.return_value = mock_normalizer

        mock_merger = MagicMock()
        mock_merger.merge.return_value = []
        mock_merger_cls.return_value = mock_merger

        llm_client = MagicMock()
        node = build_checklist_optimizer_node(llm_client)
        cases = [_tc("TC-001", ["条件A"]), _tc("TC-002", ["条件A"])]
        original_ids = [tc.id for tc in cases]

        result = node({"test_cases": cases})

        assert [tc.id for tc in result["test_cases"]] == original_ids
