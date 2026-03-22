"""app.utils.timing 模块的单元测试。"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.utils.timing import (
    NodeTimer,
    TimingRecord,
    log_timing_report,
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
        assert len(timer) == 1
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

        assert len(timer) == 1
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
