"""文档解析器基类模块。

定义了文档解析器的协议接口（Protocol），所有具体解析器（如 MarkdownParser）
均需实现此接口，以便通过工厂函数统一调度。
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.document_models import ParsedDocument


class BaseDocumentParser(Protocol):
    """文档解析器协议。

    任何实现了 ``parse`` 方法的类均满足此协议，
    无需显式继承——这是 Python 结构化子类型（鸭子类型）的惯用方式。
    """

    def parse(self, path: Path) -> ParsedDocument:
        """将源文档解析为结构化的 ``ParsedDocument``。

        Args:
            path: 文档文件的绝对路径。

        Returns:
            包含章节、元数据和原文的解析结果。
        """
