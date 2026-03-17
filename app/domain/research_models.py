from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, model_validator

EVIDENCE_REF_PATTERN = re.compile(
    r"^\s*(?P<section>.+?)\s*\((?P<line_start>\d+)(?:-(?P<line_end>\d+))?\)\s*:\s*(?P<excerpt>.*)\s*$"
)


class EvidenceRef(BaseModel):
    section_title: str
    excerpt: str = ""
    line_start: int = 0
    line_end: int = 0
    confidence: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def coerce_string_reference(cls, value: Any) -> Any:
        if isinstance(value, dict):
            normalized_value = dict(value)
            if "section_title" not in normalized_value and isinstance(normalized_value.get("section"), str):
                normalized_value["section_title"] = normalized_value["section"].strip()
            if "excerpt" not in normalized_value and isinstance(normalized_value.get("quote"), str):
                normalized_value["excerpt"] = normalized_value["quote"].strip()
            return normalized_value

        if not isinstance(value, str):
            return value

        normalized_value = value.strip()
        if not normalized_value:
            return {"section_title": "generated_ref"}

        pattern_match = EVIDENCE_REF_PATTERN.match(normalized_value)
        if pattern_match:
            line_start = int(pattern_match.group("line_start"))
            line_end = int(pattern_match.group("line_end") or line_start)
            return {
                "section_title": pattern_match.group("section").strip(),
                "excerpt": pattern_match.group("excerpt").strip(),
                "line_start": line_start,
                "line_end": line_end,
            }

        section_title, separator, excerpt = normalized_value.partition(":")
        if separator:
            return {
                "section_title": section_title.strip(),
                "excerpt": excerpt.strip(),
            }

        return {"section_title": normalized_value}


class ResearchFact(BaseModel):
    id: str
    summary: str
    change_type: str = "behavior"
    requirement: str = ""
    branch_hint: str = "main"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_requirement_object(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized_value = dict(value)
        requirement = normalized_value.get("requirement")
        if not isinstance(requirement, dict):
            return normalized_value

        scope = str(requirement.get("scope", "")).strip()
        detail = str(requirement.get("detail", "")).strip()
        parts = [part for part in (scope, detail) if part]
        normalized_value["requirement"] = " | ".join(parts)
        return normalized_value


class PlannedScenario(BaseModel):
    title: str
    fact_id: str = ""
    category: str = "functional"
    risk: str = "medium"
    rationale: str = ""
    branch_hint: str = "main"


class ResearchOutput(BaseModel):
    feature_topics: list[str] = Field(default_factory=list)
    user_scenarios: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    test_signals: list[str] = Field(default_factory=list)
    facts: list[ResearchFact] = Field(default_factory=list)
