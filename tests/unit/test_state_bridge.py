"""自动状态桥接单元测试。

覆盖以下场景：
- compute_shared_keys 交集计算
- build_bridge 入向映射（正常、缺失、override）
- build_bridge 出向映射（正常、exclude）
- None 值过滤行为
- override_in 中无效 key 的 WARNING 日志
- 缓存行为验证
"""

from __future__ import annotations

import logging
from typing import TypedDict
from unittest.mock import MagicMock

import pytest

from app.graphs.state_bridge import build_bridge, compute_shared_keys


# ---- 测试用 TypedDict ----


class ParentState(TypedDict, total=False):
    shared_a: str
    shared_b: int
    shared_c: list
    parent_only: str


class ChildState(TypedDict, total=False):
    shared_a: str
    shared_b: int
    shared_c: list
    child_only: float


# ---- compute_shared_keys 测试 ----


class TestComputeSharedKeys:
    def test_basic_intersection(self):
        """交集应包含双方都有的字段。"""
        shared = compute_shared_keys(ParentState, ChildState)
        assert shared == frozenset({"shared_a", "shared_b", "shared_c"})

    def test_returns_frozenset(self):
        """返回类型应为 frozenset（可哈希，支持 lru_cache）。"""
        shared = compute_shared_keys(ParentState, ChildState)
        assert isinstance(shared, frozenset)

    def test_excludes_non_shared(self):
        """parent_only 和 child_only 不应出现在交集中。"""
        shared = compute_shared_keys(ParentState, ChildState)
        assert "parent_only" not in shared
        assert "child_only" not in shared

    def test_cache_returns_same_object(self):
        """多次调用应返回同一个缓存对象。"""
        result1 = compute_shared_keys(ParentState, ChildState)
        result2 = compute_shared_keys(ParentState, ChildState)
        assert result1 is result2

    def test_empty_intersection(self):
        """两个完全无交集的 TypedDict。"""

        class A(TypedDict, total=False):
            x: int

        class B(TypedDict, total=False):
            y: str

        shared = compute_shared_keys(A, B)
        assert shared == frozenset()


# ---- build_bridge 入向映射测试 ----


class TestBridgeInbound:
    def _make_subgraph(self, return_dict: dict):
        """创建一个 mock 子图，invoke 时返回指定 dict。"""
        sg = MagicMock()
        sg.invoke.return_value = return_dict
        return sg

    def test_forwards_shared_keys(self):
        """共享字段应正确转发到子图。"""
        sg = self._make_subgraph({"shared_a": "result_a"})
        bridge = build_bridge(sg, ParentState, ChildState)

        bridge({"shared_a": "hello", "shared_b": 42, "parent_only": "skip"})

        call_args = sg.invoke.call_args[0][0]
        assert call_args["shared_a"] == "hello"
        assert call_args["shared_b"] == 42
        assert "parent_only" not in call_args

    def test_override_in_when_missing(self):
        """字段在 state 中缺失时，使用 override_in 默认值。"""
        sg = self._make_subgraph({})
        bridge = build_bridge(
            sg, ParentState, ChildState,
            override_in={"shared_a": "default_a"},
        )

        bridge({"shared_b": 10})

        call_args = sg.invoke.call_args[0][0]
        assert call_args["shared_a"] == "default_a"

    def test_override_in_not_used_when_present(self):
        """字段在 state 中存在时，override_in 不应覆盖。"""
        sg = self._make_subgraph({})
        bridge = build_bridge(
            sg, ParentState, ChildState,
            override_in={"shared_a": "default_a"},
        )

        bridge({"shared_a": "actual_a"})

        call_args = sg.invoke.call_args[0][0]
        assert call_args["shared_a"] == "actual_a"

    def test_none_value_triggers_override(self):
        """字段在 state 中为 None 时，应使用 override_in。"""
        sg = self._make_subgraph({})
        bridge = build_bridge(
            sg, ParentState, ChildState,
            override_in={"shared_a": "fallback"},
        )

        bridge({"shared_a": None})

        call_args = sg.invoke.call_args[0][0]
        assert call_args["shared_a"] == "fallback"

    def test_none_value_skipped_without_override(self):
        """字段为 None 且无 override 时，不应传递给子图。"""
        sg = self._make_subgraph({})
        bridge = build_bridge(sg, ParentState, ChildState)

        bridge({"shared_a": None, "shared_b": 5})

        call_args = sg.invoke.call_args[0][0]
        assert "shared_a" not in call_args
        assert call_args["shared_b"] == 5

    def test_missing_field_skipped(self):
        """state 中完全没有该字段且无 override 时，跳过。"""
        sg = self._make_subgraph({})
        bridge = build_bridge(sg, ParentState, ChildState)

        bridge({})

        call_args = sg.invoke.call_args[0][0]
        assert call_args == {}


