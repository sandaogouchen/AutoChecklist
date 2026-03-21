"""知识文档加载单元测试。

测试 app.knowledge.ingestion 模块的目录扫描和文件校验功能。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.knowledge.ingestion import scan_knowledge_directory, validate_document_path


@pytest.fixture
def knowledge_docs_dir(tmp_path: Path) -> Path:
    """创建临时知识文档目录，包含多种测试文件。"""
    docs_dir = tmp_path / "knowledge_docs"
    docs_dir.mkdir()

    # 正常 MD 文件
    (docs_dir / "guide.md").write_text("# 用户指南\n\n这是一份用户指南。", encoding="utf-8")
    (docs_dir / "api.md").write_text("# API 文档\n\n## 接口说明\n\n详情见下文。", encoding="utf-8")

    # 嵌套子目录中的 MD 文件
    sub_dir = docs_dir / "advanced"
    sub_dir.mkdir()
    (sub_dir / "deep.md").write_text("# 高级用法\n\n高级内容。", encoding="utf-8")

    # 空文件（应被跳过）
    (docs_dir / "empty.md").write_text("", encoding="utf-8")

    # 非 MD 文件（应被忽略）
    (docs_dir / "notes.txt").write_text("这不是 Markdown 文件", encoding="utf-8")

    return docs_dir


class TestScanKnowledgeDirectory:
    """scan_knowledge_directory 函数测试。"""

    def test_scans_valid_md_files(self, knowledge_docs_dir: Path) -> None:
        """应递归扫描所有有效的 .md 文件。"""
        results = scan_knowledge_directory(str(knowledge_docs_dir))

        # 应找到 3 个有效文件：guide.md, api.md, advanced/deep.md
        assert len(results) == 3
        file_names = {doc.file_name for doc, _ in results}
        assert "guide.md" in file_names
        assert "api.md" in file_names
        assert "deep.md" in file_names

    def test_returns_content_with_metadata(self, knowledge_docs_dir: Path) -> None:
        """每个结果应包含元数据和文档内容。"""
        results = scan_knowledge_directory(str(knowledge_docs_dir))
        for doc, content in results:
            assert doc.doc_id.startswith("doc_")
            assert doc.file_name.endswith(".md")
            assert doc.file_size_bytes > 0
            assert doc.md5_hash != ""
            assert len(content) > 0

    def test_skips_empty_files(self, knowledge_docs_dir: Path) -> None:
        """应跳过空文件。"""
        results = scan_knowledge_directory(str(knowledge_docs_dir))
        file_names = {doc.file_name for doc, _ in results}
        assert "empty.md" not in file_names

    def test_skips_oversized_files(self, knowledge_docs_dir: Path) -> None:
        """应跳过超过大小限制的文件。"""
        # 创建一个超过 1 KB 的文件
        big_file = knowledge_docs_dir / "big.md"
        big_file.write_text("x" * 2048, encoding="utf-8")

        results = scan_knowledge_directory(str(knowledge_docs_dir), max_doc_size_kb=1)
        file_names = {doc.file_name for doc, _ in results}
        assert "big.md" not in file_names

    def test_nonexistent_directory_returns_empty(self) -> None:
        """不存在的目录应返回空列表。"""
        results = scan_knowledge_directory("/nonexistent/path")
        assert results == []

    def test_non_directory_path_returns_empty(self, tmp_path: Path) -> None:
        """传入文件路径而非目录应返回空列表。"""
        file_path = tmp_path / "not_a_dir.md"
        file_path.write_text("content", encoding="utf-8")

        results = scan_knowledge_directory(str(file_path))
        assert results == []

    def test_ignores_non_md_files(self, knowledge_docs_dir: Path) -> None:
        """应忽略非 .md 后缀的文件。"""
        results = scan_knowledge_directory(str(knowledge_docs_dir))
        file_names = {doc.file_name for doc, _ in results}
        assert "notes.txt" not in file_names


class TestValidateDocumentPath:
    """validate_document_path 函数测试。"""

    def test_valid_file_returns_content(self, knowledge_docs_dir: Path) -> None:
        """有效文件应返回其内容。"""
        file_path = str(knowledge_docs_dir / "guide.md")
        content = validate_document_path(file_path)
        assert "用户指南" in content

    def test_nonexistent_file_raises(self) -> None:
        """不存在的文件应抛出 ValueError。"""
        with pytest.raises(ValueError, match="文件不存在"):
            validate_document_path("/nonexistent/file.md")

    def test_non_md_file_raises(self, tmp_path: Path) -> None:
        """非 .md 文件应抛出 ValueError。"""
        txt_file = tmp_path / "doc.txt"
        txt_file.write_text("content", encoding="utf-8")
        with pytest.raises(ValueError, match="仅支持 .md 格式"):
            validate_document_path(str(txt_file))

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        """空文件应抛出 ValueError。"""
        empty = tmp_path / "empty.md"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="文件为空"):
            validate_document_path(str(empty))

    def test_oversized_file_raises(self, tmp_path: Path) -> None:
        """超过大小限制的文件应抛出 ValueError。"""
        big = tmp_path / "big.md"
        big.write_text("x" * 2048, encoding="utf-8")
        with pytest.raises(ValueError, match="文件过大"):
            validate_document_path(str(big), max_doc_size_kb=1)