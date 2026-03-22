"""draft_writer 并发补充功能的单元测试。

覆盖场景：
- 并发批次结果完整性与有序性
- 单 batch 失败的异常隔离
- 空叶子列表快速返回
- batch_size 边界（恰好一批）
- 耗时元数据结构正确性
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.domain.case_models import TestCase
from app.nodes.draft_writer import (
    DraftCaseCollection,
    _REF_LEAF_BATCH_SIZE,
    _MAX_WORKERS,
    _generate_reference_leaf_details,
    _process_single_batch,
    _build_ref_leaf_prompt,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_leaf(node_id: str, title: str) -> MagicMock:
    """创建一个模拟的 ChecklistNode 叶子节点。"""
    leaf = MagicMock()
    leaf.node_id = node_id
    leaf.title = title
    leaf.source = "reference"
    leaf.children = []
    return leaf


def _make_test_case(case_id: str, title: str) -> TestCase:
    """创建一个最简 TestCase 实例。"""
    return TestCase(
        id=case_id,
        title=title,
        steps=["步骤1"],
        expected_results=["预期1"],
    )


def _make_llm_client(
    side_effect=None,
    return_value=None,
) -> MagicMock:
    """创建模拟的 LLMClient。"""
    client = MagicMock()
    if side_effect is not None:
        client.generate_structured.side_effect = side_effect
    elif return_value is not None:
        client.generate_structured.return_value = return_value
    return client


# ---------------------------------------------------------------------------
# Tests: _build_ref_leaf_prompt
# ---------------------------------------------------------------------------


class TestBuildRefLeafPrompt:
    """测试参考叶子 prompt 构建。"""

    def test_basic_prompt(self):
        leaves = [_make_leaf("n1", "登录验证"), _make_leaf("n2", "退出流程")]
        prompt = _build_ref_leaf_prompt(leaves)
        assert "【登录验证】" in prompt
        assert "【退出流程】" in prompt
        assert "node_id=n1" in prompt
        assert "preconditions" in prompt

    def test_empty_batch(self):
        prompt = _build_ref_leaf_prompt([])
        assert "用例列表" in prompt


# ---------------------------------------------------------------------------
# Tests: _process_single_batch
# ---------------------------------------------------------------------------


class TestProcessSingleBatch:
    """测试单批次处理逻辑。"""

    def test_success(self):
        leaf = _make_leaf("n1", "测试标题")
        case = _make_test_case("TC-001", "原始标题")
        collection = DraftCaseCollection(test_cases=[case])
        client = _make_llm_client(return_value=collection)

        cases, timing = _process_single_batch(client, [leaf], 0, 1)

        assert len(cases) == 1
        assert cases[0].title == "测试标题"  # 标题被覆写为叶子标题
        assert timing["batch_index"] == 0
        assert timing["case_count"] == 1
        assert timing["had_error"] is False
        assert timing["elapsed_seconds"] >= 0

    def test_error_isolation(self):
        client = _make_llm_client(side_effect=RuntimeError("LLM 超时"))
        leaf = _make_leaf("n1", "测试")

        cases, timing = _process_single_batch(client, [leaf], 2, 5)

        assert cases == []
        assert timing["had_error"] is True
        assert timing["batch_index"] == 2
        assert timing["case_count"] == 0


# ---------------------------------------------------------------------------
# Tests: _generate_reference_leaf_details (并发核心)
# ---------------------------------------------------------------------------


class TestGenerateReferenceLeafDetails:
    """测试并发参考叶子补充。"""

    def test_empty_leaves(self):
        client = _make_llm_client()
        cases, timing = _generate_reference_leaf_details(client, [], {})

        assert cases == []
        assert timing["total_leaves"] == 0
        assert timing["total_batches"] == 0
        assert timing["batches"] == []
        client.generate_structured.assert_not_called()

    def test_concurrent_batches_basic(self):
        """验证多批次并发后结果完整、有序。"""
        leaves = [_make_leaf(f"n{i}", f"标题{i}") for i in range(85)]
        # 85 叶子 / batch_size=40 → 3 批 (40+40+5)

        def _mock_generate(**kwargs):
            # 从 prompt 中提取叶子数量来决定返回多少 case
            prompt = kwargs.get("user_prompt", "")
            count = prompt.count("【")
            cases = [_make_test_case(f"TC-{i}", f"case-{i}") for i in range(count)]
            return DraftCaseCollection(test_cases=cases)

        client = _make_llm_client()
        client.generate_structured.side_effect = _mock_generate

        cases, timing = _generate_reference_leaf_details(client, leaves, {})

        # 结果完整
        assert len(cases) == 85
        # 耗时元数据正确
        assert timing["total_leaves"] == 85
        assert timing["total_batches"] == 3
        assert timing["batch_size"] == _REF_LEAF_BATCH_SIZE
        assert timing["max_workers"] == _MAX_WORKERS
        assert len(timing["batches"]) == 3
        # 按 index 有序
        indices = [b["batch_index"] for b in timing["batches"]]
        assert indices == [0, 1, 2]
        # leaf_count 分布正确
        leaf_counts = [b["leaf_count"] for b in timing["batches"]]
        assert leaf_counts == [40, 40, 5]

    def test_single_batch_failure_isolation(self):
        """一个 batch 失败不影响其他 batch。"""
        leaves = [_make_leaf(f"n{i}", f"标题{i}") for i in range(80)]
        # 80 叶子 → 2 批

        call_count = 0

        def _mock_generate(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("模拟 LLM 失败")
            cases = [_make_test_case(f"TC-{i}", f"case-{i}") for i in range(40)]
            return DraftCaseCollection(test_cases=cases)

        client = _make_llm_client()
        client.generate_structured.side_effect = _mock_generate

        cases, timing = _generate_reference_leaf_details(client, leaves, {})

        # 第一批失败（0 条），第二批成功（40 条）
        assert len(cases) == 40
        assert timing["total_batches"] == 2
        error_batches = [b for b in timing["batches"] if b["had_error"]]
        ok_batches = [b for b in timing["batches"] if not b["had_error"]]
        assert len(error_batches) == 1
        assert len(ok_batches) == 1

    def test_batch_size_boundary(self):
        """恰好 40 个叶子 = 1 batch。"""
        leaves = [_make_leaf(f"n{i}", f"标题{i}") for i in range(40)]

        def _mock_generate(**kwargs):
            cases = [_make_test_case(f"TC-{i}", f"case-{i}") for i in range(40)]
            return DraftCaseCollection(test_cases=cases)

        client = _make_llm_client()
        client.generate_structured.side_effect = _mock_generate

        cases, timing = _generate_reference_leaf_details(client, leaves, {})

        assert len(cases) == 40
        assert timing["total_batches"] == 1
        assert timing["batches"][0]["leaf_count"] == 40

    def test_timing_metadata_structure(self):
        """验证耗时元数据包含所有必需字段。"""
        leaves = [_make_leaf("n1", "标题1")]

        def _mock_generate(**kwargs):
            return DraftCaseCollection(test_cases=[_make_test_case("TC-1", "c1")])

        client = _make_llm_client()
        client.generate_structured.side_effect = _mock_generate

        _, timing = _generate_reference_leaf_details(client, leaves, {})

        # 顶层字段
        assert "batch_size" in timing
        assert "max_workers" in timing
        assert "total_leaves" in timing
        assert "total_batches" in timing
        assert "total_elapsed_seconds" in timing
        assert "batches" in timing
        assert isinstance(timing["total_elapsed_seconds"], float)

        # batch 记录字段
        batch = timing["batches"][0]
        assert "batch_index" in batch
        assert "leaf_count" in batch
        assert "case_count" in batch
        assert "elapsed_seconds" in batch
        assert "had_error" in batch

    def test_title_preserved_from_leaf(self):
        """验证生成的 case 标题被覆写为原始叶子标题。"""
        leaves = [_make_leaf("n1", "原始中文标题")]

        def _mock_generate(**kwargs):
            # LLM 可能返回不同标题
            return DraftCaseCollection(
                test_cases=[_make_test_case("TC-1", "LLM自动生成标题")]
            )

        client = _make_llm_client()
        client.generate_structured.side_effect = _mock_generate

        cases, _ = _generate_reference_leaf_details(client, leaves, {})

        assert cases[0].title == "原始中文标题"
