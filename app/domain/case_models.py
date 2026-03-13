from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.research_models import EvidenceRef


class TestCase(BaseModel):
    __test__ = False

    id: str
    title: str
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)
    priority: str = "P2"
    category: str = "functional"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class QualityReport(BaseModel):
    duplicate_groups: list[list[str]] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    repaired_fields: list[str] = Field(default_factory=list)
