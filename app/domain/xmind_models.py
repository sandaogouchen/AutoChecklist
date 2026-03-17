"""XMind 交付领域模型。

定义了 XMind 思维导图生成与交付过程中使用的数据结构：
- ``XMindNode``：思维导图中的节点
- ``XMindDeliveryResult``：XMind 交付结果
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class XMindNode(BaseModel):
    """思维导图节点。

    表示 XMind 思维导图中的一个节点，支持嵌套子节点，
    用于构建从测试用例到思维导图的层次结构映射。

    Attributes:
        title: 节点标题文本。
        children: 子节点列表。
        markers: 标记列表（对应 XMind 的图标标记，如优先级、分类等）。
        notes: 备注文本（显示在节点的备注区域）。
        labels: 标签列表（显示在节点下方的标签）。
    """

    title: str
    children: list[XMindNode] = Field(default_factory=list)
    markers: list[str] = Field(default_factory=list)
    notes: str = ""
    labels: list[str] = Field(default_factory=list)


class XMindDeliveryResult(BaseModel):
    """XMind 交付结果。

    记录 XMind 文件生成和交付的状态信息。

    Attributes:
        success: 交付是否成功。
        file_path: 生成的 .xmind 文件路径。
        map_url: 思维导图的在线访问地址（如适用）。
        map_id: 思维导图的唯一标识（如适用）。
        error_message: 失败时的错误信息。
        delivery_time: 交付完成的时间戳。
    """

    success: bool = False
    file_path: str = ""
    map_url: str = ""
    map_id: str = ""
    error_message: str = ""
    delivery_time: str = Field(default_factory=lambda: datetime.now().isoformat())
