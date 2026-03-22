"""Unit tests for XMind reference loader node.

Covers:
- Normal load: parser + analyzer produce summary
- Skip when no reference_xmind_path in state
- Graceful degradation on parse error
"""

from __future__ import annotations

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
