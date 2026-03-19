"""Checklist 共享逻辑树优化节点。

在 ``structure_assembler`` 之后执行：
1. 使用 LLM 将 ``test_cases`` 归一化为共享语义路径
2. 将语义路径合并为共享前缀树 ``optimized_tree``
3. 返回增量更新 ``{test_cases, optimized_tree}``

异常安全：任何优化错误仅记录日志，返回空 tree，下游回退到扁平渲染。
"""

from __future__ import annotations

import logging
from typing import Any

from app.clients.llm import LLMClient
from app.config.settings import get_settings
from app.domain.state import CaseGenState
from app.services.checklist_merger import ChecklistMerger
from app.services.semantic_path_normalizer import SemanticPathNormalizer

logger = logging.getLogger(__name__)


def build_checklist_optimizer_node(llm_client: LLMClient):
    """构建使用 LLM 语义归一化的 checklist optimizer 节点。"""

    def checklist_optimizer_node(state: CaseGenState) -> dict[str, Any]:
        """将 test_cases 归一化为共享逻辑树 optimized_tree。"""
        test_cases = state.get("test_cases", [])

        if not test_cases:
            return {"test_cases": test_cases, "optimized_tree": []}

        settings = get_settings()
        if not settings.enable_checklist_optimization:
            return {"test_cases": test_cases, "optimized_tree": []}

        try:
            normalized_paths = SemanticPathNormalizer(llm_client).normalize(test_cases)
            optimized_tree = ChecklistMerger().merge(normalized_paths)
        except Exception:
            logger.warning(
                "Checklist semantic optimization failed; returning empty tree",
                exc_info=True,
            )
            optimized_tree = []

        return {"test_cases": test_cases, "optimized_tree": optimized_tree}

    return checklist_optimizer_node


def checklist_optimizer_node(state: CaseGenState) -> dict[str, Any]:
    """兼容旧调用入口。

    未注入 LLM 客户端时不执行语义优化，直接回退为扁平渲染。
    """
    test_cases = state.get("test_cases", [])
    return {"test_cases": test_cases, "optimized_tree": []}
