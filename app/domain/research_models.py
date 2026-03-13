from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    section_title: str
    excerpt: str = ""
    line_start: int = 0
    line_end: int = 0
    confidence: float = 0.0


class PlannedScenario(BaseModel):
    title: str
    category: str = "functional"
    risk: str = "medium"
    rationale: str = ""


class ResearchOutput(BaseModel):
    feature_topics: list[str] = Field(default_factory=list)
    user_scenarios: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    test_signals: list[str] = Field(default_factory=list)
