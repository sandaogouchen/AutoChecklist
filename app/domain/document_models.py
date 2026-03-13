from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentSource(BaseModel):
    source_path: str
    source_type: str
    title: str = ""
    checksum: str = ""


class DocumentSection(BaseModel):
    heading: str
    level: int
    content: str = ""
    line_start: int
    line_end: int


class ParsedDocument(BaseModel):
    raw_text: str
    sections: list[DocumentSection] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: DocumentSource | None = None
