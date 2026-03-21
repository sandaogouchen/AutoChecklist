"""LightRAG GraphRAG 引擎封装。

管理 LightRAG 实例的完整生命周期，包括初始化、文档索引、
知识检索和资源释放。通过适配器将 LightRAG 的 LLM/Embedding
回调桥接到项目现有的 OpenAI-compatible 端点。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc

from app.config.settings import Settings
from app.knowledge.models import KnowledgeDocument, KnowledgeStatus, RetrievalResult

logger = logging.getLogger(__name__)

# 已索引文档的元数据文件名
_DOC_REGISTRY_FILE = "indexed_documents.json"


async def _openai_compatible_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[list] = None,
    keyword_extraction: bool = False,
    **kwargs,
) -> str:
    """LightRAG LLM 回调适配器。

    使用 httpx 直接调用 OpenAI-compatible chat/completions 端点，
    复用项目 Settings 中的 LLM 配置。
    """
    import httpx

    settings = Settings()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.0 if keyword_extraction else settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }

    async with httpx.AsyncClient(
        timeout=settings.llm_timeout_seconds
    ) as client:
        response = await client.post(
            f"{settings.llm_base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def _openai_compatible_embedding(texts: list[str]) -> np.ndarray:
    """LightRAG Embedding 回调适配器。

    使用 httpx 调用 OpenAI-compatible /v1/embeddings 端点。
    """
    import httpx

    settings = Settings()
    model = settings.knowledge_embedding_model or settings.llm_model

    async with httpx.AsyncClient(
        timeout=settings.llm_timeout_seconds
    ) as client:
        response = await client.post(
            f"{settings.llm_base_url}/embeddings",
            json={"model": model, "input": texts},
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]
        return np.array(embeddings)


class GraphRAGEngine:
    """LightRAG GraphRAG 引擎封装。

    管理 LightRAG 实例的初始化、文档索引、检索和生命周期。
    所有对外方法均为 async，与 FastAPI 的异步运行时一致。
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rag: Optional[LightRAG] = None
        self._documents: dict[str, KnowledgeDocument] = {}
        self._ready = False

    async def initialize(self) -> None:
        """初始化 LightRAG 实例并加载已有索引。

        如果工作目录中已有索引数据，LightRAG 会自动加载。
        """
        if not self._settings.enable_knowledge_retrieval:
            logger.info("知识检索未启用，跳过引擎初始化")
            return

        working_dir = self._settings.knowledge_working_dir
        Path(working_dir).mkdir(parents=True, exist_ok=True)

        try:
            embedding_dim = 1536  # OpenAI 默认维度，可后续配置化

            self._rag = LightRAG(
                working_dir=working_dir,
                llm_model_func=_openai_compatible_llm,
                embedding_func=EmbeddingFunc(
                    embedding_dim=embedding_dim,
                    max_token_size=8192,
                    func=_openai_compatible_embedding,
                ),
            )
            await self._rag.initialize_storages()
            self._load_document_registry()
            self._ready = True
            logger.info(
                "GraphRAG 引擎初始化完成 (working_dir=%s, 已索引 %d 文档)",
                working_dir,
                len(self._documents),
            )
        except Exception:
            logger.exception("GraphRAG 引擎初始化失败")
            self._ready = False

    async def finalize(self) -> None:
        """释放 LightRAG 资源。"""
        if self._rag is not None:
            try:
                await self._rag.finalize_storages()
            except Exception:
                logger.exception("GraphRAG 引擎资源释放失败")
            self._rag = None
        self._ready = False

    def is_ready(self) -> bool:
        """检查引擎是否就绪。"""
        return self._ready and self._rag is not None

    async def insert_document(self, content: str, metadata: dict) -> KnowledgeDocument:
        """索引单个知识文档。

        Args:
            content: 文档文本内容。
            metadata: 文档元数据（file_name, file_path 等）。

        Returns:
            索引完成后的 KnowledgeDocument 元数据。

        Raises:
            RuntimeError: 引擎未就绪。
        """
        if not self.is_ready():
            raise RuntimeError("GraphRAG 引擎未就绪")

        md5_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        doc_id = metadata.get("doc_id", f"doc_{md5_hash[:12]}")

        # 检查是否已索引（基于内容哈希）
        if doc_id in self._documents:
            existing = self._documents[doc_id]
            if existing.md5_hash == md5_hash:
                logger.info("文档已索引且内容未变化，跳过: %s", doc_id)
                return existing

        await self._rag.ainsert(
            content,
            ids=[doc_id],
            file_paths=[metadata.get("file_path", "")],
        )

        doc = KnowledgeDocument(
            doc_id=doc_id,
            file_name=metadata.get("file_name", ""),
            file_path=metadata.get("file_path", ""),
            file_size_bytes=len(content.encode("utf-8")),
            md5_hash=md5_hash,
            indexed_at=datetime.now(timezone.utc),
        )
        self._documents[doc_id] = doc
        self._save_document_registry()
        logger.info("文档索引完成: %s (%s)", doc.file_name, doc_id)
        return doc

    async def insert_batch(
        self, docs: list[tuple[KnowledgeDocument, str]]
    ) -> list[KnowledgeDocument]:
        """批量索引知识文档。

        跳过已索引且内容未变化的文档。

        Args:
            docs: (KnowledgeDocument 元数据, 文档内容) 的列表。

        Returns:
            成功索引的 KnowledgeDocument 列表。
        """
        if not self.is_ready():
            raise RuntimeError("GraphRAG 引擎未就绪")

        results: list[KnowledgeDocument] = []
        for doc_meta, content in docs:
            try:
                result = await self.insert_document(
                    content,
                    metadata={
                        "doc_id": doc_meta.doc_id,
                        "file_name": doc_meta.file_name,
                        "file_path": doc_meta.file_path,
                    },
                )
                results.append(result)
            except Exception:
                logger.exception("索引文档失败: %s", doc_meta.file_name)
        return results

    async def query(self, query_text: str, mode: str = "hybrid") -> RetrievalResult:
        """执行知识检索。

        Args:
            query_text: 检索查询文本。
            mode: 检索模式 (naive/local/global/hybrid/mix)。

        Returns:
            RetrievalResult 包含检索内容和来源信息。
        """
        if not self.is_ready():
            return RetrievalResult(
                success=False,
                error_message="GraphRAG 引擎未就绪",
            )

        try:
            param = QueryParam(mode=mode)
            result = await self._rag.aquery(query_text, param=param)

            # 提取来源文档标识
            sources = list(self._documents.keys())

            return RetrievalResult(
                content=result if isinstance(result, str) else str(result),
                sources=sources,
                mode=mode,
                success=True,
            )
        except Exception as exc:
            logger.exception("知识检索失败")
            return RetrievalResult(
                success=False,
                error_message=str(exc),
            )

    async def delete_document(self, doc_id: str) -> bool:
        """删除已索引的知识文档。"""
        if not self.is_ready():
            return False

        if doc_id not in self._documents:
            return False

        try:
            await self._rag.adelete_by_doc_id(doc_id)
        except Exception:
            logger.exception("从 LightRAG 删除文档失败: %s", doc_id)

        del self._documents[doc_id]
        self._save_document_registry()
        logger.info("文档已删除: %s", doc_id)
        return True

    async def reindex_all(self, docs_dir: str) -> int:
        """全量重建索引。

        清除现有索引数据，重新扫描文档目录并索引。

        Args:
            docs_dir: 知识文档目录路径。

        Returns:
            成功索引的文档数量。
        """
        from app.knowledge.ingestion import scan_knowledge_directory

        # 关闭并清理
        await self.finalize()

        # 清除工作目录
        working_dir = Path(self._settings.knowledge_working_dir)
        if working_dir.exists():
            import shutil
            shutil.rmtree(working_dir)

        self._documents.clear()

        # 重新初始化
        await self.initialize()
        if not self.is_ready():
            return 0

        # 重新扫描并索引
        scanned = scan_knowledge_directory(
            docs_dir,
            max_doc_size_kb=self._settings.knowledge_max_doc_size_kb,
        )
        results = await self.insert_batch(scanned)
        return len(results)

    def list_documents(self) -> list[KnowledgeDocument]:
        """列出所有已索引文档。"""
        return list(self._documents.values())

    def get_status(self) -> KnowledgeStatus:
        """获取知识库状态。"""
        last_indexed = None
        if self._documents:
            indexed_times = [
                d.indexed_at for d in self._documents.values() if d.indexed_at
            ]
            if indexed_times:
                last_indexed = max(indexed_times)

        return KnowledgeStatus(
            enabled=self._settings.enable_knowledge_retrieval,
            ready=self.is_ready(),
            document_count=len(self._documents),
            last_indexed_at=last_indexed,
            working_dir=self._settings.knowledge_working_dir,
        )

    # ---- 文档注册表持久化 ----

    def _load_document_registry(self) -> None:
        """从工作目录加载文档注册表。"""
        registry_path = Path(self._settings.knowledge_working_dir) / _DOC_REGISTRY_FILE
        if not registry_path.exists():
            return

        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            for doc_data in data:
                doc = KnowledgeDocument.model_validate(doc_data)
                self._documents[doc.doc_id] = doc
        except Exception:
            logger.exception("加载文档注册表失败")

    def _save_document_registry(self) -> None:
        """将文档注册表保存到工作目录。"""
        registry_path = Path(self._settings.knowledge_working_dir) / _DOC_REGISTRY_FILE
        try:
            data = [doc.model_dump(mode="json") for doc in self._documents.values()]
            registry_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("保存文档注册表失败")
