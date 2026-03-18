"""Pydantic models used by the REST API layer.

Kept separate from internal domain models so the external contract can
evolve independently of the core logic.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Body of the ``POST /run`` endpoint."""

    case_id: str = Field(..., description="Identifier of the test-case to process.")
    project_id: Optional[str] = Field(
        default=None,
        description="Optional project context id to attach to this run.",
    )
    options: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    """Envelope returned by ``POST /run``."""

    run_id: str
    status: str
    result: Optional[dict[str, Any]] = None
