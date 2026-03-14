from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.research_models import EvidenceRef


class TestCase(BaseModel):
    __test__ = False

    id: str
    fact_id: str = ""
    node_type: str = "check"
    title: str
    branch: str = "main"
    parent: str | None = None
    root: str | None = None
    prev: str | None = None
    next: str | None = None
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)
    priority: str = "P2"
    category: str = "functional"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    children: list["TestCase"] = Field(default_factory=list)


class QualityReport(BaseModel):
    duplicate_groups: list[list[str]] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    repaired_fields: list[str] = Field(default_factory=list)


TestCase.model_rebuild()
