"""文档解析领域模型。

定义了 PRD 文档解析后的结构化表示，包括：
- ``DocumentSource``：文档来源元信息
- ``DocumentSection``：文档章节
- ``ParsedDocument``：完整的解析结果
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentSource(BaseModel):
    """文档来源信息。

    记录原始文件路径、类型、标题以及内容校验和（SHA-256），
    用于追溯和缓存判断。
    """

    source_path: str
    source_type: str
    title: str = ""
    checksum: str = ""


class DocumentSection(BaseModel):
    """文档中的一个章节。

    Attributes:
        heading: 章节标题文本。
        level: 标题层级（1 = ``#``，2 = ``##``，依次类推）。
        content: 章节正文内容（不含标题行本身）。
        line_start: 章节在原文中的起始行号（从 1 开始）。
        line_end: 章节在原文中的结束行号（含）。
    """

    heading: str
    level: int
    content: str = ""
    line_start: int
    line_end: int


class ParsedDocument(BaseModel):
    """完整的文档解析结果。

    除了按章节拆分后的结构化数据外，也保留原始全文（``raw_text``），
    供 LLM prompt 直接引用。
    """

    raw_text: str
    sections: list[DocumentSection] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: DocumentSource | None = None
