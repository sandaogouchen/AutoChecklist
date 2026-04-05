from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.domain.precondition_models import (
    PreconditionGroupingResult,
    SemanticGroup,
)
from app.services.precondition_grouper import (
    PreconditionGrouper,
    _extract_primary_keyword,
    _normalize_preconditions,
    _normalize_text,
)


def _tc(
    case_id: str,
    title: str | None = None,
    preconditions: list[str] | None = None,
) -> TestCase:
    return TestCase(
        id=case_id,
        title=title or case_id,
        objective="obj",
        preconditions=preconditions or [],
        steps=["step 1"],
        expected_results=["ok"],
    )


class TestNormalizeHelpers:
    def test_normalize_text_nfkc_and_whitespace(self) -> None:
        raw = "  A\u3000B   C  "
        assert _normalize_text(raw) == "A B C"

    def test_normalize_preconditions_filters_empty(self) -> None:
        values = ["  foo  ", "", "   ", "bar"]
        assert _normalize_preconditions(values) == ("foo", "bar")


class TestExtractPrimaryKeyword:
    def test_extract_from_backticks(self) -> None:
        text = "用户可见 `optimize goal` 字段"
        assert _extract_primary_keyword(text) == "optimize goal"

    def test_extract_longest_ascii_phrase(self) -> None:
        text = "在 Ad Group creation 页面点击 Save Draft"
        assert _extract_primary_keyword(text) == "Group creation"

    def test_extract_chinese_primary_keyword(self) -> None:
        text = "已创建广告计划且预算充足"
        assert _extract_primary_keyword(text) == "广告计划"

    def test_extract_none_when_only_noise(self) -> None:
        text = "用户可以成功查看页面信息"
        assert _extract_primary_keyword(text) is None


class TestGroupingBehavior:
    def test_group_empty_input(self) -> None:
        grouper = PreconditionGrouper()
        assert grouper.group([]) == []

    def test_group_duplicate_preconditions_same_bucket(self) -> None:
        cases = [
            _tc("TC-001", preconditions=["用户可见 `optimize goal` 字段"]),
            _tc("TC-002", preconditions=["用户可编辑 `optimize goal` 字段"]),
        ]
        grouper = PreconditionGrouper()

        result = grouper.group(cases)

        assert len(result) == 1
        group = result[0]
        assert group.node_type == "precondition_group"
        assert group.title == "optimize goal"
        assert [c.source_case_id for c in group.children] == ["TC-001", "TC-002"]

    def test_group_mixed_keyword_and_other(self) -> None:
        cases = [
            _tc("TC-001", preconditions=["用户可见 `optimize goal` 字段"]),
            _tc("TC-002", preconditions=["进入白名单配置页"]),
            _tc("TC-003", preconditions=["系统存在历史数据"]),
        ]
        grouper = PreconditionGrouper()

        result = grouper.group(cases)

        assert len(result) == 3
        assert {node.node_type for node in result} == {"case"}
        assert {node.title for node in result} == {"TC-001", "TC-002", "TC-003"}

    def test_group_keyword_bucket_with_two_cases_and_other_bucket(self) -> None:
        cases = [
            _tc("TC-001", preconditions=["进入广告组创建页"]),
            _tc("TC-002", preconditions=["已打开广告组编辑页"]),
            _tc("TC-003", preconditions=["系统存在历史数据"]),
        ]
        grouper = PreconditionGrouper()

        result = grouper.group(cases)

        assert len(result) == 2
        group = next(node for node in result if node.node_type == "precondition_group")
        single = next(node for node in result if node.node_type == "case")
        assert group.title == "广告组"
        assert [c.source_case_id for c in group.children] == ["TC-001", "TC-002"]
        assert single.source_case_id == "TC-003"

    def test_group_case_with_multiple_keywords_prefers_more_global_frequency(self) -> None:
        cases = [
            _tc("TC-001", preconditions=["已创建广告计划", "进入广告组编辑页"]),
            _tc("TC-002", preconditions=["进入广告组创建页"]),
            _tc("TC-003", preconditions=["进入广告组详情页"]),
        ]
        grouper = PreconditionGrouper()

        result = grouper.group(cases)

        assert len(result) == 1
        group = result[0]
        assert group.title == "广告组"
        assert [c.source_case_id for c in group.children] == ["TC-001", "TC-002", "TC-003"]

    def test_group_case_with_frequency_tie_prefers_first_appeared(self) -> None:
        cases = [
            _tc("TC-001", preconditions=["已创建广告计划", "进入广告组编辑页"]),
            _tc("TC-002", preconditions=["进入广告计划创建页"]),
            _tc("TC-003", preconditions=["进入广告组详情页"]),
        ]
        grouper = PreconditionGrouper()

        result = grouper.group(cases)

        assert len(result) == 2
        first = result[0]
        second = result[1]
        assert first.title == "广告计划"
        assert second.title == "广告组"
        assert [c.source_case_id for c in first.children] == ["TC-001", "TC-002"]
        assert [c.source_case_id for c in second.children] == ["TC-003"]

    def test_build_tree_never_exceeds_depth_three(self) -> None:
        cases = [
            _tc("TC-001", preconditions=["进入广告计划创建页"]),
            _tc("TC-002", preconditions=["进入广告计划编辑页"]),
        ]
        grouper = PreconditionGrouper()

        result = grouper.group(cases)

        assert len(result) == 1
        group = result[0]
        assert group.node_type == "precondition_group"
        assert all(child.node_type == "case" for child in group.children)
        assert all(not child.children for child in group.children)

    def test_stable_bucket_order(self) -> None:
        cases = [
            _tc("TC-001", preconditions=["进入广告计划创建页"]),
            _tc("TC-002", preconditions=["进入白名单配置页"]),
            _tc("TC-003", preconditions=["进入广告计划编辑页"]),
            _tc("TC-004", preconditions=["系统存在历史数据"]),
            _tc("TC-005", preconditions=["进入白名单详情页"]),
        ]
        grouper = PreconditionGrouper()

        result = grouper.group(cases)

        assert [n.title for n in result] == ["广告计划", "白名单", "TC-004"]

    def test_output_shape_matches_contract(self) -> None:
        cases = [
            _tc("TC-001", preconditions=["进入广告计划创建页"]),
            _tc("TC-002", preconditions=["进入广告计划编辑页"]),
        ]
        grouper = PreconditionGrouper()

        result = grouper.group(cases)

        assert isinstance(result, list)
        assert all(isinstance(node, ChecklistNode) for node in result)
        group = result[0]
        assert group.node_type == "precondition_group"
        assert group.source_case_id is None
        assert all(child.source_case_id is not None for child in group.children)

    def test_performance_100_cases(self) -> None:
        cases = [
            _tc(f"TC-{i:03d}", preconditions=["进入广告计划创建页"])
            for i in range(100)
        ]
        grouper = PreconditionGrouper()

        start = time.time()
        result = grouper.group(cases)
        elapsed = time.time() - start
        assert elapsed < 1.0
        assert len(result) > 0


