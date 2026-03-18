"""Domain models related to individual test-case artefacts."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    """Minimal representation of a test case fed into the workflow."""

    id: str
    title: str = ""
    description: str = ""
    project_id: Optional[str] = Field(
        default=None,
        description="FK-style link to the parent ProjectContext.",
    )
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
