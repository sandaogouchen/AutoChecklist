from __future__ import annotations

from pathlib import Path

from app.parsers.base import BaseDocumentParser
from app.parsers.markdown import MarkdownParser

SUPPORTED_MARKDOWN_SUFFIXES = {".md", ".markdown", ".prd"}


def get_parser(path: Path) -> BaseDocumentParser:
    if path.suffix.lower() in SUPPORTED_MARKDOWN_SUFFIXES:
        return MarkdownParser()

    raise ValueError(f"Unsupported document type: {path.suffix}")
