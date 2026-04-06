"""Unit tests for PreconditionGrouper."""

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
        """Cases without keywords should fall back to an '其他' bucket."""
        cases = [_tc("TC-001"), _tc("TC-002")]
        result = PreconditionGrouper().group(cases)
        assert len(result) == 1
        assert result[0].node_type == "precondition_group"
        assert result[0].title == "其他"

    def test_mixed_grouped_and_ungrouped(self) -> None:
        """Shared keyword cases group; unmatched cases go to '其他'."""
        cases = [
            _tc("TC-001", preconditions=["用户已进入 `Create Ad Group` 页面", "用户已定位到 `optimize goal` 区域"]),
            _tc("TC-002", preconditions=["系统已展示 `optimize goal` 字段", "用户可编辑 `optimize goal`"]),
            _tc("TC-003", preconditions=["系统已部署测试版本", "用户已登录系统"]),
        ]
        result = PreconditionGrouper().group(cases)
        titles = [n.title for n in result]
        assert "optimize goal" in titles
        assert "其他" in titles

    def test_different_preconditions_separate_groups(self) -> None:
        """Different primary keywords should create separate groups."""
        cases = [
            _tc("TC-001", preconditions=["用户可见 `optimize goal` 字段"]),
            _tc("TC-002", preconditions=["用户可编辑 `optimize goal` 字段"]),
            _tc("TC-003", preconditions=["广告主下存在 2 个可用 TTMS account"]),
            _tc("TC-004", preconditions=["用户必须选择 TTMS account"]),
        ]
        result = PreconditionGrouper().group(cases)
        groups = [n for n in result if n.node_type == "precondition_group"]
        assert len(groups) == 2
        assert {g.title for g in groups} == {"optimize goal", "TTMS account"}

    def test_punctuation_normalization_groups_together(self) -> None:
        """Chinese vs English punctuation should be treated as identical."""
        cases = [
            _tc("TC-001", preconditions=["条件一，条件二"]),
            _tc("TC-002", preconditions=["条件一,条件二"]),
        ]
        result = PreconditionGrouper().group(cases)
        groups = [n for n in result if n.node_type == "precondition_group"]
        assert len(groups) == 1

    def test_shared_keyword_groups_different_preconditions_together(self) -> None:
        """Cases should group by shared keyword even when full lists differ."""
        cases = [
            _tc("TC-001", preconditions=["用户已定位到 `secondary goal` 区域", "系统已部署测试版本"]),
            _tc("TC-002", preconditions=["用户可查看 `secondary goal` 选项", "广告主已启用白名单"]),
        ]
        result = PreconditionGrouper().group(cases)
        assert len(result) == 1
        assert result[0].title == "secondary goal"
        assert len(result[0].children) == 2

    def test_generic_words_fall_back_to_other_group(self) -> None:
        """Generic words like 用户/系统/页面 should not become top-level groups."""
        cases = [
            _tc("TC-001", preconditions=["用户已登录系统", "用户已进入页面"]),
            _tc("TC-002", preconditions=["系统已部署测试版本", "用户已具备操作权限"]),
        ]
        result = PreconditionGrouper().group(cases)
        assert len(result) == 1
        assert result[0].title == "其他"

    def test_case_preconditions_preserved_in_keyword_group(self) -> None:
        """Case node should keep full preconditions in keyword grouping mode."""
        cases = [
            _tc("TC-001", preconditions=["用户已定位到 `optimize goal` 区域", "系统已部署测试版本"]),
            _tc("TC-002", preconditions=["用户可编辑 `optimize goal` 字段", "用户已登录系统"]),
        ]
        result = PreconditionGrouper().group(cases)
        group = result[0]
        assert group.title == "optimize goal"
        assert group.children[0].preconditions == cases[0].preconditions
        assert group.children[1].preconditions == cases[1].preconditions

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
            _tc("TC-001", preconditions=["用户可见 `optimize goal` 字段"]),
            _tc("TC-002", preconditions=["用户可编辑 `optimize goal` 字段"]),
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

        # LLM 将 entry 1,2 合并为"已登录"，entry 3,4 合并为"广告主余额充足"
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

        # 验证每组各有 2 个用例
        for node in result:
            if node.title in ("已登录", "广告主余额充足"):
                assert len(node.children) == 2

    def test_llm_does_not_merge_non_equivalent(self) -> None:
        """LLM 不应合并语义不同的前置条件。"""
        cases = [
            _tc("TC-001", preconditions=["已登录账号"]),
            _tc("TC-002", preconditions=["已创建广告计划"]),
        ]

        # LLM 输出：每个独立成组
        mock_result = PreconditionGroupingResult(
            groups=[
                SemanticGroup(representative="已登录账号", member_indices=[1]),
                SemanticGroup(representative="已创建广告计划", member_indices=[2]),
            ]
        )
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        # 每组只有 1 个用例，低于 _MIN_GROUP_SIZE=2，变成独立 case 节点
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

        # Verify LLM was actually called before the fallback
        mock_client.generate_structured.assert_called_once()

        # 回退到关键词分桶：两个中文用例都进"其他"
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
                    member_indices=[1, 2, 999],  # 999 越界
                ),
            ]
        )
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        # 应该正常合并 1,2，忽略 999
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

        # LLM 只分组了 1,2，遗漏了 3
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
        # 第三个用例未被分组，应在"其他"或作为独立 case
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

        # 关键词分桶后：Ad Group 桶有 TC-001,TC-002；其他桶有 TC-003
        # LLM 判定 "Ad Group" 和 "已打开广告组创建界面" 语义等价
        mock_result = PreconditionGroupingResult(
            groups=[
                SemanticGroup(
                    representative="广告组页面",
                    member_indices=[1, 2],  # entry 1 = "Ad Group" bucket key, entry 2 = "已打开广告组创建界面"
                ),
            ]
        )
        mock_client = _mock_llm_client(mock_result)
        grouper = PreconditionGrouper(llm_client=mock_client)
        result = grouper.group(cases)

        # 全部 3 个用例应合并到一个组
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

        # Verify LLM was actually called
        mock_client.generate_structured.assert_called_once()

        # 空 groups → 原始桶不变 → 两个中文用例在"其他"
        assert len(result) == 1
        assert result[0].title == "其他"
        assert len(result[0].children) == 2

    def test_llm_single_unique_text_skips_merge(self) -> None:
        """All cases share the same precondition text → LLM is called but
        _llm_merge_buckets returns early because unique entries ≤ 1."""
        cases = [
            _tc("TC-001", preconditions=["已登录账号"]),
            _tc("TC-002", preconditions=["已登录账号"]),
        ]

        mock_client = MagicMock()
        grouper = PreconditionGrouper(llm_client=mock_client)
        grouper.group(cases)

        # All cases have the same text → 1 unique entry → early return → no LLM call
        mock_client.generate_structured.assert_not_called()
