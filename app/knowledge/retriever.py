"""知识检索接口封装。

提供查询构造和结果格式化功能，将 GraphRAG 引擎的原始检索结果
转换为可直接注入 LLM prompt 的格式化文本。
"""

from __future__ import annotations

import logging
from typing import Optional

from app.domain.document_models import ParsedDocument
from app.knowledge.graphrag_engine import GraphRAGEngine
from app.knowledge.models import RetrievalResult

logger = logging.getLogger(__name__)

# 注入 prompt 的知识上下文最大字符数
MAX_KNOWLEDGE_CONTEXT_CHARS = 2000


def build_retrieval_query(parsed_document: ParsedDocument) -> str:
    """从 PRD 文档中构造检索查询文本。

    提取文档标题和前若干行正文作为检索查询，
    控制在 500 字符以内以提高检索精度。

    Args:
        parsed_document: 解析后的 PRD 文档。

    Returns:
        检索查询文本。
    """
    parts: list[str] = []

    # 提取标题
    if parsed_document.source and parsed_document.source.title:
        parts.append(parsed_document.source.title)

    # 提取正文前 400 字符
    if parsed_document.raw_text:
        body_preview = parsed_document.raw_text[:400].strip()
        parts.append(body_preview)

    query = "\n".join(parts)
    # 截断到 500 字符
    return query[:500] if len(query) > 500 else query


def format_retrieval_result(result: RetrievalResult) -> str:
    """将检索结果格式化为可注入 prompt 的文本。

    格式化为 Markdown 段落，包含来源信息，
    并截断到最大字符限制。

    Args:
        result: GraphRAG 检索结果。

    Returns:
        格式化后的知识上下文文本。空结果返回空字符串。
    """
    if not result.success or not result.content.strip():
        return ""

    formatted = result.content.strip()

    # 截断到最大字符限制
    if len(formatted) > MAX_KNOWLEDGE_CONTEXT_CHARS:
        formatted = formatted[:MAX_KNOWLEDGE_CONTEXT_CHARS] + "\n...(知识检索结果已截断)"

    return formatted


async def retrieve_knowledge(
    engine: GraphRAGEngine,
    parsed_document: ParsedDocument,
    mode: str = "hybrid",
) -> tuple[str, list[str], bool]:
    """执行完整的知识检索流程。

    从 PRD 文档构造查询 → 调用 GraphRAG 检索 → 格式化结果。

    Args:
        engine: GraphRAG 引擎实例。
        parsed_document: 解析后的 PRD 文档。
        mode: 检索模式。

    Returns:
        (knowledge_context, knowledge_sources, success) 三元组。
    """
    if not engine.is_ready():
        logger.info("GraphRAG 引擎未就绪，跳过知识检索")
        return "", [], False

    query = build_retrieval_query(parsed_document)
    if not query.strip():
        logger.warning("无法从 PRD 构造有效的检索查询")
        return "", [], True

    logger.info("执行知识检索 (mode=%s, query_len=%d)", mode, len(query))
    result = await engine.query(query, mode=mode)

    context = format_retrieval_result(result)
    sources = result.sources if result.success else []

    logger.info(
        "知识检索完成 (success=%s, context_len=%d, sources=%d)",
        result.success,
        len(context),
        len(sources),
    )
    return context, sources, result.success
