"""LangGraph 节点：Checklist 优化器。

在用例生成子图中位于 ``structure_assembler`` 之后、``END`` 之前，
负责两步优化：
1. 文本精炼（F2）：调用 ``refine_test_case`` 去除冗余前缀/后缀
2. 前置操作合并（F1）：调用 ``ChecklistMerger.merge`` 构建树形结构

采用 graceful degradation 策略——任一步骤异常时回退到原始 test_cases。
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.state import CaseGenState
from app.services.checklist_merger import ChecklistMerger
from app.services.text_normalizer import refine_test_case

logger = logging.getLogger(__name__)


def checklist_optimizer_node(state: CaseGenState) -> dict[str, Any]:
    """LangGraph 节点函数：优化 Checklist。

    Args:
        state: 用例生成子图状态，需包含 ``test_cases`` 键。

    Returns:
        增量状态更新，包含：
        - ``test_cases``: 精炼后的测试用例列表
        - ``optimized_tree``: 合并后的 ChecklistNode 树（可能为空列表）
    """
    test_cases = state.get("test_cases", [])
    if not test_cases:
        return {"test_cases": [], "optimized_tree": []}

    language = state.get("language", "zh-CN")

    # ---- Step 1: 文本精炼 ----
    refined_cases = []
    for case in test_cases:
        try:
            refined = refine_test_case(case, language=language)
            refined_cases.append(refined)
        except Exception:
            logger.warning(
                "refine_test_case failed for %s, keeping original",
                getattr(case, "id", "unknown"),
                exc_info=True,
            )
            refined_cases.append(case)

    # ---- Step 2: 前置操作合并 ----
    try:
        merger = ChecklistMerger()
        optimized_tree = merger.merge(refined_cases)
    except Exception:
        logger.warning(
            "ChecklistMerger.merge failed, returning empty tree",
            exc_info=True,
        )
        optimized_tree = []

    return {
        "test_cases": refined_cases,
        "optimized_tree": optimized_tree,
    }
