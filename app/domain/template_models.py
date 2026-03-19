"""项目级 Checklist 模版领域模型。

定义了项目级 checklist 模版的数据结构，包括：
- ``ProjectChecklistTemplateNode``：模版树节点（支持递归子节点）
- ``ProjectChecklistTemplateMetadata``：模版元数据（名称、版本、描述）
- ``ProjectChecklistTemplateFile``：完整的模版文件结构
- ``TemplateLeafTarget``：拍平后的叶子目标，用于 checkpoint 绑定
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectChecklistTemplateNode(BaseModel):
    """模版树节点。

    支持递归嵌套子节点，叶子节点（children 为空）表示最终的测试归类目标。

    Attributes:
        id: 节点唯一标识，在整棵模版树中不可重复。
        title: 节点标题，描述该归类项的含义。
        children: 子节点列表，为空时表示叶子节点。
    """

    id: str
    title: str
    children: list[ProjectChecklistTemplateNode] = Field(default_factory=list)


class ProjectChecklistTemplateMetadata(BaseModel):
    """模版元数据。

    Attributes:
        name: 模版名称。
        version: 模版版本号。
        description: 模版描述信息。
    """

    name: str = ""
    version: str = ""
    description: str = ""


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


# Pydantic v2 要求显式 rebuild 以支持自引用
ProjectChecklistTemplateNode.model_rebuild()
