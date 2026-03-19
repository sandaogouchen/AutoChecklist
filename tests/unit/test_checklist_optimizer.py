"""单元测试：checklist_optimizer 节点。"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.domain.checklist_models import ChecklistNode
from app.nodes.checklist_optimizer import checklist_optimizer_node


# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------

class FakeTestCase:
    """模拟 TestCase 的轻量替身。"""

    __test__ = False

    def __init__(self, id: str = "TC-001", title: str = "test", **kwargs):
        self.id = id
        self.title = title
        self.preconditions = kwargs.get("preconditions", [])
        self.steps = kwargs.get("steps", [])
        self.expected_results = kwargs.get("expected_results", [])
        self.priority = kwargs.get("priority", "P2")
        self.category = kwargs.get("category", "functional")
        self.evidence_refs = kwargs.get("evidence_refs", [])
        self.checkpoint_id = kwargs.get("checkpoint_id", "")


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestChecklistOptimizerNode:
    """checklist_optimizer_node 节点函数。"""

    def test_empty_test_cases(self):
        result = checklist_optimizer_node({"test_cases": [], "language": "zh-CN"})
        assert result["test_cases"] == []
        assert result["optimized_tree"] == []

    def test_missing_test_cases_key(self):
        result = checklist_optimizer_node({"language": "zh-CN"})
        assert result["test_cases"] == []
        assert result["optimized_tree"] == []

    @patch("app.nodes.checklist_optimizer.refine_test_case")
    @patch("app.nodes.checklist_optimizer.ChecklistMerger")
    def test_normal_flow(self, MockMerger, mock_refine):
        case = FakeTestCase(id="TC-001", title="test case")
        refined_case = FakeTestCase(id="TC-001", title="refined")
        mock_refine.return_value = refined_case

        mock_merger_instance = MagicMock()
        mock_tree = [ChecklistNode(node_id="GRP-1", title="group", node_type="group")]
        mock_merger_instance.merge.return_value = mock_tree
        MockMerger.return_value = mock_merger_instance

        state = {"test_cases": [case], "language": "zh-CN"}
        result = checklist_optimizer_node(state)

        assert result["test_cases"] == [refined_case]
        assert result["optimized_tree"] == mock_tree
        mock_refine.assert_called_once_with(case, language="zh-CN")
        mock_merger_instance.merge.assert_called_once_with([refined_case])

    @patch("app.nodes.checklist_optimizer.refine_test_case", side_effect=ValueError("boom"))
    def test_refine_failure_keeps_original(self, mock_refine):
        case = FakeTestCase(id="TC-001", title="original")
        state = {"test_cases": [case], "language": "zh-CN"}
        result = checklist_optimizer_node(state)

        # 应回退到原始用例
        assert len(result["test_cases"]) == 1
        assert result["test_cases"][0].title == "original"

    @patch("app.nodes.checklist_optimizer.refine_test_case", side_effect=lambda c, **kw: c)
    @patch("app.nodes.checklist_optimizer.ChecklistMerger")
    def test_merger_failure_returns_empty_tree(self, MockMerger, mock_refine):
        case = FakeTestCase(id="TC-001")
        mock_merger_instance = MagicMock()
        mock_merger_instance.merge.side_effect = RuntimeError("trie error")
        MockMerger.return_value = mock_merger_instance

        state = {"test_cases": [case], "language": "zh-CN"}
        result = checklist_optimizer_node(state)

        # test_cases 应正常返回，tree 为空
        assert len(result["test_cases"]) == 1
        assert result["optimized_tree"] == []
