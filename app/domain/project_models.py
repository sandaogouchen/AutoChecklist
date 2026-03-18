"""Domain models for project-level context in AutoChecklist."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ProjectType(str, Enum):
    """Supported project / technology types."""

    WEB_APP = "web_app"
    MOBILE_APP = "mobile_app"
    API_SERVICE = "api_service"
    DATA_PIPELINE = "data_pipeline"
    EMBEDDED = "embedded"
    DESKTOP = "desktop"
    OTHER = "other"


class RegulatoryFramework(str, Enum):
    """Well-known regulatory / standards frameworks."""

    DO_178C = "DO-178C"
    IEC_62304 = "IEC-62304"
    ISO_26262 = "ISO-26262"
    IEC_61508 = "IEC-61508"
    GDPR = "GDPR"
    HIPAA = "HIPAA"
    SOC2 = "SOC2"
    CUSTOM = "custom"


class ProjectContext(BaseModel):
    """Immutable snapshot of everything we know about the *project* that
    the test-case belongs to.  Stored once, referenced by every run."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    project_type: ProjectType = ProjectType.OTHER
    regulatory_frameworks: list[RegulatoryFramework] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    custom_standards: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # --- helpers ----------------------------------------------------------
    def summary_text(self) -> str:
        """One-paragraph summary suitable for injection into an LLM prompt."""
        parts = [f"Project '{self.name}'"]
        if self.description:
            parts.append(f"\u2014 {self.description}")
        if self.project_type != ProjectType.OTHER:
            parts.append(f"Type: {self.project_type.value}.")
        if self.regulatory_frameworks:
            names = ", ".join(f.value for f in self.regulatory_frameworks)
            parts.append(f"Regulatory frameworks: {names}.")
        if self.tech_stack:
            parts.append(f"Tech stack: {', '.join(self.tech_stack)}.")
        if self.custom_standards:
            parts.append(f"Custom standards: {', '.join(self.custom_standards)}.")
        return " ".join(parts)
