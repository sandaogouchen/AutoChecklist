"""Unit tests for XMindReferenceAnalyzer.

Covers:
- Skeleton extraction (top 3 layers)
- Representative path sampling (uniform, seed=42)
- Statistics (node count, leaf count, max depth, depth distribution)
- formatted_summary rendering
- generate_routing_hints with Jaccard matching
"""

from __future__ import annotations

import pytest

from app.domain.xmind_reference_models import XMindReferenceNode, XMindReferenceSummary
from app.services.xmind_reference_analyzer import XMindReferenceAnalyzer


@pytest.fixture
def analyzer() -> XMindReferenceAnalyzer:
    return XMindReferenceAnalyzer()


def _build_sample_tree() -> XMindReferenceNode:
    """Build a sample tree:

    Root
    ├── 功能测试
    │   ├── 登录模块
    │   │   ├── 正常登录
    │   │   └── 异常登录
    │   └── 注册模块
    │       └── 新用户注册
    └── 性能测试
        ├── 压力测试
        └── 负载测试
    """
    return XMindReferenceNode(
        title="Root",
        children=[
            XMindReferenceNode(
                title="功能测试",
                children=[
                    XMindReferenceNode(
                        title="登录模块",
                        children=[
                            XMindReferenceNode(title="正常登录"),
                            XMindReferenceNode(title="异常登录"),
                        ],
                    ),
                    XMindReferenceNode(
                        title="注册模块",
                        children=[
                            XMindReferenceNode(title="新用户注册"),
                        ],
                    ),
                ],
            ),
            XMindReferenceNode(
                title="性能测试",
                children=[
                    XMindReferenceNode(title="压力测试"),
                    XMindReferenceNode(title="负载测试"),
                ],
            ),
        ],
    )


class TestAnalyze:
    """Tests for the analyze() method."""

    def test_basic_statistics(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = _build_sample_tree()
        summary = analyzer.analyze(root, source_file="test.xmind")

        assert isinstance(summary, XMindReferenceSummary)
        assert summary.source_file == "test.xmind"
        # Root(1) + 功能测试(1) + 登录模块(1) + 正常登录(1) + 异常登录(1)
        # + 注册模块(1) + 新用户注册(1) + 性能测试(1) + 压力测试(1) + 负载测试(1)
        assert summary.total_nodes == 10
        # Leaves: 正常登录, 异常登录, 新用户注册, 压力测试, 负载测试
        assert summary.total_leaf_nodes == 5
        assert summary.max_depth == 3

    def test_depth_distribution(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = _build_sample_tree()
        summary = analyzer.analyze(root, source_file="test.xmind")

        # depth 0: Root(1), depth 1: 功能测试+性能测试(2),
        # depth 2: 登录模块+注册模块+压力测试+负载测试(4),
        # depth 3: 正常登录+异常登录+新用户注册(3)
        assert summary.depth_distribution[0] == 1
        assert summary.depth_distribution[1] == 2
        assert summary.depth_distribution[2] == 4
        assert summary.depth_distribution[3] == 3

    def test_skeleton_contains_branches(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = _build_sample_tree()
        summary = analyzer.analyze(root, source_file="test.xmind")

        assert "Root" in summary.skeleton
        assert "功能测试" in summary.skeleton
        assert "性能测试" in summary.skeleton
        assert "登录模块" in summary.skeleton

    def test_sampled_paths_not_empty(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = _build_sample_tree()
        summary = analyzer.analyze(root, source_file="test.xmind")

        assert len(summary.sampled_paths) > 0
        # All paths should start from root
        for path in summary.sampled_paths:
            assert "Root" in path

    def test_sampled_paths_deterministic(self, analyzer: XMindReferenceAnalyzer) -> None:
        """Sampling with seed=42 should be deterministic."""
        root = _build_sample_tree()
        summary1 = analyzer.analyze(root, source_file="a.xmind")
        summary2 = analyzer.analyze(root, source_file="b.xmind")
        assert summary1.sampled_paths == summary2.sampled_paths

    def test_formatted_summary_structure(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = _build_sample_tree()
        summary = analyzer.analyze(root, source_file="test.xmind")

        assert summary.formatted_summary.startswith("[参考 Checklist 结构]")
        assert "结构骨架" in summary.formatted_summary
        assert "代表性路径示例" in summary.formatted_summary
        assert "统计概况" in summary.formatted_summary

    def test_top_prefixes(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = _build_sample_tree()
        summary = analyzer.analyze(root, source_file="test.xmind")

        assert len(summary.top_prefixes) > 0
        for prefix in summary.top_prefixes:
            assert "Root" in prefix


class TestGenerateRoutingHints:
    """Tests for the generate_routing_hints() method."""

    def test_routing_with_matching_checkpoints(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = _build_sample_tree()
        summary = analyzer.analyze(root, source_file="test.xmind")

        hints = analyzer.generate_routing_hints(
            summary, ["登录功能测试", "性能压力测试", "安全测试"]
        )

        assert isinstance(hints, str)
        assert "登录功能测试" in hints
        assert "性能压力测试" in hints
        assert "安全测试" in hints

    def test_routing_empty_checkpoints(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = _build_sample_tree()
        summary = analyzer.analyze(root, source_file="test.xmind")

        hints = analyzer.generate_routing_hints(summary, [])
        assert hints == ""

    def test_routing_no_match_shows_fallback(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = _build_sample_tree()
        summary = analyzer.analyze(root, source_file="test.xmind")

        hints = analyzer.generate_routing_hints(summary, ["xyz_unrelated_abc"])
        # Should either suggest a branch or indicate no clear match
        assert "xyz_unrelated_abc" in hints

    def test_routing_returns_empty_for_no_branches(self, analyzer: XMindReferenceAnalyzer) -> None:
        leaf_only = XMindReferenceNode(title="Solo")
        summary = analyzer.analyze(leaf_only, source_file="solo.xmind")

        hints = analyzer.generate_routing_hints(summary, ["测试"])
        assert hints == ""


class TestEdgeCases:
    """Edge case tests."""

    def test_single_node_tree(self, analyzer: XMindReferenceAnalyzer) -> None:
        root = XMindReferenceNode(title="OnlyRoot")
        summary = analyzer.analyze(root, source_file="single.xmind")

        assert summary.total_nodes == 1
        assert summary.total_leaf_nodes == 1
        assert summary.max_depth == 0
        assert len(summary.sampled_paths) == 0

    def test_wide_tree(self, analyzer: XMindReferenceAnalyzer) -> None:
        """Tree with many first-level branches."""
        children = [XMindReferenceNode(title=f"Branch_{i}") for i in range(20)]
        root = XMindReferenceNode(title="Wide", children=children)
        summary = analyzer.analyze(root, source_file="wide.xmind")

        assert summary.total_nodes == 21
        assert summary.total_leaf_nodes == 20
