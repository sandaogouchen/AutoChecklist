"""XMind 参考文件加载节点。

作为 LangGraph 主工作流的节点，加载并分析用户提供的参考 XMind 文件，
将结构摘要写入 GlobalState。

遵循项目工厂闭包模式（``build_*_node()``），
与 knowledge_retrieval 节点的降级策略对齐——解析失败时不阻断工作流。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.domain.state import GlobalState
from app.parsers.xmind_parser import XMindParseError, XMindParser
from app.services.xmind_reference_analyzer import XMindReferenceAnalyzer

logger = logging.getLogger(__name__)


def build_xmind_reference_loader_node(
    parser: XMindParser,
    analyzer: XMindReferenceAnalyzer,
) -> Callable[[GlobalState], dict[str, Any]]:
    """构建 XMind 参考加载节点。

    Args:
        parser: XMind 解析器实例。
        analyzer: XMind 参考分析器实例。

    Returns:
        LangGraph 节点函数。
    """

    def node(state: GlobalState) -> dict[str, Any]:
        """加载并分析参考 XMind 文件。

        当 ``reference_xmind_path`` 为空时直接跳过（返回空增量）。
        解析失败时记录 warning 日志并降级为无参考模式。
        """
        ref_path = state.get("reference_xmind_path")
        if not ref_path:
            return {}

        try:
            root = parser.parse(ref_path)
            summary = analyzer.analyze(root, source_file=ref_path)
            logger.info(
                "XMind 参考文件加载成功: %s（%d 个节点, %d 个叶子）",
                ref_path,
                summary.total_nodes,
                summary.total_leaf_nodes,
            )
            return {"xmind_reference_summary": summary}
        except (FileNotFoundError, XMindParseError) as exc:
            logger.warning(
                "XMind 参考文件加载失败，降级为无参考模式: %s — %s",
                ref_path,
                exc,
            )
            return {}
        except Exception as exc:
            logger.warning(
                "XMind 参考文件处理异常，降级为无参考模式: %s — %s",
                ref_path,
                exc,
            )
            return {}

    return node
