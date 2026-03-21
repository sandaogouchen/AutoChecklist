"""项目级 Checklist 模版领域模型。

定义了项目级 checklist 模版的数据结构，包括：
- ``ProjectChecklistTemplateNode``：模版树节点（支持递归子节点 + mandatory 标记）
- ``ProjectChecklistTemplateMetadata``：模版元数据（名称、版本、描述、强制层级）
- ``ProjectChecklistTemplateFile``：完整的模版文件结构
- ``TemplateLeafTarget``：拍平后的叶子目标，用于 checkpoint 绑定
- ``MandatorySkeletonNode``：强制骨架节点，用于约束 outline 规划
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProjectChecklistTemplateNode(BaseModel):
    """模版树节点。

    支持递归嵌套子节点，叶子节点（children 为空）表示最终的测试归类目标。
    新增 mandatory 标记，支持节点级强制约束。

    Attributes:
        id: 节点唯一标识，在整棵模版树中不可重复。
        title: 节点标题，描述该归类项的含义。
        description: 节点描述信息。
        priority: 优先级标记（如 P0-P3）。
        note: 附加备注。
        status: 节点状态。
        mandatory: 是否为强制节点（默认 False）。
        children: 子节点列表，为空时表示叶子节点。
    """

    id: str
    title: str
    description: str = ""
    priority: str = ""
    note: str = ""
    status: str = ""
    mandatory: bool = False
    children: list[ProjectChecklistTemplateNode] = Field(default_factory=list)


class ProjectChecklistTemplateMetadata(BaseModel):
    """模版元数据。

    Attributes:
        name: 模版名称。
        version: 模版版本号。
        description: 模版描述信息。
        mandatory_levels: 强制层级列表，指定哪些层级深度是强制的。
            层级编号从 1 开始计数（第 1 层 = nodes 的直接子节点）。
    """

    name: str = ""
    version: str = ""
    description: str = ""
    mandatory_levels: list[int] = Field(default_factory=list)

    @field_validator("mandatory_levels")
    @classmethod
    def validate_mandatory_levels(cls, v: list[int]) -> list[int]:
        for level in v:
            if not isinstance(level, int) or level < 1:
                raise ValueError(
                    f"mandatory_levels 中的层级编号必须为正整数 (>= 1)，实际值: {level}"
                )
        return sorted(set(v))


class ProjectChecklistTemplateFile(BaseModel):
    """完整的项目级 Checklist 模版文件。

    对应 YAML 文件的顶层结构，包含元数据和节点树。

    Attributes:
        metadata: 模版元数据。
        nodes: 模版树的顶层节点列表。
    """

    metadata: ProjectChecklistTemplateMetadata = Field(
        default_factory=ProjectChecklistTemplateMetadata
    )
    nodes: list[ProjectChecklistTemplateNode] = Field(default_factory=list)


class TemplateLeafTarget(BaseModel):
    """拍平后的叶子目标。

    将模版树中的每个叶子节点展平为一条记录，
    携带从根到叶子的完整路径信息，供 checkpoint 生成阶段绑定使用。

    Attributes:
        leaf_id: 叶子节点 ID。
        leaf_title: 叶子节点标题。
        path_ids: 从根到叶子的节点 ID 路径（含叶子自身）。
        path_titles: 从根到叶子的节点标题路径（含叶子自身）。
        path_text: 用 " > " 连接的可读路径文本。
    """

    leaf_id: str
    leaf_title: str
    path_ids: list[str] = Field(default_factory=list)
    path_titles: list[str] = Field(default_factory=list)
    path_text: str = ""


class MandatorySkeletonNode(BaseModel):
    """强制骨架节点。

    从模版中提取的仅包含强制节点的子树，
    作为 outline 规划和 case 挂载的硬约束输入。

    Attributes:
        id: 节点 ID（与模版原始 ID 一致）。
        title: 节点标题。
        depth: 节点在模版树中的深度（从 1 开始）。
        is_mandatory: 是否为强制节点。
        source: 节点来源标记，固定为 "template"。
        original_metadata: 保留模版节点的原始元信息（priority/note/status 等）。
        children: 子骨架节点列表。
    """

    id: str
    title: str
    depth: int
    is_mandatory: bool
    source: Literal["template"] = "template"
    original_metadata: dict = Field(default_factory=dict)
    children: list[MandatorySkeletonNode] = Field(default_factory=list)


# Pydantic v2 要求显式 rebuild 以支持自引用
ProjectChecklistTemplateNode.model_rebuild()
MandatorySkeletonNode.model_rebuild()
