"""知识检索节点。

LangGraph 工作流节点，在 context_research 之前执行，
从 GraphRAG 知识库中检索与 PRD 相关的业务知识。

遵循项目的 factory closure 模式：外层函数接收依赖（GraphRAGEngine），
返回符合 LangGraph 节点签名的内层函数。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.config.settings import Settings
from app.knowledge.graphrag_engine import GraphRAGEngine
from app.knowledge.retriever import retrieve_knowledge

logger = logging.getLogger(__name__)


def build_knowledge_retrieval_node(
    engine: GraphRAGEngine,
    settings: Settings,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """构建知识检索节点的工厂函数。

    使用闭包捕获 ``engine`` 和 ``settings``，返回符合 LangGraph
    节点签名的可调用对象。

    与 ``build_project_context_loader`` 遵循相同的 factory closure 模式：
    外层函数接收依赖，返回内层节点函数。

    Args:
        engine: GraphRAG 引擎实例。
        settings: 应用配置实例。

    Returns:
        一个 ``(state: dict) -> dict`` 可调用对象，可注册为 LangGraph 节点。
    """

    import asyncio

    def _knowledge_retrieval_node(state: dict[str, Any]) -> dict[str, Any]:
        """从知识库检索与 PRD 相关的业务知识。

        节点行为：
        1. 检查引擎是否就绪
        2. 从 state 中获取 parsed_document
        3. 调用 retrieve_knowledge 执行检索
        4. 将结果写入 state

        降级策略：
        - 引擎未就绪 → 返回空结果
        - 检索异常 → try-except 捕获，返回空结果
        - 任何失败均不阻断主工作流
        """
        empty_result = {
            "knowledge_context": "",
            "knowledge_sources": [],
            "knowledge_retrieval_success": False,
        }

        if not engine.is_ready():
            logger.info("GraphRAG 引擎未就绪，跳过知识检索")
            return empty_result

        parsed_document = state.get("parsed_document")
        if parsed_document is None:
            logger.warning("state 中缺少 parsed_document，跳过知识检索")
            return empty_result

        try:
            mode = settings.knowledge_retrieval_mode

            # 在同步节点中运行异步检索
            loop = asyncio.new_event_loop()
            try:
                context, sources, success = loop.run_until_complete(
                    retrieve_knowledge(engine, parsed_document, mode=mode)
                )
            finally:
                loop.close()

            logger.info(
                "知识检索节点完成 (success=%s, context_len=%d)",
                success,
                len(context),
            )
            return {
                "knowledge_context": context,
                "knowledge_sources": sources,
                "knowledge_retrieval_success": success,
            }
        except Exception:
            logger.exception("知识检索节点异常，降级为空结果")
            return empty_result

    return _knowledge_retrieval_node