# ---------------------------------------------------------------------------
# LLM 语义分组测试
# ---------------------------------------------------------------------------

def _mock_llm_client(grouping_result: PreconditionGroupingResult) -> MagicMock:
    """创建返回指定分组结果的 Mock LLMClient。"""
    client = MagicMock()
    client.generate_structured.return_value = grouping_result
    return client


class TestLLMSemanticMerge:
    """Tests for LLM-based semantic grouping in PreconditionGrouper."""

    def test_llm_merges_semantically_equivalent_other_cases(self) -> None:
        """'已登录账号' 和 '用户处于登录状态' 在'其他'桶中被 LLM 合并。"""
        cases = [
            _tc("TC-001", preconditions=["已登录账号"]),
            _tc("TC-002", preconditions=["用户处于登录状态"]),
            _tc("TC-003", preconditions=["广告主余额 > 0"]),
            _tc("TC-004", preconditions=["广告主账户有余额"]),
        ]

        mock_result = PreconditionGroupingResult(
            groups=[
                SemanticGroup(representative="已登录", member_indices=[1, 2]),
                SemanticGroup(representative="广告主余额充足", member_indices=[3, 4]),
            ]
        )
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        titles = {n.title for n in result}
        assert "已登录" in titles
        assert "广告主余额充足" in titles
        assert "其他" not in titles

        for node in result:
            if node.title in ("已登录", "广告主余额充足"):
                assert len(node.children) == 2

    def test_llm_does_not_merge_non_equivalent(self) -> None:
        """LLM 不应合并语义不同的前置条件。"""
        cases = [
            _tc("TC-001", preconditions=["已登录账号"]),
            _tc("TC-002", preconditions=["已创建广告计划"]),
        ]

        mock_result = PreconditionGroupingResult(
            groups=[
                SemanticGroup(representative="已登录账号", member_indices=[1]),
                SemanticGroup(representative="已创建广告计划", member_indices=[2]),
            ]
        )
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        case_nodes = [n for n in result if n.node_type == "case"]
        assert len(case_nodes) == 2

    def test_llm_failure_fallback(self) -> None:
        """LLM 调用失败时回退到纯关键词分桶结果。"""
        cases = [
            _tc("TC-001", preconditions=["已登录账号"]),
            _tc("TC-002", preconditions=["用户处于登录状态"]),
        ]

        mock_client = MagicMock()
        mock_client.generate_structured.side_effect = RuntimeError("LLM service unavailable")

        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        mock_client.generate_structured.assert_called_once()
        assert len(result) == 1
        assert result[0].title == "其他"
        assert len(result[0].children) == 2

    def test_llm_invalid_indices_ignored(self) -> None:
        """LLM 返回越界的 member_indices 时安全忽略。"""
        cases = [
            _tc("TC-001", preconditions=["已登录账号"]),
            _tc("TC-002", preconditions=["用户处于登录状态"]),
        ]

        mock_result = PreconditionGroupingResult(
            groups=[
                SemanticGroup(
                    representative="已登录",
                    member_indices=[1, 2, 999],
                ),
            ]
        )
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        merged = [n for n in result if n.title == "已登录"]
        assert len(merged) == 1
        assert len(merged[0].children) == 2

    def test_llm_omits_some_entries(self) -> None:
        """LLM 遗漏部分前置条件时，遗漏的保持在'其他'桶。"""
        cases = [
            _tc("TC-001", preconditions=["已登录账号"]),
            _tc("TC-002", preconditions=["用户处于登录状态"]),
            _tc("TC-003", preconditions=["网络环境正常"]),
        ]

        mock_result = PreconditionGroupingResult(
            groups=[
                SemanticGroup(representative="已登录", member_indices=[1, 2]),
            ]
        )
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        titles = {n.title for n in result}
        assert "已登录" in titles
        remaining = [n for n in result if n.title != "已登录"]
        assert len(remaining) >= 1

    def test_llm_client_none_uses_keyword_only(self) -> None:
        """llm_client=None 时完全走关键词分桶逻辑。"""
        cases = [
            _tc("TC-001", preconditions=["用户可见 `optimize goal` 字段"]),
            _tc("TC-002", preconditions=["用户可编辑 `optimize goal` 字段"]),
        ]
        grouper = PreconditionGrouper(llm_client=None)
        result = grouper.group(cases)

        assert len(result) == 1
        assert result[0].title == "optimize goal"
        assert len(result[0].children) == 2

    def test_llm_representative_naming(self) -> None:
        """验证合并后的分组使用 LLM 选定的 representative 名称。"""
        cases = [
            _tc("TC-001", preconditions=["广告主余额 > 0"]),
            _tc("TC-002", preconditions=["广告主账户有余额"]),
        ]

        mock_result = PreconditionGroupingResult(
            groups=[
                SemanticGroup(
                    representative="广告主余额充足",
                    member_indices=[1, 2],
                ),
            ]
        )
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        group = [n for n in result if n.node_type == "precondition_group"]
        assert len(group) == 1
        assert group[0].title == "广告主余额充足"

    def test_llm_merges_keyword_bucket_with_other(self) -> None:
        """LLM 可以将关键词桶和'其他'桶中的用例合并。"""
        cases = [
            _tc("TC-001", preconditions=["用户已进入 `Ad Group` 创建页面"]),
            _tc("TC-002", preconditions=["用户在 `Ad Group` 编辑页面"]),
            _tc("TC-003", preconditions=["已打开广告组创建界面"]),
        ]

        mock_result = PreconditionGroupingResult(
            groups=[
                SemanticGroup(
                    representative="广告组页面",
                    member_indices=[1, 2],
                ),
            ]
        )
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        merged = [n for n in result if n.title == "广告组页面"]
        assert len(merged) == 1
        assert len(merged[0].children) == 3

    def test_llm_empty_groups_response(self) -> None:
        """LLM 返回空 groups 列表时，原始桶不受影响。"""
        cases = [
            _tc("TC-001", preconditions=["已登录账号"]),
            _tc("TC-002", preconditions=["用户处于登录状态"]),
        ]

        mock_result = PreconditionGroupingResult(groups=[])
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        mock_client.generate_structured.assert_called_once()
        assert len(result) == 1
        assert result[0].title == "其他"
        assert len(result[0].children) == 2

    def test_llm_single_unique_text_skips_merge(self) -> None:
        """All cases share the same precondition text -> no LLM call."""
        cases = [
            _tc("TC-001", preconditions=["已登录账号"]),
            _tc("TC-002", preconditions=["已登录账号"]),
        ]

        mock_client = MagicMock()
        grouper = PreconditionGrouper(llm_client=mock_client)
        grouper.group(cases)

        mock_client.generate_structured.assert_not_called()
