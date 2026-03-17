"""解析器工厂模块。

根据文件后缀名选择合适的文档解析器实例。
当前支持 Markdown 系列后缀（.md / .markdown / .prd），
后续可在此扩展 PDF、Word 等格式的支持。
"""

from __future__ import annotations

from pathlib import Path

from app.parsers.base import BaseDocumentParser
from app.parsers.markdown import MarkdownParser

# 支持的 Markdown 文件后缀集合
SUPPORTED_MARKDOWN_SUFFIXES = {".md", ".markdown", ".prd"}


def get_parser(path: Path) -> BaseDocumentParser:
    """根据文件后缀返回对应的解析器实例。

    Args:
        path: 待解析文件的路径。

    Returns:
        匹配的解析器实例。

    Raises:
        ValueError: 文件后缀不在支持列表中。
    """
    if path.suffix.lower() in SUPPORTED_MARKDOWN_SUFFIXES:
        return MarkdownParser()

    raise ValueError(f"Unsupported document type: {path.suffix}")
