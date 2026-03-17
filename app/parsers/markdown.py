"""Markdown 文档解析器。

将 Markdown 格式的 PRD 文档解析为结构化的 ``ParsedDocument``，
按标题（# 系列）拆分章节，提取引用链接，并计算内容校验和。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.domain.document_models import DocumentSection, DocumentSource, ParsedDocument


class MarkdownParser:
    """Markdown 文档解析器。

    解析策略：逐行扫描，遇到 ``#`` 开头的行即视为新章节的开始，
    将前一个章节的累积内容封装为 ``DocumentSection``。
    """

    def parse(self, path: Path) -> ParsedDocument:
        """解析指定路径的 Markdown 文件。

        Args:
            path: Markdown 文件的路径。

        Returns:
            包含章节列表、引用链接和元数据的解析结果。
        """
        raw_text = path.read_text(encoding="utf-8")
        lines = raw_text.splitlines()

        sections = self._extract_sections(lines, default_heading=path.stem)
        references = self._extract_references(lines)
        checksum = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        return ParsedDocument(
            raw_text=raw_text,
            sections=sections,
            references=references,
            metadata={"section_count": len(sections)},
            source=DocumentSource(
                source_path=str(path),
                source_type="markdown",
                title=sections[0].heading if sections else path.stem,
                checksum=checksum,
            ),
        )

    def _extract_sections(
        self, lines: list[str], default_heading: str
    ) -> list[DocumentSection]:
        """按标题行拆分文档为章节列表。

        算法：
        1. 维护一个“当前章节”的累积缓冲区（current_lines）
        2. 遇到新标题时，将缓冲区内容封装为 DocumentSection 并重置
        3. 文件末尾将最后一个章节推入结果列表

        Args:
            lines: 文档按行拆分后的列表。
            default_heading: 当文件无标题时使用的默认标题（通常为文件名）。

        Returns:
            按出现顺序排列的章节列表。
        """
        sections: list[DocumentSection] = []
        current_heading = default_heading
        current_level = 1
        current_start = 1
        current_lines: list[str] = []

        for index, line in enumerate(lines, start=1):
            if line.startswith("#"):
                # 遇到新标题：将之前累积的内容保存为一个章节
                if current_lines or sections:
                    sections.append(
                        DocumentSection(
                            heading=current_heading,
                            level=current_level,
                            content="\n".join(current_lines).strip(),
                            line_start=current_start,
                            line_end=index - 1,
                        )
                    )
                # 解析新标题的层级和文本
                level = len(line) - len(line.lstrip("#"))
                current_heading = line[level:].strip() or default_heading
                current_level = level
                current_start = index
                current_lines = []
                continue

            current_lines.append(line)

        # 处理最后一个章节（文件末尾没有新标题来触发保存）
        if lines:
            sections.append(
                DocumentSection(
                    heading=current_heading,
                    level=current_level,
                    content="\n".join(current_lines).strip(),
                    line_start=current_start,
                    line_end=len(lines),
                )
            )

        return sections

    @staticmethod
    def _extract_references(lines: list[str]) -> list[str]:
        """提取文档中所有包含 Markdown 链接语法的行。

        使用 ``](`` 作为简单的启发式匹配标记。
        """
        return [line.strip() for line in lines if "](" in line]
