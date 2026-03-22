"""Integration / end-to-end test for XMind reference pipeline.

Exercises the full flow:
  .xmind file → XMindParser → XMindReferenceAnalyzer → loader node → state update

Requirements:
- No LLM calls
- No network access
- Deterministic (seed=42 sampling)
"""

from __future__ import annotations

import json
import zipfile

import pytest

from app.domain.xmind_reference_models import XMindReferenceSummary
from app.nodes.xmind_reference_loader import build_xmind_reference_loader_node
from app.parsers.xmind_parser import XMindParser
from app.services.xmind_reference_analyzer import XMindReferenceAnalyzer


def _create_realistic_xmind(path: str) -> None:
    """Create a realistic .xmind file for integration testing.

    Structure:
      支付系统 Checklist
      ├── 功能测试
      │   ├── 支付流程
      │   │   ├── 正常支付
      │   │   ├── 异常支付
      │   │   └── 超时处理
      │   └── 退款流程
      │       ├── 全额退款
      │       └── 部分退款
      ├── 性能测试
      │   ├── 并发支付
      │   └── 大额支付
      └── 安全测试
          ├── SQL注入
          └── XSS攻击
    """
    content = [
        {
            "rootTopic": {
                "title": "支付系统 Checklist",
                "children": {
                    "attached": [
                        {
                            "title": "功能测试",
                            "children": {
                                "attached": [
                                    {
                                        "title": "支付流程",
                                        "children": {
                                            "attached": [
                                                {"title": "正常支付"},
                                                {"title": "异常支付"},
                                                {"title": "超时处理"},
                                            ]
                                        },
                                    },
                                    {
                                        "title": "退款流程",
                                        "children": {
                                            "attached": [
                                                {"title": "全额退款"},
                                                {"title": "部分退款"},
                                            ]
                                        },
                                    },
                                ]
                            },
                        },
                        {
                            "title": "性能测试",
                            "children": {
                                "attached": [
                                    {"title": "并发支付"},
                                    {"title": "大额支付"},
                                ]
                            },
                        },
                        {
                            "title": "安全测试",
                            "children": {
                                "attached": [
                                    {"title": "SQL注入"},
                                    {"title": "XSS攻击"},
                                ]
                            },
                        },
                    ]
                },
            }
        }
    ]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False))


class TestXMindReferenceEndToEnd:
    """Full pipeline integration tests."""

    def test_full_pipeline(self, tmp_path) -> None:
        """Parse → analyze → loader node → state update."""
        xmind_path = str(tmp_path / "payment.xmind")
        _create_realistic_xmind(xmind_path)

        parser = XMindParser()
        analyzer = XMindReferenceAnalyzer()
        node = build_xmind_reference_loader_node(parser, analyzer)

        state = {"reference_xmind_path": xmind_path}
        result = node(state)

        assert "xmind_reference_summary" in result
        summary: XMindReferenceSummary = result["xmind_reference_summary"]

        # Verify statistics
        assert summary.total_nodes == 14  # count all nodes
        assert summary.total_leaf_nodes == 7  # 7 leaf nodes
        assert summary.max_depth == 3

        # Verify skeleton contains key branches
        assert "支付系统 Checklist" in summary.skeleton
        assert "功能测试" in summary.skeleton
        assert "性能测试" in summary.skeleton
        assert "安全测试" in summary.skeleton

        # Verify sampled paths contain full paths
        assert len(summary.sampled_paths) > 0
        has_payment_path = any("支付" in p for p in summary.sampled_paths)
        assert has_payment_path

        # Verify formatted summary
        assert summary.formatted_summary.startswith("[参考 Checklist 结构]")

    def test_deterministic_sampling(self, tmp_path) -> None:
        """Multiple runs with same input produce identical output."""
        xmind_path = str(tmp_path / "payment.xmind")
        _create_realistic_xmind(xmind_path)

        parser = XMindParser()
        analyzer = XMindReferenceAnalyzer()
        node = build_xmind_reference_loader_node(parser, analyzer)

        result1 = node({"reference_xmind_path": xmind_path})
        result2 = node({"reference_xmind_path": xmind_path})

        s1 = result1["xmind_reference_summary"]
        s2 = result2["xmind_reference_summary"]

        assert s1.sampled_paths == s2.sampled_paths
        assert s1.skeleton == s2.skeleton
        assert s1.formatted_summary == s2.formatted_summary

    def test_routing_hints_integration(self, tmp_path) -> None:
        """Routing hints work with the analyzer and a real parsed tree."""
        xmind_path = str(tmp_path / "payment.xmind")
        _create_realistic_xmind(xmind_path)

        parser = XMindParser()
        analyzer = XMindReferenceAnalyzer()

        root = parser.parse(xmind_path)
        summary = analyzer.analyze(root, source_file=xmind_path)

        hints = analyzer.generate_routing_hints(
            summary,
            ["支付流程功能验证", "并发性能测试", "权限控制检查"],
        )

        assert isinstance(hints, str)
        assert "支付流程功能验证" in hints
        assert "并发性能测试" in hints

    def test_graceful_degradation_with_missing_file(self, tmp_path) -> None:
        """Loader returns empty dict for nonexistent file."""
        parser = XMindParser()
        analyzer = XMindReferenceAnalyzer()
        node = build_xmind_reference_loader_node(parser, analyzer)

        result = node({"reference_xmind_path": str(tmp_path / "nonexistent.xmind")})
        assert result == {}

    def test_skip_when_no_reference(self) -> None:
        """Loader skips cleanly when no reference path."""
        parser = XMindParser()
        analyzer = XMindReferenceAnalyzer()
        node = build_xmind_reference_loader_node(parser, analyzer)

        assert node({}) == {}
        assert node({"reference_xmind_path": None}) == {}
        assert node({"reference_xmind_path": ""}) == {}
