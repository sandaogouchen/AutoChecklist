"""GraphRAG 引擎封装单元测试。

测试 app.knowledge.graphrag_engine 模块的 GraphRAGEngine 类。
使用 mock 替代真实的 LightRAG 和 HTTP 调用。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.knowledge.models import KnowledgeDocument, KnowledgeStatus, RetrievalResult


@pytest.fixture
def mock_settings(tmp_path: Path):
    """创建带临时目录的 mock settings。"""
    settings = MagicMock()
    settings.enable_knowledge_retrieval = True
    settings.knowledge_working_dir = str(tmp_path / "knowledge_db")
    settings.knowledge_docs_dir = str(tmp_path / "knowledge_docs")
    settings.knowledge_retrieval_mode = "hybrid"
    settings.knowledge_top_k = 10
    settings.knowledge_embedding_model = ""
    settings.knowledge_max_doc_size_kb = 1024
    settings.llm_base_url = "http://localhost:8080/v1"
    settings.llm_api_key = "test-key"
    settings.llm_model = "test-model"
    settings.llm_timeout_seconds = 30
    settings.llm_temperature = 0.2
    settings.llm_max_tokens = 1600
    return settings


class TestGraphRAGEngineInit:
    """GraphRAGEngine 初始化测试。"""

    def test_not_ready_before_initialize(self, mock_settings) -> None:
        """初始化前引擎应不处于就绪状态。"""
        from app.knowledge.graphrag_engine import GraphRAGEngine

        engine = GraphRAGEngine(mock_settings)
        assert engine.is_ready() is False

    def test_not_ready_when_disabled(self, mock_settings) -> None:
        """知识检索未启用时，initialize 后仍不就绪。"""
        from app.knowledge.graphrag_engine import GraphRAGEngine

        mock_settings.enable_knowledge_retrieval = False
        engine = GraphRAGEngine(mock_settings)

        import asyncio
        asyncio.get_event_loop().run_until_complete(engine.initialize())

        assert engine.is_ready() is False


class TestGraphRAGEngineStatus:
    """GraphRAGEngine 状态查询测试。"""

    def test_get_status_when_not_ready(self, mock_settings) -> None:
        """未就绪时应返回 ready=False 的状态。"""
        from app.knowledge.graphrag_engine import GraphRAGEngine

        engine = GraphRAGEngine(mock_settings)
        status = engine.get_status()

        assert isinstance(status, KnowledgeStatus)
        assert status.enabled is True
        assert status.ready is False
        assert status.document_count == 0

    def test_list_documents_empty(self, mock_settings) -> None:
        """无文档时应返回空列表。"""
        from app.knowledge.graphrag_engine import GraphRAGEngine

        engine = GraphRAGEngine(mock_settings)
        docs = engine.list_documents()
        assert docs == []


class TestDocumentRegistry:
    """文档注册表持久化测试。"""

    def test_save_and_load_registry(self, mock_settings, tmp_path: Path) -> None:
        """注册表应能正确保存和加载。"""
        from app.knowledge.graphrag_engine import GraphRAGEngine, _DOC_REGISTRY_FILE

        # 准备工作目录
        working_dir = Path(mock_settings.knowledge_working_dir)
        working_dir.mkdir(parents=True, exist_ok=True)

        engine = GraphRAGEngine(mock_settings)

        # 手动添加一个文档到注册表
        doc = KnowledgeDocument(
            doc_id="doc_test123",
            file_name="test.md",
            file_path="/tmp/test.md",
            file_size_bytes=100,
            md5_hash="abc123def456",
            indexed_at=datetime.now(timezone.utc),
        )
        engine._documents["doc_test123"] = doc
        engine._save_document_registry()

        # 验证文件已写入
        registry_path = working_dir / _DOC_REGISTRY_FILE
        assert registry_path.exists()

        # 创建新实例并加载
        engine2 = GraphRAGEngine(mock_settings)
        engine2._load_document_registry()

        assert "doc_test123" in engine2._documents
        assert engine2._documents["doc_test123"].file_name == "test.md"

    def test_load_empty_registry(self, mock_settings) -> None:
        """工作目录不存在注册表文件时应正常处理。"""
        from app.knowledge.graphrag_engine import GraphRAGEngine

        engine = GraphRAGEngine(mock_settings)
        # 不创建工作目录，直接加载
        engine._load_document_registry()
        assert len(engine._documents) == 0


class TestGraphRAGEngineQuery:
    """GraphRAGEngine 检索测试（使用 mock）。"""

    def test_query_returns_failure_when_not_ready(self, mock_settings) -> None:
        """引擎未就绪时 query 应返回失败结果。"""
        from app.knowledge.graphrag_engine import GraphRAGEngine

        engine = GraphRAGEngine(mock_settings)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            engine.query("测试查询")
        )

        assert isinstance(result, RetrievalResult)
        assert result.success is False
        assert "未就绪" in result.error_message
