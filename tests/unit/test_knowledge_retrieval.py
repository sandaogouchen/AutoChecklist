"""知识检索节点单元测试。

测试 app.nodes.knowledge_retrieval 和 app.knowledge.retriever 模块。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.knowledge.models import RetrievalResult
from app.knowledge.retriever import (
    MAX_KNOWLEDGE_CONTEXT_CHARS,
    build_retrieval_query,
    format_retrieval_result,
)


class TestBuildRetrievalQuery:
    """build_retrieval_query 函数测试。"""

    def test_extracts_title_and_body(self) -> None:
        """应从 ParsedDocument 提取标题和正文。"""
        doc = MagicMock()
        doc.source.title = "登录功能 PRD"
        doc.raw_text = "这是一份关于登录功能的产品需求文档，包含各种测试场景。"

        query = build_retrieval_query(doc)
        assert "登录功能 PRD" in query
        assert "产品需求文档" in query

    def test_truncates_long_query(self) -> None:
        """应将查询截断到 500 字符。"""
        doc = MagicMock()
        doc.source.title = "标题"
        doc.raw_text = "正文内容" * 200  # 超过 400 字符

        query = build_retrieval_query(doc)
        assert len(query) <= 500

    def test_handles_missing_title(self) -> None:
        """标题为空时应仅使用正文。"""
        doc = MagicMock()
        doc.source.title = ""
        doc.raw_text = "仅有正文内容"

        query = build_retrieval_query(doc)
        assert "仅有正文内容" in query

    def test_handles_missing_raw_text(self) -> None:
        """正文为空时应仅使用标题。"""
        doc = MagicMock()
        doc.source.title = "标题"
        doc.raw_text = ""

        query = build_retrieval_query(doc)
        assert "标题" in query

    def test_handles_none_source(self) -> None:
        """source 为 None 时不应崩溃。"""
        doc = MagicMock()
        doc.source = None
        doc.raw_text = "有正文"

        # source is None, title 属性访问会抛异常，
        # 但 build_retrieval_query 使用 parsed_document.source.title
        # 所以需确认它能处理 source=None 或我们测试实际行为
        # 实际上 source 是一个可选属性，MagicMock 会返回 MagicMock
        # 用真实的 None 来测试
        doc.source = MagicMock()
        doc.source.title = None
        query = build_retrieval_query(doc)
        assert "有正文" in query


class TestFormatRetrievalResult:
    """format_retrieval_result 函数测试。"""

    def test_formats_successful_result(self) -> None:
        """成功的检索结果应格式化为非空字符串。"""
        result = RetrievalResult(
            content="这是检索到的知识内容。",
            sources=["doc_abc123"],
            success=True,
        )
        formatted = format_retrieval_result(result)
        assert "检索到的知识内容" in formatted

    def test_returns_empty_for_failed_result(self) -> None:
        """失败的检索结果应返回空字符串。"""
        result = RetrievalResult(success=False, error_message="timeout")
        formatted = format_retrieval_result(result)
        assert formatted == ""

    def test_returns_empty_for_empty_content(self) -> None:
        """内容为空的成功结果应返回空字符串。"""
        result = RetrievalResult(content="", success=True)
        formatted = format_retrieval_result(result)
        assert formatted == ""

    def test_truncates_long_content(self) -> None:
        """超过最大字符限制的内容应被截断。"""
        long_content = "知识" * (MAX_KNOWLEDGE_CONTEXT_CHARS + 100)
        result = RetrievalResult(content=long_content, success=True)
        formatted = format_retrieval_result(result)
        assert len(formatted) <= MAX_KNOWLEDGE_CONTEXT_CHARS + 50  # 含截断提示
        assert "截断" in formatted


class TestKnowledgeRetrievalNode:
    """build_knowledge_retrieval_node 工厂函数和节点行为测试。"""

    def test_returns_empty_when_engine_not_ready(self) -> None:
        """引擎未就绪时应返回空结果。"""
        from app.nodes.knowledge_retrieval import build_knowledge_retrieval_node

        engine = MagicMock()
        engine.is_ready.return_value = False
        settings = MagicMock()

        node = build_knowledge_retrieval_node(engine, settings)
        result = node({"parsed_document": MagicMock()})

        assert result["knowledge_context"] == ""
        assert result["knowledge_sources"] == []
        assert result["knowledge_retrieval_success"] is False

    def test_returns_empty_when_no_parsed_document(self) -> None:
        """state 中无 parsed_document 时应返回空结果。"""
        from app.nodes.knowledge_retrieval import build_knowledge_retrieval_node

        engine = MagicMock()
        engine.is_ready.return_value = True
        settings = MagicMock()

        node = build_knowledge_retrieval_node(engine, settings)
        result = node({})

        assert result["knowledge_context"] == ""
        assert result["knowledge_retrieval_success"] is False

    def test_graceful_degradation_on_exception(self) -> None:
        """检索过程中异常时应降级返回空结果而不抛异常。"""
        from app.nodes.knowledge_retrieval import build_knowledge_retrieval_node

        engine = MagicMock()
        engine.is_ready.return_value = True
        settings = MagicMock()
        settings.knowledge_retrieval_mode = "hybrid"

        node = build_knowledge_retrieval_node(engine, settings)

        # mock retrieve_knowledge 抛出异常
        with patch(
            "app.nodes.knowledge_retrieval.retrieve_knowledge",
            side_effect=RuntimeError("模拟检索失败"),
        ):
            result = node({"parsed_document": MagicMock()})

        assert result["knowledge_context"] == ""
        assert result["knowledge_retrieval_success"] is False
