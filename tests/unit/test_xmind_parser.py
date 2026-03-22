"""Unit tests for XMindParser.

Covers:
- Normal parse of valid .xmind (content.json format)
- FileNotFoundError when file does not exist
- XMindParseError on corrupted ZIP
- XMindParseError when content.json is missing
- UnsupportedXMindFormatError when only content.xml present (old format)
- Nested children parsing
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile

import pytest

from app.domain.xmind_reference_models import XMindReferenceNode
from app.parsers.xmind_parser import (
    UnsupportedXMindFormatError,
    XMindParseError,
    XMindParser,
)


@pytest.fixture
def parser() -> XMindParser:
    return XMindParser()


def _create_xmind_file(path: str, content_json: list | dict | None = None, *, include_xml: bool = False, no_content: bool = False) -> None:
    """Helper to create a .xmind ZIP file with optional content.json."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        if content_json is not None:
            zf.writestr("content.json", json.dumps(content_json))
        if include_xml:
            zf.writestr("content.xml", "<xmap-content/>")
        if no_content:
            zf.writestr("metadata.json", '{"creator": "test"}')


def _sample_content_json() -> list:
    """Return a minimal valid XMind 8+ content.json."""
    return [
        {
            "rootTopic": {
                "title": "Root",
                "children": {
                    "attached": [
                        {
                            "title": "Branch A",
                            "children": {
                                "attached": [
                                    {"title": "Leaf A1"},
                                    {"title": "Leaf A2"},
                                ]
                            },
                        },
                        {
                            "title": "Branch B",
                            "children": {
                                "attached": [
                                    {"title": "Leaf B1"},
                                ]
                            },
                        },
                    ]
                },
            }
        }
    ]


class TestXMindParserNormal:
    """Tests for successful parsing."""

    def test_parse_valid_xmind(self, parser: XMindParser, tmp_path) -> None:
        xmind_path = str(tmp_path / "test.xmind")
        _create_xmind_file(xmind_path, _sample_content_json())

        root = parser.parse(xmind_path)

        assert isinstance(root, XMindReferenceNode)
        assert root.title == "Root"
        assert len(root.children) == 2
        assert root.children[0].title == "Branch A"
        assert len(root.children[0].children) == 2
        assert root.children[1].title == "Branch B"
        assert len(root.children[1].children) == 1

    def test_parse_deeply_nested(self, parser: XMindParser, tmp_path) -> None:
        content = [
            {
                "rootTopic": {
                    "title": "R",
                    "children": {
                        "attached": [
                            {
                                "title": "L1",
                                "children": {
                                    "attached": [
                                        {
                                            "title": "L2",
                                            "children": {
                                                "attached": [
                                                    {"title": "L3"}
                                                ]
                                            },
                                        }
                                    ]
                                },
                            }
                        ]
                    },
                }
            }
        ]
        xmind_path = str(tmp_path / "deep.xmind")
        _create_xmind_file(xmind_path, content)

        root = parser.parse(xmind_path)
        assert root.children[0].children[0].children[0].title == "L3"

    def test_parse_children_as_list(self, parser: XMindParser, tmp_path) -> None:
        """Some XMind variants store children as a direct list."""
        content = [
            {
                "rootTopic": {
                    "title": "Root",
                    "children": [
                        {"title": "Direct Child"}
                    ],
                }
            }
        ]
        xmind_path = str(tmp_path / "list_children.xmind")
        _create_xmind_file(xmind_path, content)

        root = parser.parse(xmind_path)
        assert len(root.children) == 1
        assert root.children[0].title == "Direct Child"


class TestXMindParserErrors:
    """Tests for error conditions."""

    def test_file_not_found(self, parser: XMindParser) -> None:
        with pytest.raises(FileNotFoundError, match="XMind file not found"):
            parser.parse("/nonexistent/path/test.xmind")

    def test_corrupted_zip(self, parser: XMindParser, tmp_path) -> None:
        bad_path = str(tmp_path / "bad.xmind")
        with open(bad_path, "wb") as f:
            f.write(b"this is not a zip file")

        with pytest.raises(XMindParseError, match="损坏"):
            parser.parse(bad_path)

    def test_missing_content_json(self, parser: XMindParser, tmp_path) -> None:
        xmind_path = str(tmp_path / "no_content.xmind")
        _create_xmind_file(xmind_path, no_content=True)

        with pytest.raises(XMindParseError, match="content.json"):
            parser.parse(xmind_path)

    def test_old_format_content_xml(self, parser: XMindParser, tmp_path) -> None:
        xmind_path = str(tmp_path / "old.xmind")
        _create_xmind_file(xmind_path, include_xml=True)

        with pytest.raises(UnsupportedXMindFormatError, match="旧格式"):
            parser.parse(xmind_path)

    def test_empty_sheets_array(self, parser: XMindParser, tmp_path) -> None:
        xmind_path = str(tmp_path / "empty.xmind")
        _create_xmind_file(xmind_path, [])

        with pytest.raises(XMindParseError, match="格式异常"):
            parser.parse(xmind_path)

    def test_missing_root_topic(self, parser: XMindParser, tmp_path) -> None:
        xmind_path = str(tmp_path / "no_root.xmind")
        _create_xmind_file(xmind_path, [{"title": "Sheet1"}])

        with pytest.raises(XMindParseError, match="rootTopic"):
            parser.parse(xmind_path)
