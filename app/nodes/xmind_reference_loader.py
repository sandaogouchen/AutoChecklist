"""XMind 参考文件加载器节点。

将用户提供的参考 XMind 文件解析并分析为 ``XMindReferenceSummary``，
同时生成确定性 ChecklistNode 参考树，存入 GlobalState。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.domain.state import GlobalState
from app.parsers.xmind_parser import XMindParseError, XMindParser
from app.services.xmind_reference_analyzer import XMindReferenceAnalyzer
from app.services.xmind_reference_tree_converter import XMindReferenceTreeConverter

logger = logging.getLogger(__name__)


def build_xmind_reference_loader_node(
    parser: XMindParser,
    analyzer: XMindReferenceAnalyzer,
    tree_converter: XMindReferenceTreeConverter | None = None,
) -> Callable[[GlobalState], dict[str, Any]]:
    """构建 XMind 参考加载器节点。

    Parameters
    ----------
    parser : XMindParser
        XMind 文件解析器。
    analyzer : XMindReferenceAnalyzer
        参考结构分析器。
    tree_converter : XMindReferenceTreeConverter | None
        参考树转换器。为 None 时跳过确定性树转换。

    Returns
    -------
    Callable
        LangGraph 节点函数。
    """

    def node(state: GlobalState) -> dict[str, Any]:
        ref_path = state.get("reference_xmind_path")
        if not ref_path:
            request = state.get("request")
            if request is not None:
                ref_path = getattr(request, "reference_xmind_file_id", None)

        if not ref_path:
            return {}

        try:
            root = parser.parse(ref_path)
            summary = analyzer.analyze(root, source_file=ref_path)

            # 增强：生成确定性参考树 & 叶子标题列表
            if tree_converter is not None:
                try:
                    reference_tree = tree_converter.convert(root)
                    all_leaf_titles = tree_converter.get_leaf_titles(root)
                    summary.reference_tree = reference_tree
                    summary.all_leaf_titles = all_leaf_titles
                    logger.info(
                        "参考树转换完成: %d 一级分支, %d 叶子节点",
                        len(reference_tree),
                        len(all_leaf_titles),
                    )
                except Exception:
                    logger.warning(
                        "参考树转换失败，降级为仅 summary 模式",
                        exc_info=True,
                    )

            return {"xmind_reference_summary": summary}

        except FileNotFoundError:
            logger.warning("参考 XMind 文件未找到: %s", ref_path)
            return {}
        except XMindParseError:
            logger.warning("参考 XMind 文件解析失败: %s", ref_path, exc_info=True)
            return {}
        except Exception:
            logger.warning(
                "加载参考 XMind 时发生意外错误: %s",
                ref_path,
                exc_info=True,
            )
            return {}

    return node
