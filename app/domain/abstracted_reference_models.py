"""模板抽象化相关领域模型。

定义 XMind 参考模板抽象化后的数据结构：
- ``VerificationDimension``：单个验证维度
- ``AbstractedSubmodule``：抽象化后的子模块
- ``AbstractedModule``：抽象化后的顶层模块
- ``AbstractedReferenceSchema``：完整的抽象化输出
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VerificationDimension(BaseModel):
    """单个验证维度描述。

    描述一类需要验证的测试意图，不包含具体字段名、API 路径或 UI 控件名。
    """

    name: str = Field(..., description="维度名称，如'草稿CRUD全生命周期'")
    description: str = Field(
        ..., description="一句话描述验证目的，禁止包含具体字段名/API路径"
    )
    mode: str = Field(
        default="positive",
        description=(
            "验证模式: positive/negative/boundary/"
            "compatibility/data_consistency"
        ),
    )
    source_leaf_count: int = Field(
        default=0, description="该维度在原模板中对应的叶子节点数（密度提示）"
    )


class AbstractedSubmodule(BaseModel):
    """抽象化后的子模块（对应模板 L3 层级）。"""

    title: str = Field(..., description="子模块标题")
    dimensions: list[VerificationDimension] = Field(default_factory=list)
    density: str = Field(
        default="normal",
        description="low/normal/high，基于原模板叶子数判定",
    )


class AbstractedModule(BaseModel):
    """抽象化后的单个模块（对应模板 L2 层级）。"""

    title: str = Field(..., description="模块标题，如 'FE（模版广告创编）'")
    category: str = Field(
        default="general",
        description=(
            "模块类别: frontend_e2e / backend_api / config / "
            "environment / documentation / data_validation / general"
        ),
    )
    submodules: list[AbstractedSubmodule] = Field(default_factory=list)
    total_source_nodes: int = Field(
        default=0, description="原模板中该模块的总节点数"
    )
    boundary_hints: list[str] = Field(
        default_factory=list,
        description="从叶子节点提取的关键数值/阈值/枚举值",
    )


class AbstractedReferenceSchema(BaseModel):
    """模板抽象化的完整输出。

    将完整 XMind 参考树（数千节点）压缩为 50-80 个验证维度标签，
    保留结构骨架和验证维度，丢弃具体用例文本。
    """

    modules: list[AbstractedModule] = Field(default_factory=list)
    total_source_nodes: int = Field(default=0)
    total_dimensions: int = Field(default=0)
    abstraction_source: str = Field(
        default="", description="原模板文件名"
    )
