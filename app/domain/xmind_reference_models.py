"""XMind 参考文件相关领域模型。

定义 XMind 文件反向解析和结构分析所需的数据结构：
- ``XMindReferenceNode``：解析后的 XMind 树节点（输入模型：XMind→系统）
- ``XMindReferenceSummary``：结构分析结果摘要

与 ``xmind_models.XMindTopic``（输出模型：系统→XMind）不同，
本模块的模型用于反向读取已有 XMind 文件并提取结构信息。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.domain.checklist_models import ChecklistNode


class XMindReferenceNode(BaseModel):
    """XMind 参考文件解析后的树节点。

    仅提取节点标题和子节点层级关系，忽略 notes、markers、labels 等附加信息。
    """

    title: str
    children: list[XMindReferenceNode] = Field(default_factory=list)


class XMindReferenceSummary(BaseModel):
    """XMind 参考文件的结构分析结果。

    包含骨架提取、代表性路径采样、统计信息和预渲染的 prompt 注入文本。
    由 ``XMindReferenceAnalyzer.analyze()`` 生成。
    """

    # 元信息
    source_file: str
    total_nodes: int
    total_leaf_nodes: int
    max_depth: int

    # 结构骨架（前 2-3 层缩进文本）
    skeleton: str

    # 代表性路径采样
    sampled_paths: list[str] = Field(default_factory=list)

    # 统计信息
    depth_distribution: dict[int, int] = Field(default_factory=dict)
    top_prefixes: list[str] = Field(default_factory=list)

    # prompt 可注入的格式化摘要
    formatted_summary: str

    # ---- 增强字段：确定性参考树 ----
    reference_tree: list = Field(
        default_factory=list,
        description="参考 XMind 完整转换后的 ChecklistNode 树",
    )
    all_leaf_titles: list[str] = Field(
        default_factory=list,
        description="参考 XMind 所有叶子节点标题（用于覆盖度检测）",
    )
