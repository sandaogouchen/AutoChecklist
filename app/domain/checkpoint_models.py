"""检查点领域模型。"""
from __future__ import annotations

import hashlib
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.research_models import EvidenceRef


class Checkpoint(BaseModel):
    """测试检查点。"""
    checkpoint_id: str = ""
    title: str
    objective: str = ""
    category: str = "functional"
    priority: str = "medium"
    fact_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    verification_criteria: list[str] = Field(default_factory=list)
    # ---- 模板驱动生成支持：记录检查点所属的模板维度与条目 ----
    template_category: Optional[str] = None       # 对应模板中的维度分类名
    template_item_title: Optional[str] = None     # 对应模板中的具体条目标题

    def compute_id(self) -> str:
        """基于 title + objective 计算 SHA-256 ID。"""
        raw = f"{self.title}|{self.objective}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class CheckpointCoverage(BaseModel):
    """检查点覆盖率。"""
    total_checkpoints: int = 0
    covered_checkpoints: int = 0
    coverage_ratio: float = 0.0
    uncovered_ids: list[str] = Field(default_factory=list)
