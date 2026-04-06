"""LLM 语义分组的 Pydantic 响应模型。

供 PreconditionGrouper._llm_merge_buckets() 使用，
通过 LLMClient.generate_structured() 获得结构化的分组结果。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SemanticGroup(BaseModel):
    """语义等价的前置条件组。"""

    representative: str = Field(
        description="该组最简洁清晰的代表名称",
    )
    member_indices: list[int] = Field(
        description="属于该组的前置条件编号列表（1-based）",
    )


class PreconditionGroupingResult(BaseModel):
    """LLM 前置条件分组结果。"""

    groups: list[SemanticGroup] = Field(
        description="语义分组列表",
    )
