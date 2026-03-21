"""知识库管理 API 路由。

提供知识文档的上传索引、列表查看、删除、手动查询、
全量重建索引和状态查询等 REST 端点。

路由前缀：``/api/v1/knowledge``
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.knowledge.graphrag_engine import GraphRAGEngine
from app.knowledge.ingestion import validate_document_path
from app.knowledge.models import KnowledgeDocument, KnowledgeStatus

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


def _get_engine(request: Request) -> GraphRAGEngine:
    """从 app.state 获取 GraphRAG 引擎实例。"""
    engine: Optional[GraphRAGEngine] = getattr(request.app.state, "graphrag_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="知识检索功能未启用或引擎未初始化",
        )
    return engine


# ---- 请求/响应模型 ----

class DocumentUploadRequest(BaseModel):
    file_path: str = Field(..., min_length=1, description="本地 Markdown 文件路径")


class DocumentUploadResponse(BaseModel):
    doc_id: str
    file_name: str
    status: str = "indexed"
    entity_count: int = 0


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="查询文本")
    mode: str = Field(default="hybrid", description="检索模式: naive/local/global/hybrid/mix")


class KnowledgeQueryResponse(BaseModel):
    result: str
    sources: list[str] = Field(default_factory=list)
    mode: str = "hybrid"


class ReindexResponse(BaseModel):
    status: str = "started"
    doc_count: int = 0


# ---- 端点 ----

@router.post("/documents", status_code=201, response_model=DocumentUploadResponse)
async def upload_document(
    body: DocumentUploadRequest,
    engine: GraphRAGEngine = Depends(_get_engine),
):
    """上传并索引一个新的 Markdown 知识文档。"""
    from app.config.settings import get_settings

    settings = get_settings()
    try:
        content = validate_document_path(
            body.file_path,
            max_doc_size_kb=settings.knowledge_max_doc_size_kb,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    from pathlib import Path

    file_path = Path(body.file_path).resolve()
    try:
        doc = await engine.insert_document(
            content,
            metadata={
                "file_name": file_path.name,
                "file_path": str(file_path),
            },
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return DocumentUploadResponse(
        doc_id=doc.doc_id,
        file_name=doc.file_name,
        status="indexed",
        entity_count=doc.entity_count,
    )


@router.get("/documents")
async def list_documents(
    engine: GraphRAGEngine = Depends(_get_engine),
) -> list[dict]:
    """列出所有已索引的知识文档。"""
    docs = engine.list_documents()
    return [doc.model_dump(mode="json") for doc in docs]


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    engine: GraphRAGEngine = Depends(_get_engine),
):
    """删除指定的知识文档。"""
    deleted = await engine.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"文档未找到: {doc_id}")
    return None


@router.post("/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(
    body: KnowledgeQueryRequest,
    engine: GraphRAGEngine = Depends(_get_engine),
):
    """手动查询知识库（调试用）。"""
    result = await engine.query(body.query, mode=body.mode)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error_message)

    return KnowledgeQueryResponse(
        result=result.content,
        sources=result.sources,
        mode=result.mode,
    )


@router.post("/reindex", response_model=ReindexResponse)
async def reindex_knowledge(
    engine: GraphRAGEngine = Depends(_get_engine),
):
    """触发全量重建索引。"""
    from app.config.settings import get_settings

    settings = get_settings()
    try:
        count = await engine.reindex_all(settings.knowledge_docs_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"重建索引失败: {exc}")

    return ReindexResponse(status="completed", doc_count=count)


@router.get("/status", response_model=KnowledgeStatus)
async def get_knowledge_status(
    engine: GraphRAGEngine = Depends(_get_engine),
):
    """获取知识库状态信息。"""
    return engine.get_status()
