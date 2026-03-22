"""Unit tests for XMind reference loader node.

Covers:
- Normal load: parser + analyzer produce summary
- Skip when no reference_xmind_path in state
- Graceful degradation on parse error
- Integration with tree_converter
"""

from __future__ import annotations

import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from app.domain.xmind_reference_models import XMindReferenceNode, XMindReferenceSummary
from app.nodes.xmind_reference_loader import build_xmind_reference_loader_node
from app.parsers.xmind_parser import XMindParseError, XMindParser
from app.services.xmind_reference_analyzer import XMindReferenceAnalyzer


@pytest.fixture
def parser() -> XMindParser:
    return XMindParser()


@pytest.fixture
def analyzer() -> XMindReferenceAnalyzer:
    return XMindReferenceAnalyzer()


def _make_mock_summary() -> XMindReferenceSummary:
    return XMindReferenceSummary(
        source_file="test.xmind",
        total_nodes=5,
        total_leaf_nodes=3,
        max_depth=2,
        skeleton="Root\n├── A\n└── B",
        sampled_paths=["Root > A > Leaf1"],
        depth_distribution={0: 1, 1: 2, 2: 2},
        top_prefixes=["Root > A"],
        formatted_summary="[参考 Checklist 结构]\n...",
    )


def _create_test_xmind(tmp_path):
    """Create a minimal .xmind file for testing."""
    content = [
        {
            "rootTopic": {
                "title": "测试 Checklist",
                "children": {
                    "attached": [
                        {
                            "title": "功能模块A",
                            "children": {
                                "attached": [
                                    {"title": "测试项1"},
                                    {"title": "测试项2"},
                                ]
                            },
                        },
                        {
                            "title": "功能模块B",
                            "children": {
                                "attached": [
                                    {"title": "测试项3"},
                                ]
                            },
                        },
                    ]
                },
            }
        }
    ]
    xmind_file = tmp_path / "test.xmind"
    with zipfile.ZipFile(str(xmind_file), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False))
    return xmind_file


class TestNormalLoad:
    """Test successful XMind reference loading."""

    def test_load_produces_summary(self) -> None:
        mock_parser = MagicMock(spec=XMindParser)
        mock_analyzer = MagicMock(spec=XMindReferenceAnalyzer)

        mock_root = XMindReferenceNode(title="Root")
        mock_summary = _make_mock_summary()

        mock_parser.parse.return_value = mock_root
        mock_analyzer.analyze.return_value = mock_summary

        node = build_xmind_reference_loader_node(mock_parser, mock_analyzer)
        result = node({"reference_xmind_path": "/path/to/test.xmind"})

        assert "xmind_reference_summary" in result
        assert result["xmind_reference_summary"] is mock_summary
        mock_parser.parse.assert_called_once_with("/path/to/test.xmind")
        mock_analyzer.analyze.assert_called_once_with(
            mock_root, source_file="/path/to/test.xmind"
        )


class TestSkipWhenNoReference:
    """Test that the node returns empty dict when no reference path."""

    def test_empty_path(self, parser: XMindParser, analyzer: XMindReferenceAnalyzer) -> None:
        node = build_xmind_reference_loader_node(parser, analyzer)
        result = node({"reference_xmind_path": ""})
        assert result == {}

    def test_none_path(self, parser: XMindParser, analyzer: XMindReferenceAnalyzer) -> None:
        node = build_xmind_reference_loader_node(parser, analyzer)
        result = node({"reference_xmind_path": None})
        assert result == {}

    def test_missing_key(self, parser: XMindParser, analyzer: XMindReferenceAnalyzer) -> None:
        node = build_xmind_reference_loader_node(parser, analyzer)
        result = node({})
        assert result == {}


class TestGracefulDegradation:
    """Test graceful degradation on parse errors."""

    def test_file_not_found(self, analyzer: XMindReferenceAnalyzer) -> None:
        mock_parser = MagicMock(spec=XMindParser)
        mock_parser.parse.side_effect = FileNotFoundError("not found")

        node = build_xmind_reference_loader_node(mock_parser, analyzer)
        result = node({"reference_xmind_path": "/missing/file.xmind"})

        assert result == {}

    def test_parse_error(self, analyzer: XMindReferenceAnalyzer) -> None:
        mock_parser = MagicMock(spec=XMindParser)
        mock_parser.parse.side_effect = XMindParseError("bad file")

        node = build_xmind_reference_loader_node(mock_parser, analyzer)
        result = node({"reference_xmind_path": "/bad/file.xmind"})

        assert result == {}

    def test_unexpected_error(self, analyzer: XMindReferenceAnalyzer) -> None:
        mock_parser = MagicMock(spec=XMindParser)
        mock_parser.parse.side_effect = RuntimeError("unexpected")

        node = build_xmind_reference_loader_node(mock_parser, analyzer)
        result = node({"reference_xmind_path": "/some/file.xmind"})

        assert result == {}


class TestWithTreeConverter:
    """验证 loader 集成 tree_converter 后的行为。"""

    def test_load_produces_reference_tree(self, tmp_path) -> None:
        from app.services.xmind_reference_tree_converter import XMindReferenceTreeConverter

        xmind_file = _create_test_xmind(tmp_path)
        parser = XMindParser()
        analyzer = XMindReferenceAnalyzer()
        converter = XMindReferenceTreeConverter()

        node = build_xmind_reference_loader_node(parser, analyzer, converter)
        result = node({"reference_xmind_path": str(xmind_file)})

        summary = result["xmind_reference_summary"]
        assert hasattr(summary, "reference_tree")
        assert len(summary.reference_tree) > 0
        assert all(n.source == "reference" for n in summary.reference_tree)

    def test_load_produces_leaf_titles(self, tmp_path) -> None:
        from app.services.xmind_reference_tree_converter import XMindReferenceTreeConverter

        xmind_file = _create_test_xmind(tmp_path)
        parser = XMindParser()
        analyzer = XMindReferenceAnalyzer()
        converter = XMindReferenceTreeConverter()

        node = build_xmind_reference_loader_node(parser, analyzer, converter)
        result = node({"reference_xmind_path": str(xmind_file)})

        summary = result["xmind_reference_summary"]
        assert hasattr(summary, "all_leaf_titles")
        assert len(summary.all_leaf_titles) > 0

    def test_backward_compatible_without_converter(self, tmp_path) -> None:
        xmind_file = _create_test_xmind(tmp_path)
        parser = XMindParser()
        analyzer = XMindReferenceAnalyzer()

        # No converter passed - should still work
        node = build_xmind_reference_loader_node(parser, analyzer)
        result = node({"reference_xmind_path": str(xmind_file)})

        summary = result["xmind_reference_summary"]
        assert summary.formatted_summary  # Original behavior preserved