# ---- build_bridge 出向映射测试 ----


class TestBridgeOutbound:
    def _make_subgraph(self, return_dict: dict):
        sg = MagicMock()
        sg.invoke.return_value = return_dict
        return sg

    def test_forwards_shared_results(self):
        """子图返回的共享字段应回传到主图。"""
        sg = self._make_subgraph({
            "shared_a": "out_a",
            "shared_b": 99,
            "child_only": 3.14,
        })
        bridge = build_bridge(sg, ParentState, ChildState)

        result = bridge({"shared_a": "in"})

        assert result["shared_a"] == "out_a"
        assert result["shared_b"] == 99
        assert "child_only" not in result

    def test_exclude_out(self):
        """exclude_out 中的字段不应回传。"""
        sg = self._make_subgraph({
            "shared_a": "out_a",
            "shared_b": 99,
        })
        bridge = build_bridge(
            sg, ParentState, ChildState,
            exclude_out={"shared_b"},
        )

        result = bridge({"shared_a": "in"})

        assert "shared_a" in result
        assert "shared_b" not in result

    def test_missing_subgraph_result_skipped(self):
        """子图结果中不存在的共享字段应跳过（不回传空值）。"""
        sg = self._make_subgraph({"shared_a": "out_a"})
        bridge = build_bridge(sg, ParentState, ChildState)

        result = bridge({"shared_a": "in"})

        assert result == {"shared_a": "out_a"}


# ---- 日志与安全护栏测试 ----


class TestBridgeSafeguards:
    def test_stale_override_in_warning(self, caplog):
        """override_in 中不在交集的 key 应触发 WARNING。"""
        sg = MagicMock()
        sg.invoke.return_value = {}

        with caplog.at_level(logging.WARNING):
            build_bridge(
                sg, ParentState, ChildState,
                override_in={"nonexistent_key": "value"},
            )

        assert any("override_in contains keys not in shared set" in r.message for r in caplog.records)

    def test_exclude_out_non_shared_silently_ignored(self):
        """exclude_out 中不在交集的字段应安静忽略。"""
        sg = MagicMock()
        sg.invoke.return_value = {"shared_a": "val"}

        bridge = build_bridge(
            sg, ParentState, ChildState,
            exclude_out={"nonexistent_field"},
        )

        # 不应抛异常
        result = bridge({"shared_a": "in"})
        assert result["shared_a"] == "val"


# ---- 等价性测试：与旧手动桥接行为对比 ----


class TestEquivalenceWithManualBridge:
    """验证自动桥接与旧手动桥接在相同输入下产出等价结果。"""

    def test_full_state_equivalence(self):
        """提供完整状态时，自动桥接输出应包含所有预期字段。"""
        subgraph_output = {
            "shared_a": "scenario",
            "shared_b": 100,
            "shared_c": [1, 2, 3],
            "child_only": 0.5,
        }
        sg = MagicMock()
        sg.invoke.return_value = subgraph_output

        bridge = build_bridge(sg, ParentState, ChildState)
        result = bridge({
            "shared_a": "input_a",
            "shared_b": 50,
            "shared_c": [],
            "parent_only": "ignored",
        })

        # 应包含所有共享字段的子图输出
        assert result == {
            "shared_a": "scenario",
            "shared_b": 100,
            "shared_c": [1, 2, 3],
        }
