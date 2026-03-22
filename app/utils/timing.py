"""流水线节点级计时基础设施。

提供 ``NodeTimer`` 记录容器、``wrap_node`` 节点包装函数和
``log_timing_report`` 汇总输出函数，用于在 LangGraph 工作流中
对每个节点的执行耗时进行无侵入式度量。

用法示例::

    timer = NodeTimer()
    wrapped = wrap_node("input_parser", input_parser_node, timer)
    result = wrapped(state)
    report = log_timing_report(timer)
"""

from __future__ import annotations

import functools
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

timing_logger = logging.getLogger("app.timing")

# 已知包含 LLM 调用的节点名集合（用于自动标记）
_LLM_NODE_NAMES: frozenset[str] = frozenset({
    "context_research",
    "checkpoint_generator",
    "checkpoint_outline_planner",
    "draft_writer",
})


@dataclass
class TimingRecord:
    """单条节点计时记录。"""

    node_name: str
    elapsed_seconds: float
    is_llm_node: bool = False
    iteration_index: int = 0
    timestamp_start: str = ""
    timestamp_end: str = ""
    had_error: bool = False

    def to_dict(self) -> dict:
        return {
            "node_name": self.node_name,
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "is_llm_node": self.is_llm_node,
            "iteration_index": self.iteration_index,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "had_error": self.had_error,
        }


class NodeTimer:
    """流水线节点级计时器。

    维护有序的 ``TimingRecord`` 列表，支持按迭代轮次筛选和导出。
    """

    def __init__(self) -> None:
        self._records: list[TimingRecord] = []

    def record(
        self,
        name: str,
        elapsed: float,
        is_llm_node: bool = False,
        iteration_index: int = 0,
        had_error: bool = False,
        timestamp_start: str = "",
        timestamp_end: str = "",
    ) -> None:
        """添加一条计时记录。"""
        self._records.append(
            TimingRecord(
                node_name=name,
                elapsed_seconds=elapsed,
                is_llm_node=is_llm_node,
                iteration_index=iteration_index,
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
                had_error=had_error,
            )
        )

    def get_records(self, iteration_index: int | None = None) -> list[TimingRecord]:
        """获取指定轮次（或全部）的计时记录。"""
        if iteration_index is None:
            return list(self._records)
        return [r for r in self._records if r.iteration_index == iteration_index]

    def total_seconds(self, iteration_index: int | None = None) -> float:
        """获取总耗时。"""
        return sum(r.elapsed_seconds for r in self.get_records(iteration_index))

    def llm_seconds(self, iteration_index: int | None = None) -> float:
        """获取 LLM 节点总耗时。"""
        return sum(
            r.elapsed_seconds
            for r in self.get_records(iteration_index)
            if r.is_llm_node
        )

    def to_dict(self) -> dict:
        """导出为可序列化字典（全部轮次）。"""
        iterations: dict[int, list[dict]] = {}
        for r in self._records:
            iterations.setdefault(r.iteration_index, []).append(r.to_dict())

        total = self.total_seconds()
        llm_total = self.llm_seconds()

        return {
            "iterations": iterations,
            "total_pipeline_seconds": round(total, 4),
            "total_llm_nodes_seconds": round(llm_total, 4),
            "llm_ratio": round(llm_total / total, 4) if total > 0 else 0.0,
        }

    def reset(self) -> None:
        """清空所有记录。"""
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def wrap_node(
    name: str,
    fn,
    timer: NodeTimer,
    is_llm_node: bool | None = None,
    iteration_index: int = 0,
):
    """包装 LangGraph 节点函数，在执行前后自动记录耗时。

    Args:
        name: 节点名称，用于日志和记录。
        fn: 原始节点函数（callable），签名为 ``(state) -> state``。
        timer: 共享的 ``NodeTimer`` 实例。
        is_llm_node: 是否标记为 LLM 密集节点。
            ``None`` 时根据 ``_LLM_NODE_NAMES`` 自动判断。
        iteration_index: 当前迭代轮次索引。

    Returns:
        与 ``fn`` 签名一致的包装函数。
    """
    if is_llm_node is None:
        is_llm_node = name in _LLM_NODE_NAMES

    @functools.wraps(fn)
    def wrapper(state):
        ts_start = _now_iso()
        start = time.monotonic()
        had_error = False
        try:
            result = fn(state)
            return result
        except Exception:
            had_error = True
            raise
        finally:
            elapsed = time.monotonic() - start
            ts_end = _now_iso()
            timer.record(
                name=name,
                elapsed=elapsed,
                is_llm_node=is_llm_node,
                iteration_index=iteration_index,
                had_error=had_error,
                timestamp_start=ts_start,
                timestamp_end=ts_end,
            )
            llm_tag = "  ⚠ LLM" if is_llm_node else ""
            error_tag = "  ✗ ERROR" if had_error else ""
            timing_logger.info(
                "[TIMING] %-30s : %8.2fs%s%s",
                name,
                elapsed,
                llm_tag,
                error_tag,
            )

    return wrapper


def log_timing_report(
    timer: NodeTimer,
    iteration_index: int | None = None,
    run_id: str = "",
) -> dict:
    """输出格式化的耗时汇总报告并返回可序列化字典。

    Args:
        timer: 计时器实例。
        iteration_index: 指定迭代轮次，``None`` 表示汇总全部。
        run_id: 可选的运行 ID，写入报告。

    Returns:
        包含节点耗时明细和汇总指标的字典。
    """
    records = timer.get_records(iteration_index)

    if not records:
        timing_logger.info("[TIMING] No timing records to report.")
        return {"nodes": [], "total_pipeline_seconds": 0.0}

    iter_label = f"iteration {iteration_index}" if iteration_index is not None else "all iterations"
    sep_double = "═" * 58
    sep_single = "─" * 58

    timing_logger.info("[TIMING] %s Timing Report (%s) %s", sep_double[:3], iter_label, sep_double[:3])

    for r in records:
        if r.node_name.startswith("__"):
            continue
        llm_tag = "  ⚠ LLM" if r.is_llm_node else ""
        error_tag = "  ✗ ERROR" if r.had_error else ""
        timing_logger.info(
            "[TIMING] %-30s : %8.2fs%s%s",
            r.node_name,
            r.elapsed_seconds,
            llm_tag,
            error_tag,
        )

    timing_logger.info("[TIMING] %s", sep_single)

    total = sum(r.elapsed_seconds for r in records)
    llm_total = sum(r.elapsed_seconds for r in records if r.is_llm_node)
    llm_ratio = (llm_total / total * 100) if total > 0 else 0.0

    timing_logger.info("[TIMING] %-30s : %8.2fs", "Total pipeline", total)
    if llm_total > 0:
        timing_logger.info(
            "[TIMING] %-30s : %8.2fs (%.1f%%)",
            "Total LLM nodes",
            llm_total,
            llm_ratio,
        )
    timing_logger.info("[TIMING] %s", sep_double)

    report = {
        "run_id": run_id,
        "iteration_index": iteration_index,
        "nodes": [r.to_dict() for r in records],
        "total_pipeline_seconds": round(total, 4),
        "total_llm_nodes_seconds": round(llm_total, 4),
        "llm_ratio": round(llm_ratio / 100, 4) if total > 0 else 0.0,
    }

    return report
