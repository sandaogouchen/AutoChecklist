"""app.utils.timing 模块的单元测试。"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.utils.timing import (
    NodeTimer,
    TimingRecord,
    log_timing_report,
    maybe_wrap,
    wrap_node,
)


# ---------------------------------------------------------------------------
# NodeTimer 基本功能
# ---------------------------------------------------------------------------

class TestNodeTimer:
    """NodeTimer 核心方法测试。"""

    def test_record_and_get_records(self):
        timer = NodeTimer()
        timer.record("node_a", 1.5, is_llm_node=False, iteration_index=0)
        timer.record("node_b", 2.0, is_llm_node=True, iteration_index=0)

        records = timer.get_records()
        assert len(records) == 2
        assert records[0].node_name == "node_a"
        assert records[1].is_llm_node is True

    def test_filter_by_iteration(self):
        timer = NodeTimer()
        timer.record("a", 1.0, iteration_index=0)
        timer.record("b", 2.0, iteration_index=1)
        timer.record("c", 3.0, iteration_index=0)

        iter0 = timer.get_records(iteration_index=0)
        assert len(iter0) == 2
        assert {r.node_name for r in iter0} == {"a", "c"}

        iter1 = timer.get_records(iteration_index=1)
        assert len(iter1) == 1
        assert iter1[0].node_name == "b"

    def test_total_seconds(self):
        timer = NodeTimer()
        timer.record("a", 1.0, iteration_index=0)
        timer.record("b", 2.0, iteration_index=0)
        timer.record("c", 3.0, iteration_index=1)

        assert timer.total_seconds() == pytest.approx(6.0)
        assert timer.total_seconds(iteration_index=0) == pytest.approx(3.0)
        assert timer.total_seconds(iteration_index=1) == pytest.approx(3.0)

    def test_llm_seconds(self):
        timer = NodeTimer()
        timer.record("a", 1.0, is_llm_node=False)
        timer.record("b", 5.0, is_llm_node=True)
        timer.record("c", 3.0, is_llm_node=True)

        assert timer.llm_seconds() == pytest.approx(8.0)

    def test_to_dict_structure(self):
        timer = NodeTimer()
        timer.record("a", 1.0, is_llm_node=False, iteration_index=0)
        timer.record("b", 2.0, is_llm_node=True, iteration_index=0)

        d = timer.to_dict()
        assert "iterations" in d
        assert "internal" in d
        assert "total_pipeline_seconds" in d
        assert "total_llm_nodes_seconds" in d
        assert "llm_ratio" in d
        assert d["total_pipeline_seconds"] == pytest.approx(3.0)
        assert d["total_llm_nodes_seconds"] == pytest.approx(2.0)

    def test_reset(self):
        timer = NodeTimer()
        timer.record("a", 1.0)
        assert len(timer) == 1

        timer.reset()
        assert len(timer) == 0
        assert timer.total_seconds() == 0.0

    def test_empty_timer(self):
        timer = NodeTimer()
        assert timer.total_seconds() == 0.0
        assert timer.llm_seconds() == 0.0
        assert timer.to_dict()["llm_ratio"] == 0.0

    def test_internal_records_excluded_from_aggregates(self):
        """内部记录不计入 total_seconds 和 llm_seconds。"""
        timer = NodeTimer()
        timer.record("a", 1.0, is_llm_node=False)
        timer.record("b", 5.0, is_llm_node=True)
        timer.record("__workflow_invoke__", 100.0, is_internal=True)

        assert timer.total_seconds() == pytest.approx(6.0)
        assert timer.llm_seconds() == pytest.approx(5.0)
        assert len(timer.get_records()) == 2
        assert len(timer.get_all_records()) == 3

    def test_internal_records_in_to_dict(self):
        """to_dict 中内部记录放在 'internal' 键下。"""
        timer = NodeTimer()
        timer.record("a", 1.0)
        timer.record("__wf__", 50.0, is_internal=True)

        d = timer.to_dict()
        assert len(d["internal"]) == 1
        assert d["internal"][0]["node_name"] == "__wf__"
        assert d["total_pipeline_seconds"] == pytest.approx(1.0)

    def test_get_records_include_internal(self):
        """显式传入 include_internal=True 时包含内部记录。"""
        timer = NodeTimer()
        timer.record("a", 1.0)
        timer.record("__internal__", 2.0, is_internal=True)

        with_internal = timer.get_records(include_internal=True)
        assert len(with_internal) == 2

        without_internal = timer.get_records(include_internal=False)
        assert len(without_internal) == 1


# ---------------------------------------------------------------------------
# wrap_node
# ---------------------------------------------------------------------------

class TestWrapNode:
    """wrap_node 包装函数测试。"""

    def test_wraps_and_records(self):
        timer = NodeTimer()

        def dummy_node(state):
            time.sleep(0.05)
            return {"result": True}

        wrapped = wrap_node("dummy", dummy_node, timer)
        result = wrapped({"input": 1})

        assert result == {"result": True}
        assert len(timer.get_records()) == 1
        record = timer.get_records()[0]
        assert record.node_name == "dummy"
        assert record.elapsed_seconds >= 0.04  # at least ~50ms
        assert record.had_error is False

    def test_records_on_error(self):
        timer = NodeTimer()

        def failing_node(state):
            time.sleep(0.02)
            raise ValueError("test error")

        wrapped = wrap_node("failing", failing_node, timer)

        with pytest.raises(ValueError, match="test error"):
            wrapped({})

        assert len(timer.get_records()) == 1
        record = timer.get_records()[0]
        assert record.node_name == "failing"
        assert record.had_error is True
        assert record.elapsed_seconds >= 0.01

    def test_auto_llm_detection(self):
        timer = NodeTimer()

        def noop(state):
            return state

        # "context_research" is in _LLM_NODE_NAMES
        wrapped = wrap_node("context_research", noop, timer)
        wrapped({})

        assert timer.get_records()[0].is_llm_node is True

    def test_explicit_llm_flag_overrides(self):
        timer = NodeTimer()

        def noop(state):
            return state

        wrapped = wrap_node("custom_node", noop, timer, is_llm_node=True)
        wrapped({})

        assert timer.get_records()[0].is_llm_node is True

    def test_preserves_function_name(self):
        timer = NodeTimer()

        def my_special_node(state):
            return state

        wrapped = wrap_node("my_special_node", my_special_node, timer)
        assert wrapped.__name__ == "my_special_node"

    def test_iteration_index_passed(self):
        timer = NodeTimer()

        def noop(state):
            return state

        wrapped = wrap_node("a", noop, timer, iteration_index=2)
        wrapped({})

        assert timer.get_records()[0].iteration_index == 2

    def test_logs_when_node_returns_awaitable(self, caplog):
        timer = NodeTimer()

        async def async_node(state):
            return {"ok": True}

        wrapped = wrap_node("mr_analyzer", async_node, timer)

        with caplog.at_level("ERROR", logger="app.timing"):
            result = wrapped({"mr_input": {"diff_files": ["a.py"]}})

        assert asyncio.iscoroutine(result)
        assert "Node returned awaitable instead of dict" in caplog.text
        assert "node=mr_analyzer" in caplog.text
        assert "return_type=coroutine" in caplog.text
        result.close()


# ---------------------------------------------------------------------------
# maybe_wrap
# ---------------------------------------------------------------------------

class TestMaybeWrap:
    """maybe_wrap 条件包装函数测试。"""

    def test_returns_original_when_timer_is_none(self):
        def original(state):
            return state

        result = maybe_wrap("test", original, None, 0)
        assert result is original

    def test_returns_wrapped_when_timer_provided(self):
        timer = NodeTimer()

        def original(state):
            return state

        result = maybe_wrap("test", original, timer, 0)
        assert result is not original
        # Call it and verify timer records
        result({})
        assert len(timer.get_records()) == 1


# ---------------------------------------------------------------------------
# log_timing_report
# ---------------------------------------------------------------------------

class TestLogTimingReport:
    """log_timing_report 汇总报告测试。"""

    def test_report_structure(self):
        timer = NodeTimer()
        timer.record("a", 1.0, is_llm_node=False, iteration_index=0)
        timer.record("b", 5.0, is_llm_node=True, iteration_index=0)

        report = log_timing_report(timer, iteration_index=0, run_id="test-run")

        assert report["run_id"] == "test-run"
        assert report["iteration_index"] == 0
        assert len(report["nodes"]) == 2
        assert report["total_pipeline_seconds"] == pytest.approx(6.0)
        assert report["total_llm_nodes_seconds"] == pytest.approx(5.0)
        assert report["llm_ratio"] == pytest.approx(5.0 / 6.0, abs=0.01)

    def test_empty_report(self):
        timer = NodeTimer()
        report = log_timing_report(timer)

        assert report["total_pipeline_seconds"] == 0.0
        assert report["nodes"] == []

    def test_all_iterations_report(self):
        timer = NodeTimer()
        timer.record("a", 1.0, iteration_index=0)
        timer.record("b", 2.0, iteration_index=1)

        report = log_timing_report(timer, iteration_index=None)
        assert report["total_pipeline_seconds"] == pytest.approx(3.0)
        assert len(report["nodes"]) == 2

    def test_internal_records_excluded_from_nodes(self):
        """内部记录不出现在 nodes 列表但出现在 internal 列表。"""
        timer = NodeTimer()
        timer.record("a", 1.0)
        timer.record("__wf__", 50.0, is_internal=True)

        report = log_timing_report(timer)
        assert len(report["nodes"]) == 1
        assert report["nodes"][0]["node_name"] == "a"
        assert len(report["internal"]) == 1
        assert report["total_pipeline_seconds"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# TimingRecord
# ---------------------------------------------------------------------------

class TestTimingRecord:
    """TimingRecord 数据类测试。"""

    def test_to_dict(self):
        record = TimingRecord(
            node_name="test_node",
            elapsed_seconds=1.2345678,
            is_llm_node=True,
            iteration_index=0,
            timestamp_start="2026-03-22T06:00:00.000+00:00",
            timestamp_end="2026-03-22T06:00:01.234+00:00",
        )
        d = record.to_dict()
        assert d["node_name"] == "test_node"
        assert d["elapsed_seconds"] == 1.2346  # rounded to 4 decimals
        assert d["is_llm_node"] is True
        assert d["had_error"] is False
        assert d["is_internal"] is False

    def test_internal_flag_in_dict(self):
        record = TimingRecord(
            node_name="__wf__",
            elapsed_seconds=10.0,
            is_internal=True,
        )
        d = record.to_dict()
        assert d["is_internal"] is True
