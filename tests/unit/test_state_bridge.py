"""自动状态桥接单元测试。

覆盖以下场景：
- compute_shared_keys 交集计算
- build_bridge 入向映射（正常、缺失、override、显式 None）
- build_bridge 出向映射（显式 allowlist）
- include_out / override_in 中无效 key 的 WARNING 日志
- 缓存行为验证
- 与旧手动桥接关键行为的一致性（仅允许指定字段回传）
"""

from __future__ import annotations

import logging
from typing import TypedDict
from unittest.mock import MagicMock

from app.graphs.state_bridge import build_bridge, compute_shared_keys


# ---- 测试用 TypedDict ----


class ParentState(TypedDict, total=False):
    shared_a: str | None
    shared_b: int
    shared_c: list
    parent_only: str


class ChildState(TypedDict, total=False):
    shared_a: str | None
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

    def test_none_value_preserved_without_override(self):
        """字段显式为 None 时，应保留 None，不视为缺失。"""
        sg = self._make_subgraph({})
        bridge = build_bridge(
            sg, ParentState, ChildState,
            override_in={"shared_a": "fallback"},
        )

        bridge({"shared_a": None})

        call_args = sg.invoke.call_args[0][0]
        assert "shared_a" in call_args
        assert call_args["shared_a"] is None

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

    def test_only_include_out_fields_are_returned(self):
        """只有 include_out 中显式登记的字段才应回传。"""
        sg = self._make_subgraph({
            "shared_a": "out_a",
            "shared_b": 99,
            "child_only": 3.14,
        })
        bridge = build_bridge(
            sg,
            ParentState,
            ChildState,
            include_out={"shared_a"},
        )

        result = bridge({"shared_a": "in"})

        assert result == {"shared_a": "out_a"}
        assert "shared_b" not in result
        assert "child_only" not in result

    def test_no_include_out_means_no_child_output_promoted(self):
        """未配置 include_out 时，不应有任何子图字段回传到主图。"""
        sg = self._make_subgraph({
            "shared_a": "out_a",
            "shared_b": 99,
        })
        bridge = build_bridge(sg, ParentState, ChildState)

        result = bridge({"shared_a": "in"})

        assert result == {}

    def test_allowed_key_missing_from_subgraph_result_is_skipped(self):
        """include_out 允许但子图未返回的字段，应跳过。"""
        sg = self._make_subgraph({"shared_a": "out_a"})
        bridge = build_bridge(
            sg,
            ParentState,
            ChildState,
            include_out={"shared_a", "shared_b"},
        )

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

    def test_stale_include_out_warning(self, caplog):
        """include_out 中不在交集的 key 应触发 WARNING。"""
        sg = MagicMock()
        sg.invoke.return_value = {}

        with caplog.at_level(logging.WARNING):
            build_bridge(
                sg, ParentState, ChildState,
                include_out={"nonexistent_field"},
            )

        assert any("include_out contains keys not in shared set" in r.message for r in caplog.records)


# ---- 关键行为测试：显式回传边界 ----


class TestExplicitOutboundBoundary:
    """验证自动桥接不会因 shared keys 扩大主图可见输出范围。"""

    def test_only_allowlisted_outputs_are_promoted(self):
        subgraph_output = {
            "shared_a": "scenario",
            "shared_b": 100,
            "shared_c": [1, 2, 3],
            "child_only": 0.5,
        }
        sg = MagicMock()
        sg.invoke.return_value = subgraph_output

        bridge = build_bridge(
            sg,
            ParentState,
            ChildState,
            include_out={"shared_a", "shared_c"},
        )
        result = bridge({
            "shared_a": "input_a",
            "shared_b": 50,
            "shared_c": [],
            "parent_only": "ignored",
        })

        assert result == {
            "shared_a": "scenario",
            "shared_c": [1, 2, 3],
        }
