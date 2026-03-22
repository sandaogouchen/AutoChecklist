"""模板抽象化 LangGraph 节点。

将 ``TemplateAbstractorService`` 包装为 LangGraph 节点函数，
插入在 ``xmind_reference_loader`` 之后、``checkpoint_outline_planner`` 之前。

节点从 ``GlobalState`` 中读取 ``xmind_reference_summary``，
调用抽象化服务生成 ``AbstractedReferenceSchema``，
并将结果写入 state 的 ``abstracted_reference_schema`` 字段。
"""

from __future__ import annotations

from typing import Any, Callable

import structlog

from app.clients.llm import LLMClient
from app.domain.state import GlobalState
from app.services.template_abstractor import TemplateAbstractorService

logger = structlog.get_logger(__name__)


def build_template_abstractor_node(
    llm_client: LLMClient,
) -> Callable[[GlobalState], dict[str, Any]]:
    """构建模板抽象化节点。

    Parameters
    ----------
    llm_client : LLMClient
        LLM 客户端实例，传递给 ``TemplateAbstractorService``。

    Returns
    -------
    Callable
        LangGraph 节点函数，接收 ``GlobalState`` 返回增量更新 dict。
    """
    service = TemplateAbstractorService(llm_client)

    def template_abstractor_node(
        state: GlobalState,
    ) -> dict[str, Any]:
        """模板抽象化节点。

        从 state 中获取 ``xmind_reference_summary``，如果不存在或
        ``reference_tree`` 为空则跳过，返回 ``None``。
        否则调用 ``TemplateAbstractorService.abstract()`` 生成
        ``AbstractedReferenceSchema``。
        """
        xmind_reference_summary = state.get("xmind_reference_summary")

        if xmind_reference_summary is None:
            logger.warning(
                "template_abstractor_node: "
                "xmind_reference_summary 不存在，跳过抽象化"
            )
            return {"abstracted_reference_schema": None}

        reference_tree = getattr(
            xmind_reference_summary, "reference_tree", None
        )
        if not reference_tree:
            logger.warning(
                "template_abstractor_node: "
                "reference_tree 为空，跳过抽象化",
                source_file=getattr(
                    xmind_reference_summary, "source_file", ""
                ),
            )
            return {"abstracted_reference_schema": None}

        total_nodes = getattr(xmind_reference_summary, "total_nodes", 0)
        logger.info(
            "template_abstractor_node: 开始模板抽象化",
            source_file=getattr(
                xmind_reference_summary, "source_file", ""
            ),
            total_nodes=total_nodes,
            reference_tree_roots=len(reference_tree),
        )

        try:
            result = service.abstract(xmind_reference_summary)
        except Exception:
            logger.exception(
                "template_abstractor_node: 模板抽象化失败",
                source_file=getattr(
                    xmind_reference_summary, "source_file", ""
                ),
            )
            return {"abstracted_reference_schema": None}

        logger.info(
            "template_abstractor_node: 模板抽象化完成",
            modules=len(result.modules),
            total_dimensions=result.total_dimensions,
            total_source_nodes=result.total_source_nodes,
            abstraction_source=result.abstraction_source,
        )

        return {"abstracted_reference_schema": result}

    return template_abstractor_node
